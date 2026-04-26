from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import plistlib
import re
import secrets as py_secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import tomllib

CLI_MAX_SUPPORTED_SCHEMA = 1


SPARK_HOME = Path(os.environ.get("SPARK_HOME", Path.home() / ".spark")).expanduser()
STATE_DIR = SPARK_HOME / "state"
CONFIG_DIR = SPARK_HOME / "config"
MODULE_CONFIG_DIR = CONFIG_DIR / "modules"
LOG_DIR = SPARK_HOME / "logs"
REGISTRY_PATH = STATE_DIR / "installed.json"
CONFIG_PATH = STATE_DIR / "setup.json"
PID_PATH = STATE_DIR / "pids.json"
PID_LOCK_PATH = STATE_DIR / "pids.json.lock"
INSTALL_PROGRESS_PATH = STATE_DIR / "install_progress.json"
USER_CONFIG_PATH = CONFIG_DIR / "config.json"
SECRETS_INDEX_PATH = CONFIG_DIR / "secrets_index.json"
SECRETS_FILE_PATH = CONFIG_DIR / "secrets.local.json"
KEYCHAIN_SERVICE = "spark-cli"
AUTOSTART_SERVICE_NAME = "spark-telegram-agent"
AUTOSTART_LAUNCHD_LABEL = "ai.sparkswarm.spark-telegram-agent"
AUTOSTART_WINDOWS_TASK_NAME = "Spark Telegram Agent"
REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_REGISTRY_PATH = REPO_ROOT / "registry.json"
DEFAULT_TELEGRAM_PROFILE = "default"
TELEGRAM_PROFILE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$")

try:  # keyring is an optional runtime dep; we degrade gracefully without it.
    import keyring as _keyring
    import keyring.errors as _keyring_errors
    HAS_KEYRING = True
except ImportError:  # pragma: no cover - exercised only on minimal installs
    _keyring = None
    _keyring_errors = None
    HAS_KEYRING = False


@dataclass
class Module:
    name: str
    path: Path
    manifest: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.manifest.get("module", {}).get("version", "unknown"))

    @property
    def kind(self) -> str:
        return str(self.manifest.get("module", {}).get("kind", "unknown"))

    @property
    def plane(self) -> str:
        return str(self.manifest.get("module", {}).get("plane", "unknown"))

    @property
    def capabilities(self) -> list[str]:
        return [str(item) for item in self.manifest.get("provides", {}).get("capabilities", [])]

    @property
    def needs_modules(self) -> list[str]:
        return [str(item) for item in self.manifest.get("needs", {}).get("modules", [])]

    @property
    def claims(self) -> dict[str, list[Any]]:
        return {
            "secrets": list(self.manifest.get("claims", {}).get("secrets", [])),
            "ports": list(self.manifest.get("claims", {}).get("ports", [])),
            "routes": list(self.manifest.get("claims", {}).get("routes", [])),
        }

    @property
    def run_command(self) -> str | None:
        run = self.manifest.get("run", {}).get("default", {})
        command = run.get("command")
        if not command:
            return None
        return str(command)

    @property
    def healthcheck_command(self) -> str | None:
        health = self.manifest.get("healthcheck", {})
        command = health.get("command")
        if not command:
            return None
        return str(command)

    @property
    def ready_check(self) -> str | None:
        run = self.manifest.get("run", {}).get("default", {})
        ready = run.get("ready_check")
        if not ready:
            return None
        return str(ready)

    @property
    def post_ready_watch_seconds(self) -> int | None:
        run = self.manifest.get("run", {}).get("default", {})
        configured = run.get("post_ready_watch_seconds")
        if configured is None:
            return None
        try:
            return max(0, int(configured))
        except (TypeError, ValueError):
            return None

    @property
    def install_commands(self) -> list[str]:
        commands = self.manifest.get("install", {}).get("dev", {}).get("commands", [])
        return [str(command) for command in commands]

    @property
    def telegram_profile(self) -> dict[str, Any]:
        return dict(self.manifest.get("profiles", {}).get("telegram_starter", {}))

    @property
    def needed_secrets(self) -> list[str]:
        return [str(item) for item in self.manifest.get("needs", {}).get("secrets", [])]

    def resolve_secret_definition(self, secret_id: str) -> dict[str, Any]:
        secret_blocks = self.manifest.get("secrets", {})
        candidates = [
            secret_id,
            secret_id.replace(".", "_"),
            secret_id.replace("-", "_"),
        ]
        for candidate in candidates:
            block = secret_blocks.get(candidate)
            if isinstance(block, dict):
                return dict(block)
        suffix = secret_id.split(".")[-1].replace("-", "_")
        for key, block in secret_blocks.items():
            if str(key).endswith(suffix) and isinstance(block, dict):
                return dict(block)
        return {}

    def hook_command(self, hook_name: str) -> str | None:
        hooks = self.manifest.get("hooks", {})
        command = hooks.get(hook_name)
        if not command:
            return None
        return str(command)


@dataclass
class SetupBundlePlan:
    modules: dict[str, Module]
    bundle: list[Module]
    ingress_owner: Module
    installed_modules: dict[str, Module]


def load_registry_definition() -> dict[str, Any]:
    return load_json(LOCAL_REGISTRY_PATH, {"modules": {}, "bundles": {}})


def is_git_source(source: str) -> bool:
    value = (source or "").strip()
    if not value:
        return False
    if value.startswith(("http://", "https://", "git://", "ssh://", "git@")):
        return True
    if value.endswith(".git"):
        return True
    if value.startswith("github.com/") or value.startswith("gitlab.com/"):
        return True
    return False


def normalize_git_url(source: str) -> str:
    value = source.strip()
    if value.startswith(("github.com/", "gitlab.com/")):
        return f"https://{value}"
    return value


def infer_module_name_from_url(url: str) -> str:
    cleaned = url.strip().removesuffix(".git").rstrip("/")
    last = cleaned.split("/")[-1]
    return last or "module"


def clone_target_for_module(name: str) -> Path:
    return SPARK_HOME / "modules" / name / "source"


def git_command(*args: str) -> list[str]:
    return ["git", "-c", "core.longpaths=true", *args]


def clone_module_source(name: str, source: str) -> Path:
    target = clone_target_for_module(name)
    if (target / "spark.toml").exists() and (target / ".git").exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not (target / ".git").exists():
        raise SystemExit(
            f"Cannot clone {name}: {target} exists but is not a git checkout. Remove it first."
        )
    url = normalize_git_url(source)
    result = subprocess.run(
        git_command("clone", "--depth=1", url, str(target)),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "unknown git error"
        raise SystemExit(f"git clone failed for {name}: {detail}")
    return target


def pull_module_source(path: Path) -> tuple[bool, str]:
    result = subprocess.run(
        git_command("-C", str(path), "pull", "--ff-only"),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, summarize_command_output(result)


def module_is_git_managed(module_path: Path) -> bool:
    try:
        return module_path.is_relative_to(SPARK_HOME / "modules")
    except AttributeError:  # pragma: no cover - Python <3.9 fallback
        return str(SPARK_HOME / "modules") in str(module_path)


def long_path_aware(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return f"\\\\?\\{resolved}"
    return resolved


def retry_remove_readonly(func: Any, path: str, _exc_info: Any) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    target = long_path_aware(path)
    try:
        shutil.rmtree(target, onexc=retry_remove_readonly)
    except TypeError:  # pragma: no cover - Python <3.12 fallback
        shutil.rmtree(target, onerror=retry_remove_readonly)


def remove_module_clone(name: str) -> None:
    module_home = SPARK_HOME / "modules" / name
    if not module_home.exists():
        return
    remove_tree(module_home)


def ensure_state_dirs() -> None:
    for path in (SPARK_HOME, STATE_DIR, CONFIG_DIR, MODULE_CONFIG_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def keychain_available() -> bool:
    if not HAS_KEYRING:
        return False
    try:
        _keyring.get_password(KEYCHAIN_SERVICE, "__spark_probe__")
    except Exception:
        return False
    return True


def default_spark_home() -> Path:
    return Path.home().joinpath(".spark").expanduser()


def keychain_namespace() -> str:
    try:
        raw = str(SPARK_HOME.resolve()).lower()
    except OSError:
        raw = str(SPARK_HOME.absolute()).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def keychain_account(secret_id: str) -> str:
    return f"{secret_id}@{keychain_namespace()}"


def default_home_uses_legacy_keychain() -> bool:
    try:
        return SPARK_HOME.resolve() == default_spark_home().resolve()
    except OSError:
        return SPARK_HOME.absolute() == default_spark_home().absolute()


def load_secrets_index() -> dict[str, str]:
    return load_json(SECRETS_INDEX_PATH, {})


def save_secrets_index(index: dict[str, str]) -> None:
    save_json(SECRETS_INDEX_PATH, index)


def store_secret(secret_id: str, value: str, preferred: str = "keychain") -> str:
    """Store a secret value. Returns the backend actually used ('keychain' or 'file')."""
    ensure_state_dirs()
    index = load_secrets_index()
    if preferred == "keychain" and keychain_available():
        try:
            _keyring.set_password(KEYCHAIN_SERVICE, keychain_account(secret_id), value)
            index[secret_id] = "keychain"
            save_secrets_index(index)
            return "keychain"
        except Exception:
            pass
    file_secrets = load_json(SECRETS_FILE_PATH, {})
    file_secrets[secret_id] = value
    save_json(SECRETS_FILE_PATH, file_secrets)
    try:
        os.chmod(SECRETS_FILE_PATH, 0o600)
    except OSError:
        pass
    index[secret_id] = "file"
    save_secrets_index(index)
    return "file"


def fetch_secret(secret_id: str) -> str | None:
    index = load_secrets_index()
    backend = index.get(secret_id)
    if backend == "keychain" and HAS_KEYRING:
        try:
            value = _keyring.get_password(KEYCHAIN_SERVICE, keychain_account(secret_id))
            if value is not None:
                return value
            if default_home_uses_legacy_keychain():
                return _keyring.get_password(KEYCHAIN_SERVICE, secret_id)
            return None
        except Exception:
            return None
    if backend == "file":
        return load_json(SECRETS_FILE_PATH, {}).get(secret_id)
    return None


def delete_secret(secret_id: str) -> bool:
    index = load_secrets_index()
    backend = index.pop(secret_id, None)
    removed = False
    if backend == "keychain" and HAS_KEYRING:
        try:
            _keyring.delete_password(KEYCHAIN_SERVICE, keychain_account(secret_id))
            removed = True
        except Exception:
            pass
        if default_home_uses_legacy_keychain():
            try:
                _keyring.delete_password(KEYCHAIN_SERVICE, secret_id)
                removed = True
            except Exception:
                pass
    if backend == "file":
        file_secrets = load_json(SECRETS_FILE_PATH, {})
        if secret_id in file_secrets:
            file_secrets.pop(secret_id)
            save_json(SECRETS_FILE_PATH, file_secrets)
            removed = True
    if backend is not None:
        save_secrets_index(index)
    return removed


def list_stored_secrets() -> dict[str, str]:
    return dict(load_secrets_index())


def module_secret_env_bindings(module: Module) -> list[dict[str, str]]:
    """Return env_var bindings for secrets the module declares in [needs.secrets]."""
    bindings: list[dict[str, str]] = []
    for secret_id in module.needed_secrets:
        definition = module.resolve_secret_definition(secret_id)
        env_var = definition.get("env_var")
        if not env_var:
            continue
        bindings.append(
            {
                "secret_id": str(secret_id),
                "env_var": str(env_var),
                "storage": str(definition.get("storage") or "file"),
            }
        )
    return bindings


def split_secret_bindings(module: Module) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (file_or_env_backed, keychain_backed) bindings for a module."""
    bindings = module_secret_env_bindings(module)
    keychain_backed = [b for b in bindings if b["storage"] == "keychain"]
    other_backed = [b for b in bindings if b["storage"] != "keychain"]
    return other_backed, keychain_backed


def strip_keychain_env_vars(env_values: dict[str, str], module: Module) -> dict[str, str]:
    _, keychain_backed = split_secret_bindings(module)
    keychain_env_vars = {b["env_var"] for b in keychain_backed}
    return {key: value for key, value in env_values.items() if key not in keychain_env_vars}


def keychain_env_for_module(module: Module) -> dict[str, str]:
    """Resolve keychain-backed env vars at start time, skipping any that are not stored."""
    env: dict[str, str] = {}
    _, keychain_backed = split_secret_bindings(module)
    for binding in keychain_backed:
        value = fetch_secret(binding["secret_id"])
        if value is not None:
            env[binding["env_var"]] = value
    return env


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


def load_module(path: Path) -> Module:
    manifest_path = path / "spark.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    name = str(manifest.get("module", {}).get("name") or path.name)
    return Module(name=name, path=path, manifest=manifest)


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_clipboard_text() -> str:
    commands: list[list[str]] = []
    if sys.platform == "win32":
        commands.append(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"])
    elif sys.platform == "darwin":
        commands.append(["pbpaste"])
    else:
        for candidate in ("wl-paste", "xclip", "xsel"):
            path = shutil.which(candidate)
            if not path:
                continue
            if candidate == "xclip":
                commands.append([path, "-selection", "clipboard", "-o"])
            elif candidate == "xsel":
                commands.append([path, "--clipboard", "--output"])
            else:
                commands.append([path])

    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            value = result.stdout.strip()
            if value:
                return value
    raise SystemExit(
        "Could not read a secret from the system clipboard. Copy the value first, then use `@clipboard`, "
        "use `@env:NAME`, or pass the value directly."
    )


def resolve_secret_input(value: str) -> str:
    stripped = value.strip()
    if stripped.lower() == "@clipboard":
        return read_clipboard_text()
    if stripped.lower().startswith("@env:"):
        env_name = stripped[5:].strip()
        if not env_name:
            raise SystemExit("Invalid secret reference: @env: requires an environment variable name.")
        env_value = os.environ.get(env_name)
        if not env_value:
            raise SystemExit(f"Environment variable {env_name} is not set or is empty.")
        return env_value
    return value


def parse_secret_pairs(raw_pairs: list[str] | None) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for raw in raw_pairs or []:
        if "=" not in raw:
            raise SystemExit(f"Invalid --secret value: {raw}. Expected KEY=VALUE.")
        key, value = raw.split("=", 1)
        secrets[key.strip()] = resolve_secret_input(value)
    return secrets


def collect_secret_requirements(modules: list[Module]) -> dict[str, dict[str, Any]]:
    requirements: dict[str, dict[str, Any]] = {}
    for module in modules:
        for secret_id in module.needed_secrets:
            definition = module.resolve_secret_definition(secret_id)
            requirement = requirements.setdefault(
                secret_id,
                {
                    "prompt": definition.get("prompt") or secret_id,
                    "required": bool(definition.get("required", True)),
                    "env_var": definition.get("env_var"),
                    "modules": [],
                },
            )
            requirement["modules"].append(module.name)
            if definition.get("required", False):
                requirement["required"] = True
            if definition.get("env_var") and not requirement.get("env_var"):
                requirement["env_var"] = definition.get("env_var")
    return requirements


def collect_secret_values(
    args: argparse.Namespace,
    modules: list[Module],
    *,
    interactive: bool | None = None,
) -> dict[str, str]:
    secret_values = parse_secret_pairs(getattr(args, "secret", None))
    legacy_map = {
        "telegram.bot_token": getattr(args, "bot_token", None),
        "telegram.admin_ids": getattr(args, "admin_telegram_ids", None),
        "telegram.relay_secret": getattr(args, "telegram_relay_secret", None),
        "llm.zai.api_key": getattr(args, "zai_api_key", None),
        "llm.openai.api_key": getattr(args, "openai_api_key", None),
        "llm.anthropic.api_key": getattr(args, "anthropic_api_key", None),
    }
    for key, value in legacy_map.items():
        if value:
            secret_values.setdefault(key, resolve_secret_input(str(value)))

    requirements = collect_secret_requirements(modules)
    for secret_id in requirements:
        if secret_id in secret_values:
            continue
        stored = fetch_secret(secret_id)
        if stored:
            secret_values[secret_id] = stored
            continue
        generated = fetch_generated_secret_value(requirements[secret_id])
        if generated:
            secret_values[secret_id] = generated

    if interactive is None:
        interactive = setup_is_interactive(args)
    if interactive:
        secret_values = run_setup_wizard(secret_values, requirements)

    missing = [
        secret_id
        for secret_id, requirement in requirements.items()
        if requirement.get("required") and not secret_values.get(secret_id)
    ]
    if missing:
        descriptions = []
        for secret_id in missing:
            requirement = requirements[secret_id]
            descriptions.append(f"{secret_id} ({requirement.get('prompt')})")
        raise SystemExit("Missing required secrets: " + ", ".join(descriptions))
    return secret_values


def ensure_generated_setup_secrets(secret_values: dict[str, str], modules: list[Module]) -> dict[str, str]:
    values = dict(secret_values)
    needs_relay_secret = any("telegram.relay_secret" in module.needed_secrets for module in modules)
    if needs_relay_secret and not values.get("telegram.relay_secret"):
        values["telegram.relay_secret"] = py_secrets.token_urlsafe(32)
    return values


def stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def stdout_is_tty() -> bool:
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def read_secret_interactive(prompt: str) -> str:
    """Read a secret from an interactive terminal.

    Windows users get one asterisk per typed/pasted character so they can tell
    input landed without exposing the value. Other terminals fall back to the
    standard hidden getpass prompt.
    """
    if sys.platform == "win32" and stdin_is_tty() and stdout_is_tty():
        import msvcrt

        chars: list[str] = []
        sys.stdout.write(prompt)
        sys.stdout.flush()
        while True:
            char = msvcrt.getwch()
            if char in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars)
            if char == "\x03":
                raise KeyboardInterrupt
            if char == "\x1a":
                raise EOFError
            if char in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            if char in {"\b", "\x7f"}:
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            chars.append(char)
            sys.stdout.write("*")
            sys.stdout.flush()
    return getpass.getpass(prompt)


def setup_is_interactive(args: argparse.Namespace) -> bool:
    if getattr(args, "non_interactive", False):
        return False
    return stdin_is_tty()


def detect_claude_code() -> dict[str, Any]:
    path = shutil.which("claude")
    return {"present": bool(path), "path": path}


def detect_codex_cli() -> dict[str, Any]:
    path = shutil.which("codex")
    return {"present": bool(path), "path": path}


def resolve_runtime_binary(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    if name == "python":
        current = Path(sys.executable)
        if current.exists():
            return str(current)
        return shutil.which("python3")
    return None


def detect_runtime_binary(name: str) -> dict[str, Any]:
    path = resolve_runtime_binary(name)
    if not path:
        return {"name": name, "present": False, "path": None, "version": None}
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"name": name, "present": True, "path": path, "version": None, "error": str(error)}
    output = (result.stdout + result.stderr).strip().splitlines()
    version = output[0] if result.returncode == 0 and output else None
    return {"name": name, "present": True, "path": path, "version": version}


def write_runtime_shim(path: Path, content: str, *, executable: bool = False) -> None:
    try:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            if executable and os.name != "nt":
                path.chmod(0o755)
            return
    except OSError:
        pass

    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        if executable and os.name != "nt":
            temp_path.chmod(0o755)
        os.replace(temp_path, path)
    except PermissionError:
        if path.exists():
            return
        raise
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def shell_command_env() -> dict[str, str]:
    env = os.environ.copy()
    current_python = Path(sys.executable)
    python_path = str(current_python) if current_python.exists() else resolve_runtime_binary("python")
    if not python_path:
        return env

    shim_dir = STATE_DIR / "runtime-shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        for shim_name in ("python.cmd", "python3.cmd"):
            write_runtime_shim(shim_dir / shim_name, f'@"{python_path}" %*\n')
        write_runtime_shim(shim_dir / "pip.cmd", f'@"{python_path}" -m pip %*\n')
    else:
        for shim_name in ("python", "python3"):
            write_runtime_shim(shim_dir / shim_name, f'#!/usr/bin/env sh\nexec "{python_path}" "$@"\n', executable=True)
        write_runtime_shim(shim_dir / "pip", f'#!/usr/bin/env sh\nexec "{python_path}" -m pip "$@"\n', executable=True)
    env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", "")
    return env


def parse_version_tuple(raw: str) -> tuple[int, ...] | None:
    match = re.search(r"\d+(?:\.\d+)*", raw or "")
    if not match:
        return None
    try:
        return tuple(int(part) for part in match.group(0).split("."))
    except ValueError:
        return None


def compare_version_tuples(actual: tuple[int, ...], operator: str, required: tuple[int, ...]) -> bool:
    length = max(len(actual), len(required))
    a = actual + (0,) * (length - len(actual))
    r = required + (0,) * (length - len(required))
    if operator in (">=",):
        return a >= r
    if operator == ">":
        return a > r
    if operator in ("==", "="):
        return a == r
    if operator == "<":
        return a < r
    if operator == "<=":
        return a <= r
    return False


def parse_version_constraint(constraint: str) -> list[tuple[str, tuple[int, ...]]]:
    clauses: list[tuple[str, tuple[int, ...]]] = []
    for chunk in (constraint or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.match(r"^(>=|<=|==|=|>|<)?\s*(.+)$", chunk)
        if not match:
            continue
        operator = match.group(1) or ">="
        version_tuple = parse_version_tuple(match.group(2))
        if version_tuple is not None:
            clauses.append((operator, version_tuple))
    return clauses


def runtime_version_satisfies(detected_version: str, constraint: str) -> tuple[bool, str]:
    actual = parse_version_tuple(detected_version or "")
    if actual is None:
        return True, f"could not parse `{detected_version}`; skipping constraint check"
    clauses = parse_version_constraint(constraint or "")
    if not clauses:
        return True, "no parseable constraint"
    actual_str = ".".join(str(n) for n in actual)
    for operator, required in clauses:
        if not compare_version_tuples(actual, operator, required):
            req_str = ".".join(str(n) for n in required)
            return False, f"{actual_str} does not satisfy {operator}{req_str}"
    return True, f"{actual_str} satisfies {constraint}"


def check_runtime_version_for_module(module: Module) -> tuple[bool, str]:
    runtime = module.manifest.get("runtime", {})
    kind = runtime.get("kind")
    constraint = runtime.get("version")
    if not kind or not constraint:
        return True, ""
    info = detect_runtime_binary(str(kind))
    if not info["present"]:
        return False, f"{module.name} needs {kind} {constraint} but {kind} is not on PATH"
    detected = info.get("version") or ""
    ok, detail = runtime_version_satisfies(detected, str(constraint))
    if ok:
        return True, f"{module.name}: {kind} {constraint} satisfied ({detail})"
    return False, f"{module.name}: {kind} {constraint} not satisfied -- {detail}"


def enforce_runtime_versions(modules: list[Module]) -> None:
    problems: list[str] = []
    for module in modules:
        ok, detail = check_runtime_version_for_module(module)
        if not ok and detail:
            problems.append(detail)
    if problems:
        raise SystemExit("Runtime version requirements not met:\n  - " + "\n  - ".join(problems))


def manifest_schema_version(module: Module) -> int:
    raw = module.manifest.get("schema", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def validate_manifest_schema(module: Module) -> None:
    version = manifest_schema_version(module)
    if version > CLI_MAX_SUPPORTED_SCHEMA:
        raise SystemExit(
            f"{module.name} declares manifest schema {version}; this spark-cli only supports "
            f"schema {CLI_MAX_SUPPORTED_SCHEMA}. Upgrade spark-cli."
        )


def required_runtimes_for_modules(modules: list[Module]) -> list[str]:
    seen: list[str] = []
    for module in modules:
        runtime = module.manifest.get("runtime", {})
        for key in ("package_manager", "kind"):
            candidate = runtime.get(key)
            if not candidate:
                continue
            name = str(candidate)
            if name not in seen:
                seen.append(name)
    return seen


def print_setup_preflight(bundle: list[Module]) -> None:
    print("")
    print("Spark setup preflight:")
    cc = detect_claude_code()
    if cc["present"]:
        print(f"  [OK]   claude (Claude Code) detected at {cc['path']}")
    else:
        print("  [miss] claude (Claude Code) not on PATH -- install for Claude subscription/OAuth-style calls")
    codex = detect_codex_cli()
    if codex["present"]:
        print(f"  [OK]   codex (OpenAI/Codex CLI) detected at {codex['path']}")
    else:
        print("  [miss] codex not on PATH -- install/sign in for OpenAI ChatGPT/Codex OAuth-style calls")
    for runtime_name in required_runtimes_for_modules(bundle):
        info = detect_runtime_binary(runtime_name)
        if info["present"]:
            version = info.get("version") or "version unknown"
            print(f"  [OK]   {runtime_name} -> {version}")
        else:
            print(f"  [miss] {runtime_name} not on PATH -- install before running setup")
    constraint_lines = []
    for module in bundle:
        ok, detail = check_runtime_version_for_module(module)
        if not detail:
            continue
        marker = "[OK]  " if ok else "[WARN]"
        constraint_lines.append(f"  {marker} {detail}")
    if constraint_lines:
        print("")
        print("Module runtime constraints:")
        for line in constraint_lines:
            print(line)


def prompt_for_secret(secret_id: str, requirement: dict[str, Any]) -> str:
    required = bool(requirement.get("required"))
    prompt_text = str(requirement.get("prompt") or secret_id)
    suffix = "" if required else " (press enter to skip)"
    if secret_id == "telegram.admin_ids":
        while True:
            try:
                value = input(f"  {prompt_text}{suffix}: ").strip()
            except EOFError:
                return ""
            if value:
                return value
            if not required:
                return ""
            print(f"  {secret_id} is required. Enter your numeric Telegram ID or cancel with Ctrl-C.")
    while True:
        try:
            value = read_secret_interactive(
                f"  {prompt_text}{suffix} (typing is masked; type @clipboard to use copied value): "
            )
        except EOFError:
            return ""
        if value:
            return resolve_secret_input(value)
        if not required:
            return ""
        print(f"  {secret_id} is required. Paste a value or cancel with Ctrl-C.")


def fetch_generated_secret_value(requirement: dict[str, Any]) -> str | None:
    env_var = requirement.get("env_var")
    if not env_var:
        return None
    for module_name in requirement.get("modules", []):
        values = read_generated_env(MODULE_CONFIG_DIR / f"{module_name}.env")
        value = values.get(str(env_var))
        if value:
            return value
    return None


def run_setup_wizard(
    existing_values: dict[str, str],
    requirements: dict[str, dict[str, Any]],
) -> dict[str, str]:
    collected = dict(existing_values)
    to_prompt = [
        secret_id
        for secret_id, requirement in requirements.items()
        if secret_id not in collected and requirement.get("required")
    ]
    if not to_prompt:
        return collected
    print("")
    print("Spark setup wizard -- first, enter the required Telegram setup values.")
    print("  Secrets are masked with stars on Windows and hidden on other terminals.")
    print("  Telegram admin IDs are shown so comma-separated IDs are easy to verify.")
    for secret_id in to_prompt:
        value = prompt_for_secret(secret_id, requirements[secret_id])
        if value:
            collected[secret_id] = value
    return collected


def normalize_telegram_profile(profile: str | None) -> str:
    normalized = (profile or DEFAULT_TELEGRAM_PROFILE).strip().lower()
    if normalized in {"", DEFAULT_TELEGRAM_PROFILE}:
        return DEFAULT_TELEGRAM_PROFILE
    if not TELEGRAM_PROFILE_PATTERN.match(normalized):
        raise SystemExit(
            "Invalid Telegram profile name. Use 2-40 lowercase letters, numbers, and dashes; "
            "start with a letter and end with a letter or number."
        )
    return normalized


def telegram_profile_is_default(profile: str | None) -> bool:
    return normalize_telegram_profile(profile) == DEFAULT_TELEGRAM_PROFILE


def module_process_key(module_name: str, profile: str | None = None) -> str:
    normalized = normalize_telegram_profile(profile)
    if module_name == "spark-telegram-bot" and normalized != DEFAULT_TELEGRAM_PROFILE:
        return f"{module_name}:{normalized}"
    return module_name


def generated_module_env_path(module: Module, profile: str | None = None) -> Path:
    normalized = normalize_telegram_profile(profile)
    if module.name == "spark-telegram-bot" and normalized != DEFAULT_TELEGRAM_PROFILE:
        return MODULE_CONFIG_DIR / f"{module.name}.{normalized}.env"
    return MODULE_CONFIG_DIR / f"{module.name}.env"


def telegram_profile_secret_id(profile: str, secret_name: str) -> str:
    normalized = normalize_telegram_profile(profile)
    return f"telegram.profiles.{normalized}.{secret_name}"


def keychain_env_for_telegram_profile(profile: str | None) -> dict[str, str]:
    normalized = normalize_telegram_profile(profile)
    if normalized == DEFAULT_TELEGRAM_PROFILE:
        return {}
    env: dict[str, str] = {}
    bot_token = fetch_secret(telegram_profile_secret_id(normalized, "bot_token"))
    relay_secret = fetch_secret(telegram_profile_secret_id(normalized, "relay_secret"))
    if bot_token:
        env["BOT_TOKEN"] = bot_token
    if relay_secret:
        env["TELEGRAM_RELAY_SECRET"] = relay_secret
    return env


def spark_builder_home() -> Path:
    return STATE_DIR / "spark-intelligence"


def write_generated_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_generated_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value
    return values


def module_runtime_env(module: Module, profile: str | None = None) -> dict[str, str]:
    env = shell_command_env()
    env.update(read_generated_env(generated_module_env_path(module)))
    if module.name == "spark-telegram-bot" and not telegram_profile_is_default(profile):
        env.update(read_generated_env(generated_module_env_path(module, profile)))
    env.update(keychain_env_for_module(module))
    if module.name == "spark-telegram-bot":
        env.update(keychain_env_for_telegram_profile(profile))
    return env


LLM_PROVIDER_ENV: dict[str, dict[str, str]] = {
    "zai": {
        "api_key_secret": "llm.zai.api_key",
        "api_key_env": "ZAI_API_KEY",
        "base_url_arg": "zai_base_url",
        "base_url_env": "ZAI_BASE_URL",
        "base_url_default": "https://api.z.ai/api/coding/paas/v4/",
        "model_arg": "zai_model",
        "model_env": "ZAI_MODEL",
        "model_default": "glm-5.1",
        "bot_provider": "zai",
    },
    "openai": {
        "api_key_secret": "llm.openai.api_key",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_arg": "openai_base_url",
        "base_url_env": "OPENAI_BASE_URL",
        "base_url_default": "https://api.openai.com/v1",
        "model_arg": "openai_model",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-5.5",
        "bot_provider": "codex",
    },
    "anthropic": {
        "api_key_secret": "llm.anthropic.api_key",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_arg": "anthropic_base_url",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "base_url_default": "https://api.anthropic.com",
        "model_arg": "anthropic_model",
        "model_env": "ANTHROPIC_MODEL",
        "model_default": "claude-sonnet-4.5",
        "bot_provider": "claude",
    },
    "ollama": {
        "base_url_arg": "ollama_url",
        "base_url_env": "OLLAMA_URL",
        "base_url_default": "http://localhost:11434",
        "model_arg": "ollama_model",
        "model_env": "OLLAMA_MODEL",
        "model_default": "kimi-k2.5:cloud",
        "bot_provider": "ollama",
    },
    "codex": {
        "model_arg": "codex_model",
        "model_env": "CODEX_MODEL",
        "model_default": "gpt-5.5",
        "bot_provider": "codex",
    },
    "not_configured": {
        "model_arg": "not_configured_model",
        "model_env": "SPARK_UNCONFIGURED_LLM_MODEL",
        "model_default": "",
        "bot_provider": "none",
    },
}

LLM_PROVIDER_CHOICES = sorted(provider for provider in LLM_PROVIDER_ENV if provider != "not_configured")
LLM_ROLES = ("chat", "builder", "memory", "mission")
LLM_PROVIDER_WIZARD_ORDER = ("openai", "codex", "anthropic", "zai", "ollama")
LLM_ROLE_LABELS = {
    "chat": "Telegram chat replies",
    "builder": "Builder reasoning",
    "memory": "memory synthesis and recall",
    "mission": "Spawner missions and coding work",
}
LLM_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "codex": "Codex CLI / ChatGPT sign-in",
    "anthropic": "Anthropic / Claude",
    "zai": "Z.AI / GLM coding endpoint",
    "ollama": "Ollama local",
}
LLM_PROVIDER_AUTH_HINTS = {
    "openai": "signed-in Codex CLI or OPENAI_API_KEY",
    "codex": "signed-in Codex CLI",
    "anthropic": "Claude Code sign-in or ANTHROPIC_API_KEY",
    "zai": "ZAI_API_KEY",
    "ollama": "local Ollama server",
}


def describe_llm_provider_setup(provider: str) -> str:
    spec = LLM_PROVIDER_ENV[provider]
    auth_hint = LLM_PROVIDER_AUTH_HINTS[provider]
    status = ""
    if provider == "openai":
        status = "ChatGPT/Codex sign-in detected" if detect_codex_cli()["present"] else "use OPENAI_API_KEY or run `codex` to sign in"
    elif provider == "codex":
        status = "Codex CLI detected" if detect_codex_cli()["present"] else "run `codex` to sign in first"
    elif provider == "anthropic":
        status = "Claude Code detected" if detect_claude_code()["present"] else "use ANTHROPIC_API_KEY or run `claude` to sign in"
    elif provider == "ollama":
        status = "local Ollama server"
    elif provider == "zai":
        status = "uses the GLM coding endpoint API key"
    return f"{LLM_PROVIDER_LABELS[provider]} ({spec['model_default']}; {auth_hint}; {status})"


def setup_has_llm_provider_selection(args: argparse.Namespace) -> bool:
    if getattr(args, "llm_provider", None):
        return True
    return any(getattr(args, f"{role}_llm_provider", None) for role in LLM_ROLES)


def provider_requires_wizard_api_key(provider: str) -> bool:
    if provider == "zai":
        return True
    if provider == "openai":
        return not detect_codex_cli()["present"]
    if provider == "anthropic":
        return not detect_claude_code()["present"]
    return False


def prompt_for_provider_choice(prompt: str, default: str) -> str | None:
    provider_by_number = {str(index): provider for index, provider in enumerate(LLM_PROVIDER_WIZARD_ORDER, start=1)}
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return None
    if not answer:
        answer = default
    if answer in {"0", "skip", "none", "not_configured"}:
        return "not_configured"
    provider = provider_by_number.get(answer, answer)
    if provider not in LLM_PROVIDER_CHOICES:
        print(f"  Unknown provider `{answer}`.")
        return None
    return provider


def selected_llm_providers(args: argparse.Namespace, secret_values: dict[str, str]) -> list[str]:
    providers: list[str] = []
    default_provider = resolve_llm_provider(args, secret_values)
    if default_provider != "not_configured":
        providers.append(default_provider)
    for role in LLM_ROLES:
        provider = getattr(args, f"{role}_llm_provider", None)
        if provider and provider not in providers:
            providers.append(str(provider))
    return providers


def collect_provider_api_keys(providers: list[str], secret_values: dict[str, str]) -> dict[str, str]:
    updated = dict(secret_values)
    for provider in providers:
        if provider == "not_configured":
            continue
        spec = LLM_PROVIDER_ENV[provider]
        secret_id = spec.get("api_key_secret")
        if not secret_id or updated.get(secret_id) or not provider_requires_wizard_api_key(provider):
            continue
        label = LLM_PROVIDER_LABELS.get(provider, provider)
        hint = LLM_PROVIDER_AUTH_HINTS.get(provider, "API key")
        print(f"")
        print(f"{label} needs {hint} for this setup.")
        if provider == "zai":
            print(f"  Endpoint: {spec['base_url_default']}")
            print(f"  Model: {spec['model_default']} (override with --zai-model if needed)")
        value = prompt_for_secret(
            str(secret_id),
            {
                "prompt": f"{label} API key",
                "required": True,
            },
        )
        if value:
            updated[str(secret_id)] = value
    return updated


def run_llm_provider_wizard(args: argparse.Namespace, secret_values: dict[str, str]) -> dict[str, str]:
    if setup_has_llm_provider_selection(args):
        return collect_provider_api_keys(selected_llm_providers(args, secret_values), secret_values)
    if resolve_llm_provider(args, secret_values) != "not_configured":
        return collect_provider_api_keys(selected_llm_providers(args, secret_values), secret_values)
    print("")
    print("Choose Spark LLM provider")
    print("  Pick the provider Spark should use for normal chat, Builder, and memory.")
    print("  Missions can use a local executor like Codex or Claude when available.")
    print("  Press Enter for the recommended OpenAI/Codex path, or type a number/provider name.")
    for index, provider in enumerate(LLM_PROVIDER_WIZARD_ORDER, start=1):
        suffix = " [recommended]" if provider == "openai" else ""
        print(f"  {index}. {describe_llm_provider_setup(provider)}{suffix}")
    print("  0. Skip for now")
    provider = prompt_for_provider_choice("Provider [1/OpenAI, 0 to skip]: ", "openai")
    if provider is None:
        return secret_values
    if provider == "not_configured":
        return secret_values
    setattr(args, "llm_provider", provider)

    try:
        print("")
        print("Role setup")
        print("  1. Recommended: use this provider for chat/Builder/memory, and a local executor for missions when available.")
        print("  2. Use one provider for every role.")
        print("  3. Customize chat, Builder, memory, and mission providers.")
        split_roles = input("Role setup [1]: ").strip().lower()
    except EOFError:
        split_roles = ""
    if split_roles in {"2", "same", "one", "all"}:
        for role in LLM_ROLES:
            setattr(args, f"{role}_llm_provider", provider)
    elif split_roles in {"3", "custom", "customize", "customise", "y", "yes"}:
        for role in LLM_ROLES:
            label = LLM_ROLE_LABELS[role]
            chosen = prompt_for_provider_choice(f"  {label} provider [{provider}]: ", provider)
            if chosen and chosen != "not_configured":
                setattr(args, f"{role}_llm_provider", chosen)

    roles = resolve_llm_roles(args, secret_values)
    print("")
    print("Spark LLM roles selected:")
    for role in LLM_ROLES:
        role_provider = roles[role]
        print(f"  {role}: {LLM_PROVIDER_LABELS.get(role_provider, role_provider)}")
    return collect_provider_api_keys(selected_llm_providers(args, secret_values), secret_values)


def resolve_llm_provider(args: argparse.Namespace, secret_values: dict[str, str]) -> str:
    requested = getattr(args, "llm_provider", None)
    if requested:
        return str(requested)
    for provider, spec in LLM_PROVIDER_ENV.items():
        secret_id = spec.get("api_key_secret")
        if secret_id and secret_values.get(secret_id):
            return provider
    return "not_configured"


def default_mission_llm_provider(default_provider: str) -> str:
    """Prefer a local executor for missions when the default LLM is chat-only."""
    if default_provider in {"codex", "openai", "anthropic", "not_configured"}:
        return default_provider
    if detect_codex_cli()["present"]:
        return "codex"
    if detect_claude_code()["present"]:
        return "anthropic"
    return default_provider


def resolve_llm_roles(args: argparse.Namespace, secret_values: dict[str, str]) -> dict[str, str]:
    default_provider = resolve_llm_provider(args, secret_values)
    roles: dict[str, str] = {}
    for role in LLM_ROLES:
        explicit = getattr(args, f"{role}_llm_provider", None)
        if explicit:
            roles[role] = str(explicit)
        elif role == "mission":
            roles[role] = default_mission_llm_provider(default_provider)
        else:
            roles[role] = default_provider
    return roles


def provider_auth_mode(provider: str, env: dict[str, str]) -> str:
    if provider == "not_configured":
        return "not_configured"
    spec = LLM_PROVIDER_ENV[provider]
    api_key_env = spec.get("api_key_env")
    if api_key_env and env.get(api_key_env):
        return "api_key"
    if provider == "codex" and detect_codex_cli()["present"]:
        return "codex_oauth"
    if provider == "openai" and detect_codex_cli()["present"]:
        return "codex_oauth"
    if provider == "anthropic" and detect_claude_code()["present"]:
        return "claude_oauth"
    if provider == "ollama":
        return "local"
    return "not_configured"


def build_llm_env(args: argparse.Namespace, secret_values: dict[str, str]) -> tuple[str, dict[str, str]]:
    roles = resolve_llm_roles(args, secret_values)
    provider = roles["chat"]
    spec = LLM_PROVIDER_ENV[provider]
    env: dict[str, str] = {
        "LLM_PROVIDER": provider,
        "SPARK_LLM_PROVIDER": provider,
        "BOT_DEFAULT_PROVIDER": spec["bot_provider"],
    }

    for provider_name, provider_spec in LLM_PROVIDER_ENV.items():
        api_key_secret = provider_spec.get("api_key_secret")
        api_key_env = provider_spec.get("api_key_env")
        if api_key_secret and api_key_env and secret_values.get(api_key_secret):
            env[api_key_env] = secret_values[api_key_secret]

    for provider_name in sorted(set(roles.values())):
        provider_spec = LLM_PROVIDER_ENV[provider_name]
        if provider_name == "not_configured":
            continue
        if provider_name in {"codex", "openai"}:
            codex = detect_codex_cli()
            if codex["present"]:
                env["CODEX_PATH"] = str(codex["path"])
        base_url_arg = provider_spec.get("base_url_arg")
        if base_url_arg:
            base_url = getattr(args, base_url_arg, None) or provider_spec["base_url_default"]
            env[provider_spec["base_url_env"]] = str(base_url)
        model = getattr(args, provider_spec["model_arg"], None) or provider_spec["model_default"]
        env[provider_spec["model_env"]] = str(model)

    for role, role_provider in roles.items():
        role_spec = LLM_PROVIDER_ENV[role_provider]
        role_prefix = f"SPARK_{role.upper()}_LLM"
        env[f"{role_prefix}_PROVIDER"] = role_provider
        env[f"{role_prefix}_BOT_PROVIDER"] = role_spec["bot_provider"]
        env[f"{role_prefix}_MODEL"] = env.get(role_spec["model_env"], role_spec["model_default"])
        if role_spec.get("base_url_env"):
            env[f"{role_prefix}_BASE_URL"] = env.get(role_spec["base_url_env"], role_spec["base_url_default"])
        env[f"{role_prefix}_AUTH_MODE"] = provider_auth_mode(role_provider, env)
    return provider, env


def non_secret_llm_env(llm_env: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in llm_env.items()
        if not key.endswith("_API_KEY") and key not in {"ZAI_API_KEY", "ANTHROPIC_API_KEY"}
    }


def spark_prefixed_metadata_env(llm_env: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in non_secret_llm_env(llm_env).items():
        result[key if key.startswith("SPARK_") else f"SPARK_{key}"] = value
    return result


def llm_setup_state(provider: str, env: dict[str, str]) -> dict[str, Any]:
    spec = LLM_PROVIDER_ENV[provider]
    api_key_env = spec.get("api_key_env")
    roles: dict[str, dict[str, Any]] = {}
    for role in LLM_ROLES:
        role_provider = env.get(f"SPARK_{role.upper()}_LLM_PROVIDER", provider)
        role_model = env.get(f"SPARK_{role.upper()}_LLM_MODEL", "")
        role_auth = env.get(f"SPARK_{role.upper()}_LLM_AUTH_MODE", "not_configured")
        roles[role] = {
            "provider": role_provider,
            "bot_provider": LLM_PROVIDER_ENV[str(role_provider)]["bot_provider"],
            "model": role_model,
            "auth_mode": role_auth,
        }
    return {
        "provider": provider,
        "configured": provider != "not_configured",
        "bot_default_provider": spec["bot_provider"],
        "base_url_env": spec.get("base_url_env"),
        "model_env": spec["model_env"],
        "model": env.get(spec["model_env"], ""),
        "api_key_env": api_key_env,
        "api_key_configured": bool(api_key_env and env.get(api_key_env)),
        "auth_mode": provider_auth_mode(provider, env),
        "roles": roles,
    }


def telegram_profile_webhook_urls(setup_state: dict[str, Any] | None = None) -> list[str]:
    setup = setup_state if isinstance(setup_state, dict) else load_json(CONFIG_PATH, {})
    profiles = setup.get("telegram_profiles") if isinstance(setup, dict) else None
    urls: list[str] = []
    if isinstance(profiles, dict):
        for profile_state in profiles.values():
            if not isinstance(profile_state, dict):
                continue
            webhook_url = profile_state.get("webhook_url")
            if isinstance(webhook_url, str) and webhook_url.strip():
                url = webhook_url.strip()
            else:
                try:
                    relay_port = int(profile_state.get("relay_port", 0))
                except (TypeError, ValueError):
                    continue
                if relay_port <= 0 or relay_port > 65535:
                    continue
                url = f"http://127.0.0.1:{relay_port}/spawner-events"
            if url not in urls:
                urls.append(url)
    return urls


def default_telegram_webhook_url(spawner_ui_url: str | None) -> str:
    relay_base = spawner_ui_url or "http://127.0.0.1:5173"
    if relay_base.endswith(":5173"):
        relay_base = relay_base[:-4] + "8788"
    return f"{relay_base}/spawner-events"


def build_module_envs(args: argparse.Namespace, modules_by_name: dict[str, Module], secret_values: dict[str, str]) -> dict[str, dict[str, str]]:
    gateway = modules_by_name["spark-telegram-bot"]
    spawner = modules_by_name["spawner-ui"]
    builder = modules_by_name["spark-intelligence-builder"]
    researcher = modules_by_name.get("spark-researcher")
    character = modules_by_name.get("spark-character")
    memory = modules_by_name.get("domain-chip-memory")
    builder_home = spark_builder_home()
    _, llm_env = build_llm_env(args, secret_values)
    relay_secret = secret_values.get("telegram.relay_secret") or py_secrets.token_urlsafe(32)

    gateway_env = {
        "BOT_TOKEN": secret_values.get("telegram.bot_token", ""),
        "ADMIN_TELEGRAM_IDS": secret_values.get("telegram.admin_ids", ""),
        "SPARK_BUILDER_REPO": str(builder.path),
        "SPARK_BUILDER_HOME": str(builder_home),
        "SPARK_BUILDER_PYTHON": str(Path(sys.executable)),
        "SPARK_BUILDER_BRIDGE_MODE": "required",
        "SPAWNER_UI_URL": args.spawner_ui_url or "http://127.0.0.1:5173",
        "TELEGRAM_GATEWAY_MODE": "polling",
        "TELEGRAM_RELAY_SECRET": relay_secret,
    }
    if character is not None:
        gateway_env["SPARK_CHARACTER_ROOT"] = str(character.path)
    gateway_env.update(llm_env)

    webhook_urls = telegram_profile_webhook_urls() or [default_telegram_webhook_url(args.spawner_ui_url)]
    spawner_env = {
        "MISSION_CONTROL_WEBHOOK_URLS": ",".join(webhook_urls),
        "SPARK_WORKSPACE_ROOT": str(SPARK_HOME / "workspaces"),
        "SPAWNER_STATE_DIR": str(STATE_DIR / "spawner-ui"),
    }
    llm_metadata_env = spark_prefixed_metadata_env(llm_env)
    spawner_env.update(llm_metadata_env)
    mission_provider = llm_env.get("SPARK_MISSION_LLM_BOT_PROVIDER") or llm_env.get("BOT_DEFAULT_PROVIDER")
    if mission_provider:
        spawner_env["DEFAULT_MISSION_PROVIDER"] = mission_provider
    if mission_provider == "codex":
        spawner_env["SPAWNER_PRD_AUTO_PROVIDER"] = "codex"
        if llm_env.get("CODEX_PATH"):
            spawner_env["CODEX_PATH"] = llm_env["CODEX_PATH"]
    spawner_env["TELEGRAM_RELAY_SECRET"] = relay_secret

    builder_env = {
        "SPARK_INTELLIGENCE_HOME": str(builder_home),
        **llm_metadata_env,
    }
    if researcher is not None:
        builder_env["SPARK_RESEARCHER_ROOT"] = str(researcher.path)
    if character is not None:
        builder_env["SPARK_CHARACTER_ROOT"] = str(character.path)
    if memory is not None:
        builder_env["SPARK_DOMAIN_CHIP_MEMORY_ROOT"] = str(memory.path)

    return {
        gateway.name: gateway_env,
        spawner.name: spawner_env,
        builder.name: builder_env,
    }


def split_telegram_admin_ids(raw_admin_ids: str | None) -> list[str]:
    if not raw_admin_ids:
        return []
    admin_ids: list[str] = []
    for item in raw_admin_ids.split(","):
        admin_id = item.strip()
        if admin_id and admin_id not in admin_ids:
            admin_ids.append(admin_id)
    return admin_ids


def next_telegram_profile_relay_port(setup_state: dict[str, Any]) -> int:
    used_ports = {8788}
    profiles = setup_state.get("telegram_profiles")
    if isinstance(profiles, dict):
        for profile_state in profiles.values():
            if isinstance(profile_state, dict):
                try:
                    used_ports.add(int(profile_state.get("relay_port", 0)))
                except (TypeError, ValueError):
                    pass
    port = 8789
    while port in used_ports:
        port += 1
    return port


def append_spawner_webhook_url(spawner: Module, webhook_url: str) -> None:
    generated_path = generated_module_env_path(spawner)
    generated_env = read_generated_env(generated_path)
    existing_urls = [
        item.strip()
        for item in generated_env.get("MISSION_CONTROL_WEBHOOK_URLS", "").split(",")
        if item.strip()
    ]
    if webhook_url not in existing_urls:
        existing_urls.append(webhook_url)
    generated_env["MISSION_CONTROL_WEBHOOK_URLS"] = ",".join(existing_urls)
    write_generated_env(generated_path, generated_env)
    env_path = module_env_path(spawner)
    if env_path is not None:
        update_env_file(env_path, generated_env)


def configure_telegram_profile(args: argparse.Namespace) -> int:
    profile = normalize_telegram_profile(getattr(args, "profile", None))
    installed = resolve_installed_modules()
    gateway = installed.get("spark-telegram-bot")
    spawner = installed.get("spawner-ui")
    if gateway is None or spawner is None:
        raise SystemExit("Install the telegram-starter bundle before adding Telegram profiles: spark setup")

    bot_token_arg = getattr(args, "bot_token", None)
    if bot_token_arg:
        bot_token = resolve_secret_input(str(bot_token_arg))
    else:
        bot_token = fetch_secret(telegram_profile_secret_id(profile, "bot_token"))
    if not bot_token:
        raise SystemExit(
            "Missing profile bot token. Pass --bot-token @clipboard or --bot-token @env:SPARK_TELEGRAM_BOT_TOKEN."
        )

    base_env = read_generated_env(generated_module_env_path(gateway))
    setup_state = load_json(CONFIG_PATH, {})
    relay_port = getattr(args, "telegram_relay_port", None) or next_telegram_profile_relay_port(setup_state)
    try:
        relay_port = int(relay_port)
    except (TypeError, ValueError):
        raise SystemExit("--telegram-relay-port must be a number.")
    if relay_port <= 0 or relay_port > 65535:
        raise SystemExit("--telegram-relay-port must be between 1 and 65535.")

    profile_env = dict(base_env)
    profile_env["ADMIN_TELEGRAM_IDS"] = getattr(args, "admin_telegram_ids", None) or base_env.get("ADMIN_TELEGRAM_IDS", "")
    profile_env["TELEGRAM_GATEWAY_MODE"] = "polling"
    profile_env["TELEGRAM_RELAY_PORT"] = str(relay_port)
    profile_env["SPARK_TELEGRAM_PROFILE"] = profile
    profile_env.pop("BOT_TOKEN", None)

    write_generated_env(generated_module_env_path(gateway, profile), profile_env)
    backend = store_secret(telegram_profile_secret_id(profile, "bot_token"), bot_token, preferred="keychain")

    webhook_url = f"http://127.0.0.1:{relay_port}/spawner-events"
    append_spawner_webhook_url(spawner, webhook_url)

    profiles = setup_state.setdefault("telegram_profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        setup_state["telegram_profiles"] = profiles
    profiles[profile] = {
        "module": "spark-telegram-bot",
        "env_file": str(generated_module_env_path(gateway, profile)),
        "relay_port": relay_port,
        "webhook_url": webhook_url,
        "bot_token_secret": telegram_profile_secret_id(profile, "bot_token"),
        "admin_ids_configured": bool(profile_env.get("ADMIN_TELEGRAM_IDS")),
        "configured_at": timestamp_now(),
    }
    save_json(CONFIG_PATH, setup_state)

    print(f"Telegram profile configured: {profile}")
    print(f"Profile env: {generated_module_env_path(gateway, profile)}")
    print(f"Secret {telegram_profile_secret_id(profile, 'bot_token')} -> {backend}")
    print(f"Spawner mission relay URL added: {webhook_url}")
    print("Start it with:")
    print(f"  spark start spark-telegram-bot --profile {profile}")
    print("Read its logs with:")
    print(f"  spark logs spark-telegram-bot --profile {profile}")
    return 0


def initialize_builder_runtime_home(modules_by_name: dict[str, Module], secret_values: dict[str, str] | None = None) -> list[str]:
    notes: list[str] = []
    builder = modules_by_name.get("spark-intelligence-builder")
    if builder is None:
        return notes

    builder_home = spark_builder_home()
    builder_home.mkdir(parents=True, exist_ok=True)
    notes.append(f"prepared Builder home at {builder_home}")

    builder_src = builder.path / "src"
    if not (builder_src / "spark_intelligence").exists():
        notes.append("skipped Builder runtime bootstrap because spark_intelligence source is not present")
        return notes

    inserted = False
    builder_src_value = str(builder_src)
    if builder_src_value not in sys.path:
        sys.path.insert(0, builder_src_value)
        inserted = True
    try:
        from spark_intelligence.attachments import add_attachment_root, activate_chip, sync_attachment_snapshot
        from spark_intelligence.channel.service import add_channel
        from spark_intelligence.config.loader import ConfigManager
        from spark_intelligence.state.db import StateDB

        config_manager = ConfigManager.from_home(str(builder_home))
        config_manager.bootstrap()
        state_db = StateDB(config_manager.paths.state_db)
        state_db.initialize()

        researcher = modules_by_name.get("spark-researcher")
        if researcher is not None:
            config_manager.set_path("spark.researcher.runtime_root", str(researcher.path))
            researcher_config = researcher.path / "spark-researcher.project.json"
            if researcher_config.exists():
                config_manager.set_path("spark.researcher.config_path", str(researcher_config))
            notes.append(f"connected spark-researcher at {researcher.path}")

        memory = modules_by_name.get("domain-chip-memory")
        if memory is not None:
            add_attachment_root(config_manager, target="chips", root=str(memory.path))
            config_manager.set_path("spark.memory.enabled", True)
            config_manager.set_path("spark.memory.shadow_mode", False)
            config_manager.set_path("spark.memory.sdk_module", "domain_chip_memory")
            activate_chip(config_manager, chip_key="domain-chip-memory")
            sync_attachment_snapshot(config_manager=config_manager, state_db=state_db)
            notes.append(f"activated domain-chip-memory at {memory.path}")

        setup_secrets = secret_values or {}
        telegram_bot_token = setup_secrets.get("telegram.bot_token") or None
        telegram_admin_ids = split_telegram_admin_ids(setup_secrets.get("telegram.admin_ids"))
        if telegram_bot_token or telegram_admin_ids:
            pairing_mode = "allowlist" if telegram_admin_ids else "pairing"
            add_channel(
                config_manager=config_manager,
                state_db=state_db,
                channel_kind="telegram",
                bot_token=telegram_bot_token,
                allowed_users=telegram_admin_ids,
                pairing_mode=pairing_mode,
                status="enabled",
            )
            notes.append(f"configured Builder telegram channel ({pairing_mode}, {len(telegram_admin_ids)} admin IDs)")
    except Exception as exc:  # pragma: no cover - defensive fallback for partial installs
        notes.append(f"Builder runtime bootstrap skipped: {exc}")
    finally:
        if inserted:
            try:
                sys.path.remove(builder_src_value)
            except ValueError:
                pass
    return notes


def discover_modules() -> dict[str, Module]:
    modules: dict[str, Module] = {}
    registry = load_registry_definition()
    for name, metadata in registry.get("modules", {}).items():
        source = str(metadata.get("source", ""))
        clone_path = clone_target_for_module(name)
        if (clone_path / "spark.toml").exists():
            module = load_module(clone_path)
            modules[module.name] = module
            continue
        if source and not is_git_source(source):
            path = Path(source)
            manifest_path = path / "spark.toml"
            if manifest_path.exists():
                module = load_module(path)
                modules[module.name] = module
    return modules


def resolve_bundle(bundle_name: str, modules: dict[str, Module]) -> list[Module]:
    registry = load_registry_definition()
    bundle = registry.get("bundles", {}).get(bundle_name, {})
    names = bundle.get("modules")
    if not names:
        raise SystemExit(f"Unknown bundle: {bundle_name}")
    missing = [name for name in names if name not in modules]
    if missing:
        raise SystemExit(f"Bundle {bundle_name} is missing local module manifests: {', '.join(missing)}")
    return [modules[name] for name in names]


def ensure_bundle_modules_available(names: list[str], modules: dict[str, Module]) -> dict[str, Module]:
    """Populate `modules` with any missing bundle members.

    If a registry entry has a git URL source that has not been cloned yet,
    this triggers `resolve_install_target`, which clones the source into
    `~/.spark/modules/<name>/source/` and loads the manifest from there.
    """
    augmented = dict(modules)
    for name in names:
        if name in augmented:
            continue
        module = resolve_install_target(name, augmented)
        augmented[module.name] = module
    return augmented


def resolve_bundle_names(bundle_name: str) -> list[str]:
    registry = load_registry_definition()
    bundle = registry.get("bundles", {}).get(bundle_name, {})
    names = bundle.get("modules")
    if not names:
        raise SystemExit(f"Unknown bundle: {bundle_name}")
    return [str(name) for name in names]


def expand_targets(target: str | None, modules: dict[str, Module], include_all: bool = False) -> list[str]:
    if target is None:
        return list(modules.keys()) if include_all else []
    registry = load_registry_definition()
    bundles = registry.get("bundles", {})
    if target in bundles:
        return list(bundles[target].get("modules", []))
    return [target]


def detect_ingress_owner(bundle: list[Module]) -> Module:
    owners = [module for module in bundle if "telegram.ingress" in module.capabilities]
    if len(owners) != 1:
        raise SystemExit(
            "Expected exactly one telegram ingress owner in bundle, found "
            f"{len(owners)}: {', '.join(module.name for module in owners) or 'none'}"
        )
    return owners[0]


def needs_capabilities(module: Module) -> list[str]:
    return [str(item) for item in module.manifest.get("needs", {}).get("capabilities", [])]


def capability_providers(capability: str, modules: dict[str, Module]) -> list[str]:
    return sorted(name for name, module in modules.items() if capability in module.capabilities)


def validate_capability_needs_for_install(
    candidates: list[Module],
    installed_modules: dict[str, Module],
    discoverable_modules: dict[str, Module],
) -> list[str]:
    """Check that every `needs.capabilities` entry is satisfiable.

    A capability is satisfied when any already-installed module OR any other
    module in the same install batch provides it. Returns a list of error
    lines (empty means all needs can be met).
    """
    effective: dict[str, Module] = dict(installed_modules)
    for candidate in candidates:
        effective[candidate.name] = candidate

    errors: list[str] = []
    for candidate in candidates:
        for capability in needs_capabilities(candidate):
            providers = [
                name
                for name, module in effective.items()
                if name != candidate.name and capability in module.capabilities
            ]
            if providers:
                continue
            suggestions = [
                name
                for name, module in discoverable_modules.items()
                if name != candidate.name and capability in module.capabilities
            ]
            if suggestions:
                errors.append(
                    f"{candidate.name} needs capability `{capability}`; install one of: {', '.join(sorted(suggestions))}"
                )
            else:
                errors.append(
                    f"{candidate.name} needs capability `{capability}` but no discoverable module provides it"
                )
    return errors


def detect_capability_conflicts(candidate_modules: list[Module], installed_modules: dict[str, Module]) -> list[str]:
    combined: dict[str, Module] = dict(installed_modules)
    for module in candidate_modules:
        combined[module.name] = module

    capability_owners: dict[str, set[str]] = {}
    for module in combined.values():
        for capability in module.capabilities:
            capability_owners.setdefault(capability, set()).add(module.name)

    conflicts: list[str] = []
    ingress_owners = sorted(capability_owners.get("telegram.ingress", set()))
    if len(ingress_owners) > 1:
        conflicts.append("multiple telegram ingress owners declared: " + ", ".join(ingress_owners))
    return conflicts


def module_env_path(module: Module) -> Path | None:
    config = module.manifest.get("config", {})
    output = config.get("output")
    if not output:
        return None
    return module.path / str(output)


def update_env_file(path: Path, values: dict[str, str]) -> None:
    start = "# --- spark-cli managed start ---"
    end = "# --- spark-cli managed end ---"
    lines: list[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
        inside = False
        for line in existing:
            if line.strip() == start:
                inside = True
                continue
            if line.strip() == end:
                inside = False
                continue
            if not inside:
                lines.append(line)
        while lines and not lines[-1].strip():
            lines.pop()
    if lines:
        lines.append("")
    lines.append(start)
    for key, value in values.items():
        lines.append(f"{key}={value}")
    lines.append(end)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def remove_managed_env_block(path: Path) -> None:
    start = "# --- spark-cli managed start ---"
    end = "# --- spark-cli managed end ---"
    if not path.exists():
        return
    lines: list[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == start:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if not inside:
            lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    output = "\n".join(lines).strip()
    path.write_text((output + "\n") if output else "", encoding="utf-8")


def cmd_list(_: argparse.Namespace) -> int:
    registry = load_registry_definition()
    installed = load_json(REGISTRY_PATH, {})
    modules = discover_modules()
    for module in modules.values():
        metadata = registry.get("modules", {}).get(module.name, {})
        blessed = "yes" if metadata.get("blessed") else "no"
        installed_marker = "installed" if module.name in installed else "available"
        print(
            f"{module.name}\t{module.version}\t{module.kind}\t{module.plane}\t{blessed}\t{installed_marker}\t{module.path}"
        )
    return 0


def resolve_install_target(target: str, modules: dict[str, Module]) -> Module:
    if target in modules:
        return modules[target]
    registry = load_registry_definition()
    registry_metadata = registry.get("modules", {}).get(target)
    if registry_metadata:
        source = str(registry_metadata.get("source", ""))
        if is_git_source(source):
            clone_path = clone_module_source(target, source)
            return load_module(clone_path)
        if source and Path(source).exists():
            manifest_path = Path(source) / "spark.toml"
            if manifest_path.exists():
                return load_module(Path(source))
            raise SystemExit(f"Registry entry {target} points at {source} but no spark.toml is there.")
    if is_git_source(target):
        name = infer_module_name_from_url(target)
        clone_path = clone_module_source(name, target)
        return load_module(clone_path)
    candidate = Path(target)
    if candidate.exists():
        manifest_path = candidate / "spark.toml"
        if not manifest_path.exists():
            raise SystemExit(f"{candidate} does not contain spark.toml")
        return load_module(candidate)
    raise SystemExit(f"Unknown module target: {target}")


def install_module_record(
    module: Module,
    *,
    operation: str,
    source_kind: str,
    source_target: str,
    skip_install_commands: bool,
    bundle_name: str | None = None,
) -> None:
    installed = load_json(REGISTRY_PATH, {})
    existing = dict(installed.get(module.name, {}))
    registry_metadata = load_registry_definition().get("modules", {}).get(module.name, {})
    now = timestamp_now()
    installed_via = dict(existing.get("installed_via", {}))
    if not installed_via:
        installed_via = {
            "kind": source_kind,
            "target": source_target,
        }
        if bundle_name:
            installed_via["bundle"] = bundle_name

    bundle_provenance = list(existing.get("bundle_provenance", []))
    if bundle_name and bundle_name not in bundle_provenance:
        bundle_provenance.append(bundle_name)

    installed[module.name] = {
        **existing,
        "path": str(module.path),
        "source": str(module.path),
        "version": module.version,
        "kind": module.kind,
        "plane": module.plane,
        "summary": str(registry_metadata.get("summary") or module.manifest.get("module", {}).get("description", "")),
        "blessed": bool(registry_metadata.get("blessed", False)),
        "installed_at": existing.get("installed_at") or now,
        "updated_at": now,
        "installed_via": installed_via,
        "bundle_provenance": bundle_provenance,
    }
    outcome_key = "last_install" if operation == "install" else "last_update"
    installed[module.name][outcome_key] = {
        "status": "ok",
        "at": now,
        "source_kind": source_kind,
        "source_target": source_target,
        "bundle": bundle_name,
        "skip_install_commands": skip_install_commands,
    }
    save_json(REGISTRY_PATH, installed)


def describe_installed_record(module: Module, record: dict[str, Any]) -> dict[str, Any]:
    registry_metadata = load_registry_definition().get("modules", {}).get(module.name, {})
    installed = dict(record)
    installed.setdefault("path", str(module.path))
    installed.setdefault("source", str(module.path))
    installed.setdefault("version", module.version)
    installed.setdefault("kind", module.kind)
    installed.setdefault("plane", module.plane)
    installed.setdefault("summary", str(registry_metadata.get("summary") or module.manifest.get("module", {}).get("description", "")))
    installed.setdefault("blessed", bool(registry_metadata.get("blessed", False)))
    return installed


def remove_module_record(module_name: str) -> None:
    installed = load_json(REGISTRY_PATH, {})
    installed.pop(module_name, None)
    save_json(REGISTRY_PATH, installed)


def is_blessed_registry_entry(target: str) -> bool:
    metadata = load_registry_definition().get("modules", {}).get(target)
    if not metadata:
        return False
    return bool(metadata.get("blessed"))


def describe_install_risk(module: Module) -> list[str]:
    lines: list[str] = []
    commands = module.install_commands
    if commands:
        lines.append("Install commands that will run from the module repo:")
        for command in commands:
            lines.append(f"  $ {command}")
    hooks = module.manifest.get("hooks", {})
    for hook_name in ("post_install", "pre_uninstall", "post_uninstall"):
        command = hooks.get(hook_name)
        if command:
            lines.append(f"Hook {hook_name}: {command}")
    return lines


def prompt_trust_non_blessed_install(module: Module, target: str, risk: list[str]) -> bool:
    print("")
    print(f"WARNING: {target} is not in the blessed registry.")
    print("Installing it will execute code from the module repository on this machine:")
    print("")
    for line in risk:
        print(f"  {line}")
    print("")
    try:
        answer = input("Type 'yes' to proceed: ").strip().lower()
    except EOFError:
        return False
    return answer in ("yes", "y")


def ensure_trust_for_install(args: argparse.Namespace, module: Module, target: str) -> None:
    if getattr(args, "trust", False):
        return
    if is_blessed_registry_entry(target):
        return
    risk = describe_install_risk(module)
    if not risk:
        return
    if getattr(args, "skip_install_commands", False):
        # Install commands are being skipped; uninstall hooks run later on tear-down
        # but we still surface them the first time a non-blessed module is added.
        pass
    if not stdin_is_tty() or getattr(args, "non_interactive", False):
        raise SystemExit(
            f"Refusing to install non-blessed module `{target}` non-interactively. "
            f"Pass --trust to approve running its install commands and hooks."
        )
    if not prompt_trust_non_blessed_install(module, target, risk):
        raise SystemExit(f"Install aborted: {target} was not trusted.")


def load_install_progress(target: str) -> dict[str, Any]:
    data = load_json(INSTALL_PROGRESS_PATH, {})
    entry = data.get(target) if isinstance(data, dict) else None
    return dict(entry) if isinstance(entry, dict) else {}


def save_install_progress(target: str, progress: dict[str, Any]) -> None:
    data = load_json(INSTALL_PROGRESS_PATH, {})
    if not isinstance(data, dict):
        data = {}
    data[target] = progress
    save_json(INSTALL_PROGRESS_PATH, data)


def clear_install_progress(target: str) -> None:
    data = load_json(INSTALL_PROGRESS_PATH, {})
    if not isinstance(data, dict):
        return
    if target not in data:
        return
    data.pop(target)
    if data:
        save_json(INSTALL_PROGRESS_PATH, data)
    elif INSTALL_PROGRESS_PATH.exists():
        INSTALL_PROGRESS_PATH.unlink()


def record_install_step(target: str, step: str) -> None:
    progress = load_install_progress(target)
    completed = progress.setdefault("steps_completed", [])
    if step not in completed:
        completed.append(step)
    progress["last_step"] = step
    progress["last_ok_at"] = timestamp_now()
    save_install_progress(target, progress)


def record_install_failure(target: str, step: str, error: str) -> None:
    progress = load_install_progress(target)
    progress["failed_step"] = step
    progress["last_error"] = error
    progress["failed_at"] = timestamp_now()
    save_install_progress(target, progress)


def step_previously_completed(target: str, step: str, resume: bool) -> bool:
    if not resume:
        return False
    return step in load_install_progress(target).get("steps_completed", [])


def print_install_summary(modules: list[Module]) -> None:
    print("Install plan:")
    for module in modules:
        print(f"- {module.name} ({module.kind}, {module.plane})")
    ingress_owners = [module.name for module in modules if "telegram.ingress" in module.capabilities]
    if ingress_owners:
        print(f"Telegram ingress owner: {', '.join(ingress_owners)}")


def install_modules(modules: list[Module]) -> None:
    print_install_summary(modules)
    for module in modules:
        print(f"Installed {module.name} from {module.path}")
        if "telegram.ingress" in module.capabilities:
            print("This module declares telegram.ingress and should be the only live Telegram token owner.")


def execute_install_commands(module: Module) -> None:
    for command in module.install_commands:
        print(f"Running install command for {module.name}: {command}")
        result = run_shell(command_with_managed_python(command), module.path)
        if result.returncode != 0:
            raise SystemExit(
                f"{module.name} install command failed: {summarize_command_output(result)}"
            )


def run_module_hook(module: Module, hook_name: str) -> None:
    command = module.hook_command(hook_name)
    if not command:
        return
    result = run_shell(command, module.path, env=module_runtime_env(module))
    if result.returncode != 0:
        raise SystemExit(
            f"{module.name} hook `{hook_name}` failed: {summarize_command_output(result)}"
        )


def sync_generated_env_to_module(module: Module) -> None:
    generated_path = generated_module_env_path(module)
    env_path = module_env_path(module)
    if env_path is None or not generated_path.exists():
        return
    values: dict[str, str] = {}
    for line in generated_path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    if values:
        update_env_file(env_path, values)


def update_setup_state_after_uninstall(module_names: list[str]) -> None:
    setup_state = load_json(CONFIG_PATH, {})
    if not setup_state:
        return
    remaining = [name for name in setup_state.get("modules", []) if name not in module_names]
    if not remaining:
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        return
    setup_state["modules"] = remaining
    if setup_state.get("telegram_ingress_owner") in module_names:
        setup_state["telegram_ingress_owner"] = None
    save_json(CONFIG_PATH, setup_state)


def resolve_installed_modules() -> dict[str, Module]:
    installed = load_json(REGISTRY_PATH, {})
    return {name: load_module(Path(data["path"])) for name, data in installed.items()}


def detect_uninstall_blockers(removing_modules: list[Module], installed_modules: dict[str, Module]) -> list[str]:
    removing_names = {module.name for module in removing_modules}
    blockers: list[str] = []
    for module in installed_modules.values():
        if module.name in removing_names:
            continue
        for dependency in module.needs_modules:
            if dependency in removing_names:
                blockers.append(f"{module.name} depends on {dependency}")
    return blockers


def evaluate_module_health(module: Module) -> dict[str, Any]:
    command = module.healthcheck_command
    if not command:
        return {
            "name": module.name,
            "version": module.version,
            "kind": module.kind,
            "plane": module.plane,
            "healthy": None,
            "detail": "no healthcheck declared",
            "healthcheck_command": None,
            "failure_hint": None,
        }
    timeout_seconds = ready_timeout_seconds(module)
    result = run_shell(command, module.path, env=module_runtime_env(module), timeout=timeout_seconds)
    detail = summarize_command_output(result)
    failure_hint = str(module.manifest.get("healthcheck", {}).get("failure_hint", "")).strip() or None
    success_hint = str(module.manifest.get("healthcheck", {}).get("success_hint", "")).strip() or None
    return {
        "name": module.name,
        "version": module.version,
        "kind": module.kind,
        "plane": module.plane,
        "healthy": result.returncode == 0,
        "detail": detail,
        "healthcheck_command": command,
        "failure_hint": failure_hint,
        "success_hint": success_hint,
    }


def determine_install_source_kind(target: str, modules: dict[str, Module]) -> str:
    registry = load_registry_definition()
    registry_metadata = registry.get("modules", {}).get(target)
    if registry_metadata:
        source = str(registry_metadata.get("source", ""))
        if is_git_source(source):
            return "registry_git"
        return "registry"
    if is_git_source(target):
        return "git_url"
    if Path(target).exists():
        return "local_path"
    if target in modules:
        return "discovered"
    return "unknown"


def dependency_issues_for_module(module: Module, module_results: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    missing_dependencies: list[str] = []
    unhealthy_dependencies: list[str] = []
    for dependency in module.needs_modules:
        dependency_result = module_results.get(dependency)
        if dependency_result is None:
            missing_dependencies.append(dependency)
            continue
        if dependency_result.get("healthy") is False:
            unhealthy_dependencies.append(dependency)
    return missing_dependencies, unhealthy_dependencies


def build_module_repair_hints(
    module: Module,
    result: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    setup_state: dict[str, Any],
) -> list[str]:
    hints: list[str] = []
    runtime_ok, runtime_detail = check_runtime_version_for_module(module)
    if not runtime_ok and runtime_detail:
        hints.append(f"Repair runtime first: {runtime_detail}. If you used install.sh, run Spark through the installed wrapper at `{SPARK_HOME / 'bin' / ('spark.cmd' if os.name == 'nt' else 'spark')}` so managed Node/Python are on PATH.")
    missing_dependencies, unhealthy_dependencies = dependency_issues_for_module(module, module_results)
    if missing_dependencies:
        hints.append(
            "Install missing dependencies first: " + ", ".join(missing_dependencies) + "."
        )
    if unhealthy_dependencies:
        hints.append(
            "Repair dependency health first: " + ", ".join(unhealthy_dependencies) + "."
        )
    if result.get("healthy") is False and result.get("failure_hint"):
        hints.append(str(result["failure_hint"]))
    if module.manifest.get("config", {}).get("installer_owned"):
        generated_path = generated_module_env_path(module)
        env_path = module_env_path(module)
        if env_path is not None and not generated_path.exists():
            bundle_name = setup_state.get("bundle") or "telegram-starter"
            hints.append(f"Run `spark setup {bundle_name}` to regenerate installer-owned config.")
    deduped: list[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped


def build_status_repair_hints(
    modules: dict[str, Module],
    module_results: list[dict[str, Any]],
    setup_state: dict[str, Any],
    tracked_pids: dict[str, Any] | None = None,
) -> list[str]:
    hints: list[str] = []
    bundle_name = setup_state.get("bundle")
    installed_names = set(modules)
    if bundle_name:
        expected_modules: set[str] | None = None
        try:
            expected_modules = set(resolve_bundle_names(str(bundle_name)))
        except SystemExit:
            hints.append(
                f"Configured bundle `{bundle_name}` is not present in the local registry. Run `spark setup telegram-starter`."
            )
        if expected_modules is not None:
            missing_modules = sorted(expected_modules - installed_names)
            if missing_modules:
                hints.append(
                    f"Setup bundle `{bundle_name}` is incomplete. Reinstall missing modules: {', '.join(missing_modules)}."
                )
    ingress_owner = setup_state.get("telegram_ingress_owner")
    if ingress_owner and ingress_owner not in installed_names:
        hints.append(
            f"Configured Telegram ingress owner `{ingress_owner}` is not installed. Run `spark setup {bundle_name or 'telegram-starter'}`."
        )
    llm_state = setup_state.get("llm")
    if not isinstance(llm_state, dict) or not llm_state.get("provider") or llm_state.get("provider") == "not_configured":
        hints.append(
            "No LLM provider is configured. Run `spark setup` to choose chat, builder, memory, and mission providers."
        )
    if isinstance(llm_state, dict):
        setup_secret_keys = set(setup_state.get("secret_keys", []))
        hints.extend(build_llm_repair_hints(llm_state, secret_keys=setup_secret_keys))
    if bundle_name:
        expected_runtime_names = expected_runtime_process_names(installed_names, setup_state)
        if expected_runtime_names:
            process_ok, process_detail = process_runtime_detail(tracked_pids or {}, expected_runtime_names)
            if not process_ok:
                hints.append(f"{process_detail} Run `spark start {bundle_name}`.")
    module_results_by_name = {item["name"]: item for item in module_results}
    for module in modules.values():
        missing_dependencies, unhealthy_dependencies = dependency_issues_for_module(module, module_results_by_name)
        if missing_dependencies:
            hints.append(
                f"{module.name} is missing dependencies: {', '.join(missing_dependencies)}."
            )
        if unhealthy_dependencies:
            hints.append(
                f"{module.name} is blocked on unhealthy dependencies: {', '.join(unhealthy_dependencies)}."
            )
    deduped: list[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped


def build_llm_repair_hints(llm_state: dict[str, Any], *, secret_keys: set[str] | None = None) -> list[str]:
    hints: list[str] = []
    stored_secret_keys = secret_keys or set()
    roles = llm_state.get("roles")
    if isinstance(roles, dict):
        role_items = [(role, roles.get(role, {})) for role in LLM_ROLES]
    else:
        role_items = [("all", llm_state)]
    for role, state in role_items:
        if not isinstance(state, dict):
            continue
        provider = str(state.get("provider") or llm_state.get("provider") or "not_configured")
        auth_mode = str(state.get("auth_mode") or llm_state.get("auth_mode") or "not_configured")
        provider_spec = LLM_PROVIDER_ENV.get(provider, {})
        api_key_secret = provider_spec.get("api_key_secret")
        if auth_mode == "not_configured":
            if bool(state.get("api_key_configured") or llm_state.get("api_key_configured")):
                auth_mode = "api_key"
            elif api_key_secret and api_key_secret in stored_secret_keys:
                auth_mode = "api_key"
            elif provider in {"codex", "openai"} and detect_codex_cli()["present"]:
                auth_mode = "codex_oauth"
            elif provider == "anthropic" and detect_claude_code()["present"]:
                auth_mode = "claude_oauth"
            elif provider == "ollama":
                auth_mode = "local"
        role_label = "LLM provider" if role == "all" else f"LLM role `{role}`"
        role_flag = "--llm-provider" if role == "all" else f"--{role}-llm-provider"
        if provider == "not_configured":
            hints.append(
                f"{role_label} is not configured. Run `spark setup {role_flag} openai` to use Codex/OpenAI, or choose anthropic, zai, ollama, or codex."
            )
        elif provider == "zai" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses Z.AI but is missing an API key. Re-run `spark setup {role_flag} zai --zai-api-key <key>`."
            )
        elif provider == "anthropic" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses Anthropic but neither Claude Code nor ANTHROPIC_API_KEY is configured. Run `claude` to sign in, or rerun `spark setup {role_flag} anthropic --anthropic-api-key <key>`."
            )
        elif provider == "openai" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses OpenAI but neither Codex CLI OAuth nor OPENAI_API_KEY is configured. Run `codex` to sign in with ChatGPT, or rerun `spark setup {role_flag} openai --openai-api-key <key>`."
            )
        elif provider == "codex" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses Codex but the Codex CLI is not signed in or not on PATH. Run `codex` first, then rerun `spark setup {role_flag} codex`."
            )
    return hints


def cmd_install(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = discover_modules()
    installed_modules = resolve_installed_modules()
    registry = load_registry_definition()
    resume = getattr(args, "resume", False)
    if args.target in registry.get("bundles", {}):
        bundle_names = resolve_bundle_names(args.target)
        modules = ensure_bundle_modules_available(bundle_names, modules)
        bundle_modules = [modules[name] for name in bundle_names]
        detect_ingress_owner(bundle_modules)
        for module in bundle_modules:
            validate_manifest_schema(module)
        conflicts = detect_capability_conflicts(bundle_modules, installed_modules)
        if conflicts:
            raise SystemExit("Cannot install bundle because of capability conflicts: " + "; ".join(conflicts))
        unmet = validate_capability_needs_for_install(bundle_modules, installed_modules, modules)
        if unmet:
            raise SystemExit("Cannot install bundle because of unmet capability needs:\n  - " + "\n  - ".join(unmet))
        if not getattr(args, "skip_runtime_check", False):
            enforce_runtime_versions(bundle_modules)
        for module in bundle_modules:
            ensure_trust_for_install(args, module, module.name)
            run_install_commands_with_progress(module, module.name, args, resume)
        install_modules(bundle_modules)
        for module in bundle_modules:
            install_module_record(
                module,
                operation="install",
                source_kind="bundle",
                source_target=args.target,
                bundle_name=args.target,
                skip_install_commands=args.skip_install_commands,
            )
            clear_install_progress(module.name)
        return 0
    module = resolve_install_target(args.target, modules)
    validate_manifest_schema(module)
    source_kind = determine_install_source_kind(args.target, modules)
    conflicts = detect_capability_conflicts([module], installed_modules)
    if conflicts:
        raise SystemExit("Cannot install module because of capability conflicts: " + "; ".join(conflicts))
    unmet = validate_capability_needs_for_install([module], installed_modules, modules)
    if unmet:
        raise SystemExit("Cannot install module because of unmet capability needs:\n  - " + "\n  - ".join(unmet))
    if not getattr(args, "skip_runtime_check", False):
        enforce_runtime_versions([module])
    ensure_trust_for_install(args, module, args.target)
    run_install_commands_with_progress(module, args.target, args, resume)
    install_modules([module])
    install_module_record(
        module,
        operation="install",
        source_kind=source_kind,
        source_target=args.target,
        skip_install_commands=args.skip_install_commands,
    )
    clear_install_progress(args.target)
    return 0


def run_install_commands_with_progress(
    module: Module,
    progress_key: str,
    args: argparse.Namespace,
    resume: bool,
) -> None:
    """Run [install.dev].commands with progress tracking so --resume can skip them."""
    if args.skip_install_commands:
        return
    if step_previously_completed(progress_key, "install_commands", resume):
        print(f"--resume: skipping install commands for {module.name} (already completed).")
        return
    try:
        execute_install_commands(module)
    except SystemExit as error:
        record_install_failure(progress_key, "install_commands", str(error))
        raise
    record_install_step(progress_key, "install_commands")


def setup_should_run_install_commands(
    module: Module,
    installed_modules: dict[str, Module],
    args: argparse.Namespace,
) -> bool:
    """Return whether setup should run dependency install commands for this module."""
    if getattr(args, "skip_install_commands", False):
        return False
    if getattr(args, "run_install_commands", False):
        return True
    return module.name not in installed_modules


def print_setup_next_steps(bundle_name: str, ingress_owner: Module, llm_state: dict[str, Any]) -> None:
    provider = llm_state.get("provider") or "unknown"
    model = llm_state.get("model") or "not configured"
    roles = llm_state.get("roles") if isinstance(llm_state.get("roles"), dict) else {}
    print("")
    print("Spark is installed. Next steps:")
    print("  1. Verify the install:")
    print("     spark status")
    print("  2. Make Spark start when this computer logs in:")
    print("     spark autostart install --now")
    print("  3. Manual start fallback:")
    print("     spark start telegram-starter")
    print("  4. Open your Telegram bot and send:")
    print("     /start")
    print("     /myid")
    print("     /diagnose")
    print("  5. Send a normal message and confirm the LLM responds.")
    print("")
    if provider == "not_configured":
        print("LLM provider: not configured yet")
    else:
        print(f"LLM provider: {provider} ({model})")
    if roles:
        print("LLM roles:")
        for role in LLM_ROLES:
            role_state = roles.get(role, {})
            print(
                f"  - {role}: {role_state.get('provider', provider)} "
                f"({role_state.get('model', model)}, auth={role_state.get('auth_mode', llm_state.get('auth_mode', 'unknown'))})"
            )
    print("Need a bot token? Open @BotFather in Telegram, run /newbot, then rerun:")
    print(f"     spark setup {bundle_name}")
    print("Need to choose or change LLMs? Run `spark setup` for the guided picker, or use role flags for automation.")
    print("OpenAI can use a signed-in Codex/ChatGPT session (`codex`) or OPENAI_API_KEY; Anthropic can use Claude Code (`claude`) or ANTHROPIC_API_KEY.")
    print("For role-level control, use --chat-llm-provider, --builder-llm-provider, --memory-llm-provider, and --mission-llm-provider.")
    print("Need to turn the agent off? Run `spark stop telegram-starter` or `spark autostart uninstall`.")
    print("Run `spark guide` anytime for BotFather, LLM, module, and Telegram command help.")


def resolve_setup_bundle_plan(args: argparse.Namespace) -> SetupBundlePlan:
    modules = discover_modules()
    modules = ensure_bundle_modules_available(resolve_bundle_names(args.bundle), modules)
    bundle = resolve_bundle(args.bundle, modules)
    ingress_owner = detect_ingress_owner(bundle)
    installed_modules = resolve_installed_modules()
    for module in bundle:
        validate_manifest_schema(module)
    conflicts = detect_capability_conflicts(bundle, installed_modules)
    if conflicts:
        raise SystemExit("Cannot run setup because of capability conflicts: " + "; ".join(conflicts))
    unmet = validate_capability_needs_for_install(bundle, installed_modules, modules)
    if unmet:
        raise SystemExit("Cannot run setup because of unmet capability needs:\n  - " + "\n  - ".join(unmet))
    if not getattr(args, "skip_runtime_check", False):
        enforce_runtime_versions(bundle)
    return SetupBundlePlan(
        modules=modules,
        bundle=bundle,
        ingress_owner=ingress_owner,
        installed_modules=installed_modules,
    )


def collect_setup_configuration(
    args: argparse.Namespace,
    bundle: list[Module],
    ingress_owner: Module,
    interactive: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Collect secrets and LLM choices, then build the persisted setup state."""
    existing_setup = load_json(CONFIG_PATH, {})
    secret_values = collect_secret_values(args, bundle, interactive=interactive)
    secret_values = ensure_generated_setup_secrets(secret_values, bundle)
    if interactive:
        secret_values = run_llm_provider_wizard(args, secret_values)
    llm_provider, llm_env = build_llm_env(args, secret_values)
    preserved_secret_keys = set(existing_setup.get("secret_keys", [])) if isinstance(existing_setup, dict) else set()
    preserved_profiles = existing_setup.get("telegram_profiles") if isinstance(existing_setup, dict) else None
    setup_state = {
        "bundle": args.bundle,
        "modules": [module.name for module in bundle],
        "telegram_ingress_owner": ingress_owner.name,
        "configured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "secret_keys": sorted(preserved_secret_keys | set(secret_values.keys())),
        "llm": llm_setup_state(llm_provider, llm_env),
        "builder_home": str(spark_builder_home()),
    }
    if isinstance(preserved_profiles, dict) and preserved_profiles:
        setup_state["telegram_profiles"] = preserved_profiles
    return secret_values, setup_state


def install_setup_bundle(
    args: argparse.Namespace,
    bundle: list[Module],
    installed_modules: dict[str, Module],
) -> None:
    """Install or register setup bundle modules while keeping reruns lightweight."""
    resume = getattr(args, "resume", False)
    setup_install_skips: dict[str, bool] = {}
    for module in bundle:
        ensure_trust_for_install(args, module, module.name)
        if setup_should_run_install_commands(module, installed_modules, args):
            run_install_commands_with_progress(module, module.name, args, resume)
            setup_install_skips[module.name] = False
        else:
            setup_install_skips[module.name] = True
            if module.name in installed_modules and not getattr(args, "skip_install_commands", False):
                print(
                    f"Skipping install commands for {module.name}: already installed "
                    "(use --run-install-commands to reinstall dependencies)."
                )
    install_modules(bundle)
    for module in bundle:
        install_module_record(
            module,
            operation="install",
            source_kind="bundle",
            source_target=args.bundle,
            bundle_name=args.bundle,
            skip_install_commands=args.skip_install_commands or setup_install_skips.get(module.name, False),
        )
        clear_install_progress(module.name)


def write_setup_runtime_config(
    args: argparse.Namespace,
    modules: dict[str, Module],
    bundle: list[Module],
    secret_values: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Write Builder state, keychain secrets, and generated module env files."""
    builder_notes = initialize_builder_runtime_home(modules, secret_values)
    keychain_report = persist_keychain_secrets(bundle, secret_values)
    generated_envs = build_module_envs(args, modules, secret_values)
    for module in bundle:
        env_values = strip_keychain_env_vars(generated_envs.get(module.name, {}), module)
        generated_path = generated_module_env_path(module)
        write_generated_env(generated_path, env_values)
        env_path = module_env_path(module)
        if env_path is not None and env_values:
            update_env_file(env_path, env_values)
    return builder_notes, keychain_report


def print_setup_summary(
    args: argparse.Namespace,
    ingress_owner: Module,
    builder_notes: list[str],
    keychain_report: dict[str, str],
    setup_state: dict[str, Any],
) -> None:
    print("Spark setup complete.")
    print(f"Bundle: {args.bundle}")
    print(f"Telegram ingress owner: {ingress_owner.name}")
    print("Bot token routed only to spark-telegram-bot.")
    print(f"Generated module config dir: {MODULE_CONFIG_DIR}")
    for note in builder_notes:
        print(f"Builder runtime: {note}")
    if keychain_report:
        for secret_id, backend in sorted(keychain_report.items()):
            print(f"Secret {secret_id} -> {backend}")
    print_setup_next_steps(args.bundle, ingress_owner, setup_state["llm"])


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    if not telegram_profile_is_default(getattr(args, "profile", None)):
        return configure_telegram_profile(args)
    plan = resolve_setup_bundle_plan(args)
    interactive = setup_is_interactive(args)
    if interactive:
        print_setup_preflight(plan.bundle)
    secret_values, setup_state = collect_setup_configuration(
        args,
        plan.bundle,
        plan.ingress_owner,
        interactive,
    )
    save_json(CONFIG_PATH, setup_state)
    install_setup_bundle(args, plan.bundle, plan.installed_modules)
    builder_notes, keychain_report = write_setup_runtime_config(
        args,
        plan.modules,
        plan.bundle,
        secret_values,
    )
    print_setup_summary(args, plan.ingress_owner, builder_notes, keychain_report, setup_state)
    return 0


def persist_keychain_secrets(bundle: list[Module], secret_values: dict[str, str]) -> dict[str, str]:
    """Store each keychain-declared secret from the bundle; return {secret_id: backend_used}."""
    report: dict[str, str] = {}
    seen: set[str] = set()
    for module in bundle:
        _, keychain_backed = split_secret_bindings(module)
        for binding in keychain_backed:
            secret_id = binding["secret_id"]
            if secret_id in seen:
                continue
            value = secret_values.get(secret_id)
            if not value:
                continue
            backend = store_secret(secret_id, value, preferred="keychain")
            report[secret_id] = backend
            seen.add(secret_id)
    return report


def run_shell(
    command: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env or shell_command_env(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr = (stderr + "\n" if stderr else "") + f"command timed out after {timeout}s"
        return subprocess.CompletedProcess(command, 124, stdout=stdout, stderr=stderr)


def quote_managed_python() -> str:
    python_path = str(Path(sys.executable))
    if os.name == "nt":
        return subprocess.list2cmdline([python_path])
    return shlex.quote(python_path)


def command_with_managed_python(command: str) -> str:
    stripped = command.lstrip()
    leading = command[: len(command) - len(stripped)]
    managed_python = quote_managed_python()
    rewrites = (
        ("uv pip install", f"{managed_python} -m pip install"),
        ("uv pip ", f"{managed_python} -m pip "),
        ("python -m pip", f"{managed_python} -m pip"),
        ("python3 -m pip", f"{managed_python} -m pip"),
        ("pip ", f"{managed_python} -m pip "),
        ("pip3 ", f"{managed_python} -m pip "),
        ("python ", f"{managed_python} "),
        ("python3 ", f"{managed_python} "),
    )
    for source, replacement in rewrites:
        if stripped == source.rstrip() or stripped.startswith(source):
            return leading + replacement + stripped[len(source):]
    return command


def summarize_command_output(result: subprocess.CompletedProcess[str]) -> str:
    lines = []
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    for raw_line in (stdout + "\n" + stderr).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("> "):
            continue
        lines.append(line)
    if not lines:
        return "no output"
    try:
        payload = json.loads("\n".join(lines))
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("detail", "message", "summary", "status"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if "backend" in payload and "document_count" in payload:
            return (
                f"memory backend={payload.get('backend')} | "
                f"documents={payload.get('document_count')} | "
                f"manifest_present={payload.get('manifest_present')}"
            )
        if "normalized_contracts" in payload:
            contracts = payload.get("normalized_contracts")
            official = payload.get("official_benchmark_adapters")
            shadow = payload.get("shadow_benchmark_adapters")
            return (
                f"{len(contracts) if isinstance(contracts, list) else 0} normalized contracts | "
                f"{len(official) if isinstance(official, list) else 0} official adapters | "
                f"{len(shadow) if isinstance(shadow, list) else 0} shadow adapters"
            )
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))[:200]
    return lines[-1]


def collect_status_payload() -> dict[str, Any]:
    ensure_state_dirs()
    installed = load_json(REGISTRY_PATH, {})
    setup_state = load_json(CONFIG_PATH, {})
    if not installed:
        return {
            "ok": False,
            "summary": "No installed Spark modules recorded.",
            "repair": "Run `spark setup telegram-starter` first.",
            "modules": [],
        }

    modules = {name: load_module(Path(data["path"])) for name, data in installed.items()}
    module_results = [evaluate_module_health(module) for module in modules.values()]
    module_results_by_name = {item["name"]: item for item in module_results}
    for item in module_results:
        item["installed"] = describe_installed_record(modules[item["name"]], dict(installed.get(item["name"], {})))
        item["repair_hints"] = build_module_repair_hints(
            modules[item["name"]],
            item,
            module_results_by_name,
            setup_state,
        )
    tracked_pids = load_pids()
    repair_hints = build_status_repair_hints(modules, module_results, setup_state, tracked_pids)
    ok = all(item["healthy"] is not False for item in module_results) and not repair_hints
    return {
        "ok": ok,
        "summary": "Spark CLI spike status",
        "telegram_ingress_owner": setup_state.get("telegram_ingress_owner"),
        "llm": setup_state.get("llm"),
        "telegram_profiles": telegram_profile_runtime_status(setup_state, tracked_pids),
        "modules": module_results,
        "tracked_pids": tracked_pids,
        "config_dir": str(CONFIG_DIR),
        "repair_hints": repair_hints,
    }


def cmd_status(args: argparse.Namespace) -> int:
    payload = collect_status_payload()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1

    if not payload.get("modules"):
        print(payload["summary"])
        print(payload["repair"])
        return 1

    print(payload["summary"])
    ingress_owner = payload.get("telegram_ingress_owner")
    if ingress_owner:
        print(f"Telegram ingress owner: {ingress_owner}")
    llm_state = payload.get("llm")
    if isinstance(llm_state, dict) and llm_state.get("provider"):
        if llm_state["provider"] == "not_configured":
            print("LLM provider: not configured")
        else:
            model = llm_state.get("model") or "default"
            print(f"LLM provider: {llm_state['provider']} ({model})")
        roles = llm_state.get("roles")
        if isinstance(roles, dict):
            role_summary = ", ".join(
                f"{role}={roles.get(role, {}).get('provider', llm_state['provider'])}"
                for role in LLM_ROLES
            )
            print(f"LLM roles: {role_summary}")
    profiles = payload.get("telegram_profiles")
    if isinstance(profiles, list) and profiles:
        profile_summary = ", ".join(
            f"{item.get('profile')}={'running' if item.get('running') else 'stopped'}"
            + (f"(:{item.get('relay_port')})" if item.get("relay_port") else "")
            for item in profiles
            if isinstance(item, dict)
        )
        if profile_summary:
            print(f"Telegram profiles: {profile_summary}")
    for hint in payload.get("repair_hints", []):
        print(f"Repair: {hint}")
    print("")

    exit_code = 0
    for module in payload["modules"]:
        healthy = module["healthy"]
        if healthy is None:
            marker = "[SKIP]"
        elif healthy:
            marker = "[OK]"
        else:
            marker = "[ERR]"
        detail = str(module["detail"])
        if module.get("repair_hints"):
            detail = f"{detail} -- {' '.join(module['repair_hints'])}"
        print(f"{marker} {module['name']:<26} {detail}")
        if healthy is False:
            exit_code = 1
    if payload.get("repair_hints"):
        exit_code = 1
    return exit_code


def cmd_doctor(args: argparse.Namespace) -> int:
    payload = collect_status_payload()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Spark CLI spike doctor")
        print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


def collect_telegram_fix_payload() -> dict[str, Any]:
    status_payload = collect_status_payload()
    setup_state = load_json(CONFIG_PATH, {})
    secret_keys = set(setup_state.get("secret_keys", [])) if isinstance(setup_state, dict) else set()
    modules_by_name = {
        item.get("name"): item for item in status_payload.get("modules", []) if isinstance(item, dict)
    }
    telegram_result = modules_by_name.get("spark-telegram-bot")
    pids = status_payload.get("tracked_pids") if isinstance(status_payload.get("tracked_pids"), dict) else {}
    telegram_pid = pids.get("spark-telegram-bot") if isinstance(pids, dict) else None

    env_values = read_generated_env(MODULE_CONFIG_DIR / "spark-telegram-bot.env")
    builder_env = read_generated_env(MODULE_CONFIG_DIR / "spark-intelligence-builder.env")
    llm_state = status_payload.get("llm") if isinstance(status_payload.get("llm"), dict) else {}
    llm_hints = build_llm_repair_hints(llm_state) if llm_state else [
        "No LLM provider is configured. Run `spark setup` to choose chat, builder, memory, and mission providers."
    ]
    recent_gateway_log = "".join(tail_log_lines(module_log_path("spark-telegram-bot"), 120))
    polling_conflict = (
        "409: Conflict" in recent_gateway_log
        and "getUpdates" in recent_gateway_log
    )

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "starter_installed",
            "ok": bool(status_payload.get("modules")),
            "detail": "Spark starter modules are installed." if status_payload.get("modules") else "No installed Spark modules recorded.",
            "repair": "spark setup telegram-starter",
        }
    )
    checks.append(
        {
            "name": "telegram_module_health",
            "ok": bool(telegram_result and telegram_result.get("healthy") is True),
            "detail": telegram_result.get("detail") if telegram_result else "spark-telegram-bot is not installed.",
            "repair": "spark status",
        }
    )
    telegram_detail = str(telegram_result.get("detail", "")) if isinstance(telegram_result, dict) else ""
    token_recorded = "telegram.bot_token" in secret_keys
    token_rejected = "telegram rejected bot_token" in telegram_detail.lower()
    checks.append(
        {
            "name": "bot_token",
            "ok": token_recorded and not token_rejected,
            "detail": (
                "Telegram bot token is configured."
                if token_recorded and not token_rejected
                else "Telegram bot token is stored but Telegram rejected it; rotate it in BotFather."
                if token_recorded and token_rejected
                else "Telegram bot token is missing."
            ),
            "repair": "spark setup --bot-token <BOTFATHER_TOKEN>",
        }
    )
    checks.append(
        {
            "name": "admin_allowlist",
            "ok": "telegram.admin_ids" in secret_keys,
            "detail": "Telegram admin allowlist is configured." if "telegram.admin_ids" in secret_keys else "Telegram admin ids are missing.",
            "repair": "Send /myid to the bot, then rerun `spark setup --admin-telegram-ids <id>`.",
        }
    )
    bridge_mode = env_values.get("SPARK_BUILDER_BRIDGE_MODE")
    checks.append(
        {
            "name": "builder_bridge",
            "ok": bridge_mode == "required" and bool(env_values.get("SPARK_BUILDER_HOME")),
            "detail": "Telegram is configured to require the Builder bridge." if bridge_mode == "required" else "Telegram is not configured to require the Builder bridge.",
            "repair": "spark setup telegram-starter",
        }
    )
    memory_roots_ok = bool(
        builder_env.get("SPARK_INTELLIGENCE_HOME")
        and builder_env.get("SPARK_DOMAIN_CHIP_MEMORY_ROOT")
        and builder_env.get("SPARK_RESEARCHER_ROOT")
    )
    checks.append(
        {
            "name": "builder_memory_roots",
            "ok": memory_roots_ok,
            "detail": "Builder has Spark home, domain-chip-memory, and Researcher roots." if memory_roots_ok else "Builder memory/Researcher roots are not fully wired.",
            "repair": "spark setup telegram-starter",
        }
    )
    checks.append(
        {
            "name": "llm_roles",
            "ok": not llm_hints,
            "detail": "All Spark LLM roles have configured auth." if not llm_hints else "One or more Spark LLM roles are not ready.",
            "repair": " ".join(llm_hints) if llm_hints else "",
        }
    )
    process_running = False
    if isinstance(telegram_pid, dict):
        process_running = pid_is_running(int(telegram_pid.get("pid", 0)))
    process_detail = (
        f"spark-telegram-bot is running (pid {telegram_pid.get('pid')})."
        if process_running and isinstance(telegram_pid, dict)
        else "spark-telegram-bot is not running under Spark supervision."
    )
    process_repair = "spark restart telegram-starter"
    if not process_running and polling_conflict:
        process_detail += " Recent logs show Telegram 409 getUpdates conflict, which means another copy of this bot is already polling Telegram."
        process_repair = "Stop the other bot process or use a fresh BotFather token, then run `spark restart telegram-starter`."
    checks.append(
        {
            "name": "telegram_process",
            "ok": process_running,
            "detail": process_detail,
            "repair": process_repair,
        }
    )

    ok = all(bool(check["ok"]) for check in checks)
    return {
        "ok": ok,
        "summary": "Spark Telegram repair",
        "checks": checks,
        "status_repair_hints": status_payload.get("repair_hints", []),
        "next_commands": [
            "spark status",
            "spark verify --deep",
            "spark restart telegram-starter",
            "spark logs spark-telegram-bot --lines 80",
            "spark setup telegram-starter",
        ],
    }


def cmd_fix(args: argparse.Namespace) -> int:
    if args.target != "telegram":
        raise SystemExit(f"Unknown fix target: {args.target}")
    payload = collect_telegram_fix_payload()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    print(payload["summary"])
    print("")
    for check in payload["checks"]:
        marker = "[OK]" if check["ok"] else "[FIX]"
        print(f"{marker} {check['name']}: {check['detail']}")
        if not check["ok"] and check.get("repair"):
            print(f"      {check['repair']}")
    if payload.get("status_repair_hints"):
        print("")
        print("Status repair hints:")
        for hint in payload["status_repair_hints"]:
            print(f"  - {hint}")
    print("")
    print("Useful commands:")
    for command in payload["next_commands"]:
        print(f"  {command}")
    return 0 if payload.get("ok") else 1


def provider_catalog_payload() -> dict[str, Any]:
    codex = detect_codex_cli()
    claude = detect_claude_code()
    return {
        "providers": [
            {
                "id": "openai",
                "label": "OpenAI",
                "auth": ["codex_oauth", "api_key"],
                "oauth_available": bool(codex["present"]),
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider openai",
            },
            {
                "id": "codex",
                "label": "Codex CLI",
                "auth": ["codex_oauth"],
                "oauth_available": bool(codex["present"]),
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider codex",
            },
            {
                "id": "anthropic",
                "label": "Anthropic",
                "auth": ["claude_oauth", "api_key"],
                "oauth_available": bool(claude["present"]),
                "recommended_for": ["chat", "builder"],
                "setup": "spark setup --llm-provider anthropic",
            },
            {
                "id": "zai",
                "label": "Z.AI / GLM",
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider zai --zai-api-key <key>",
            },
            {
                "id": "ollama",
                "label": "Ollama",
                "auth": ["local"],
                "oauth_available": False,
                "recommended_for": ["memory", "local/private"],
                "setup": "spark setup --llm-provider ollama --ollama-model <model>",
            },
        ],
        "roles": list(LLM_ROLES),
    }


def provider_status_payload() -> dict[str, Any]:
    setup_state = load_json(CONFIG_PATH, {})
    llm_state = setup_state.get("llm") if isinstance(setup_state, dict) else None
    secret_keys = set(setup_state.get("secret_keys", [])) if isinstance(setup_state, dict) else set()
    if not isinstance(llm_state, dict):
        return {
            "ok": False,
            "configured": False,
            "summary": "No LLM provider is configured.",
            "roles": {},
            "repair_hints": ["Run `spark setup --llm-provider openai` or `spark setup --llm-provider codex` to choose a provider."],
        }
    roles = llm_state.get("roles")
    if not isinstance(roles, dict):
        roles = {role: llm_state for role in LLM_ROLES}
    role_payload: dict[str, Any] = {}
    for role in LLM_ROLES:
        state = roles.get(role, {})
        if not isinstance(state, dict):
            state = {}
        provider = str(state.get("provider") or llm_state.get("provider") or "not_configured")
        auth_mode = str(state.get("auth_mode") or llm_state.get("auth_mode") or "not_configured")
        provider_spec = LLM_PROVIDER_ENV.get(provider, {})
        api_key_secret = provider_spec.get("api_key_secret")
        if auth_mode == "not_configured":
            if bool(state.get("api_key_configured") or llm_state.get("api_key_configured")):
                auth_mode = "api_key"
            elif api_key_secret and api_key_secret in secret_keys:
                auth_mode = "api_key"
            elif provider in {"codex", "openai"} and detect_codex_cli()["present"]:
                auth_mode = "codex_oauth"
            elif provider == "anthropic" and detect_claude_code()["present"]:
                auth_mode = "claude_oauth"
            elif provider == "ollama":
                auth_mode = "local"
        role_payload[role] = {
            "provider": provider,
            "bot_provider": state.get("bot_provider") or provider_spec.get("bot_provider"),
            "model": state.get("model") or llm_state.get("model") or "",
            "auth_mode": auth_mode,
            "ready": provider != "not_configured" and auth_mode != "not_configured",
        }
    repair_hints = build_llm_repair_hints({"provider": llm_state.get("provider"), "roles": role_payload})
    return {
        "ok": not repair_hints,
        "configured": bool(llm_state.get("provider") and llm_state.get("provider") != "not_configured"),
        "summary": "Spark LLM provider roles",
        "roles": role_payload,
        "repair_hints": repair_hints,
    }


def cmd_providers(args: argparse.Namespace) -> int:
    if args.providers_command == "list":
        payload = provider_catalog_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        print("Spark LLM providers")
        for provider in payload["providers"]:
            auth = ", ".join(provider["auth"])
            oauth = "available" if provider["oauth_available"] else "not detected"
            print(f"{provider['id']:<10} {provider['label']:<16} auth={auth}; oauth={oauth}")
            print(f"           setup: {provider['setup']}")
        return 0
    if args.providers_command == "status":
        payload = provider_status_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print(payload["summary"])
        for role in LLM_ROLES:
            state = payload["roles"].get(role, {})
            marker = "[OK]" if state.get("ready") else "[FIX]"
            print(
                f"{marker} {role:<7} provider={state.get('provider', 'not_configured')} "
                f"model={state.get('model') or 'not configured'} auth={state.get('auth_mode', 'not_configured')}"
            )
        for hint in payload["repair_hints"]:
            print(f"Repair: {hint}")
        return 0 if payload["ok"] else 1
    raise SystemExit(f"Unknown providers command: {args.providers_command}")


def installed_record_path(installed: object, module_name: str) -> Path | None:
    if not isinstance(installed, dict):
        return None
    record = installed.get(module_name)
    raw_path = record.get("path") if isinstance(record, dict) else record
    if not raw_path:
        return None
    return Path(str(raw_path)).expanduser()


def prepend_pythonpath(env: dict[str, str], paths: list[Path]) -> None:
    existing = env.get("PYTHONPATH", "").strip()
    present = [str(path) for path in paths if path.exists()]
    if not present:
        return
    env["PYTHONPATH"] = os.pathsep.join([*present, existing]) if existing else os.pathsep.join(present)


def collect_builder_memory_direct_smoke(
    *,
    installed: object,
    builder_home: str,
    builder_env: dict[str, str],
) -> dict[str, Any]:
    builder_path = installed_record_path(installed, "spark-intelligence-builder")
    memory_path = installed_record_path(installed, "domain-chip-memory")
    if not builder_home:
        return {
            "ok": False,
            "ran": False,
            "detail": "Builder home is not configured.",
            "repair": "spark setup telegram-starter",
        }
    missing = []
    if builder_path is None or not builder_path.exists():
        missing.append("spark-intelligence-builder")
    if memory_path is None or not memory_path.exists():
        missing.append("domain-chip-memory")
    if missing:
        return {
            "ok": False,
            "ran": False,
            "detail": f"Cannot run memory smoke because installed module paths are missing: {', '.join(missing)}.",
            "repair": "spark setup telegram-starter",
        }

    env = shell_command_env()
    env.update({key: value for key, value in builder_env.items() if value})
    env["SPARK_INTELLIGENCE_HOME"] = builder_home
    env["SPARK_DOMAIN_CHIP_MEMORY_ROOT"] = str(memory_path)
    prepend_pythonpath(env, [builder_path / "src", memory_path / "src"])
    command = [
        sys.executable,
        "-m",
        "spark_intelligence.cli",
        "memory",
        "direct-smoke",
        "--home",
        builder_home,
        "--sdk-module",
        "domain_chip_memory",
        "--json",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(builder_path),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "ran": True,
            "detail": f"Builder memory direct smoke could not complete: {exc}",
            "repair": "spark setup telegram-starter",
        }
    detail = summarize_command_output(result)
    if result.returncode == 0:
        return {
            "ok": True,
            "ran": True,
            "detail": "Builder memory direct smoke wrote, read, and cleaned up through domain-chip-memory.",
            "repair": "",
        }
    return {
        "ok": False,
        "ran": True,
        "detail": detail or f"Builder memory direct smoke failed with exit {result.returncode}.",
        "repair": "spark setup telegram-starter",
    }


def collect_verify_payload(*, deep: bool = False) -> dict[str, Any]:
    status_payload = collect_status_payload()
    provider_payload = provider_status_payload()
    setup_state = load_json(CONFIG_PATH, {})
    installed = load_json(REGISTRY_PATH, {})
    secret_keys = set(setup_state.get("secret_keys", [])) if isinstance(setup_state, dict) else set()
    bundle_name = str(setup_state.get("bundle") or "telegram-starter") if isinstance(setup_state, dict) else "telegram-starter"
    try:
        expected_modules = resolve_bundle_names(bundle_name)
    except SystemExit:
        expected_modules = []

    installed_names = set(installed) if isinstance(installed, dict) else set()
    status_modules = status_payload.get("modules") if isinstance(status_payload.get("modules"), list) else []
    unhealthy = [
        str(item.get("name"))
        for item in status_modules
        if isinstance(item, dict) and item.get("healthy") is False
    ]
    checked = [
        str(item.get("name"))
        for item in status_modules
        if isinstance(item, dict) and item.get("healthy") is not None
    ]

    gateway_env = read_generated_env(MODULE_CONFIG_DIR / "spark-telegram-bot.env")
    builder_env = read_generated_env(MODULE_CONFIG_DIR / "spark-intelligence-builder.env")
    spawner_env = read_generated_env(MODULE_CONFIG_DIR / "spawner-ui.env")
    pids = status_payload.get("tracked_pids") if isinstance(status_payload.get("tracked_pids"), dict) else {}

    def running(module_name: str) -> bool:
        record = pids.get(module_name) if isinstance(pids, dict) else None
        if not isinstance(record, dict):
            return False
        try:
            return pid_is_running(int(record.get("pid", 0)))
        except (TypeError, ValueError):
            return False

    checks: list[dict[str, Any]] = []

    missing_modules = [name for name in expected_modules if name not in installed_names]
    checks.append(
        {
            "name": "starter_bundle",
            "ok": bool(expected_modules) and not missing_modules,
            "required": True,
            "detail": (
                f"{bundle_name} has all {len(expected_modules)} expected modules installed."
                if expected_modules and not missing_modules
                else f"{bundle_name} is missing: {', '.join(missing_modules) or 'bundle definition unavailable'}."
            ),
            "repair": f"spark setup {bundle_name}",
        }
    )

    checks.append(
        {
            "name": "module_health",
            "ok": bool(checked) and not unhealthy,
            "required": True,
            "detail": (
                f"{len(checked)} module healthchecks passed."
                if checked and not unhealthy
                else f"Unhealthy modules: {', '.join(unhealthy) or 'no healthchecks completed'}."
            ),
            "repair": "spark status",
        }
    )

    checks.append(
        {
            "name": "llm_roles",
            "ok": bool(provider_payload.get("ok")),
            "required": True,
            "detail": "Chat, builder, memory, and mission LLM roles are ready." if provider_payload.get("ok") else "One or more LLM roles are not ready.",
            "repair": "spark providers status",
        }
    )

    gateway_webhook_keys = [key for key, value in gateway_env.items() if "WEBHOOK" in key and value]
    telegram_security_ok = (
        "telegram.bot_token" in secret_keys
        and "telegram.admin_ids" in secret_keys
        and gateway_env.get("TELEGRAM_GATEWAY_MODE") == "polling"
        and not gateway_webhook_keys
        and "BOT_TOKEN" not in gateway_env
    )
    checks.append(
        {
            "name": "telegram_long_polling_security",
            "ok": telegram_security_ok,
            "required": True,
            "detail": (
                "Telegram uses long polling, has token/admin secrets recorded, and generated config does not expose BOT_TOKEN."
                if telegram_security_ok
                else "Telegram token/admin setup, long-polling mode, or generated secret hygiene needs repair."
            ),
            "repair": "spark setup telegram-starter",
        }
    )

    if isinstance(setup_state, dict):
        builder_home = gateway_env.get("SPARK_BUILDER_HOME") or str(setup_state.get("builder_home", ""))
    else:
        builder_home = ""
    builder_bridge_ok = (
        gateway_env.get("SPARK_BUILDER_BRIDGE_MODE") == "required"
        and bool(builder_home)
        and bool(builder_env.get("SPARK_INTELLIGENCE_HOME"))
        and bool(builder_env.get("SPARK_DOMAIN_CHIP_MEMORY_ROOT"))
        and bool(builder_env.get("SPARK_RESEARCHER_ROOT"))
    )
    checks.append(
        {
            "name": "builder_memory_bridge",
            "ok": builder_bridge_ok,
            "required": True,
            "detail": (
                "Telegram requires Builder, and Builder has memory plus Researcher roots."
                if builder_bridge_ok
                else "Builder bridge, domain-chip-memory root, or spark-researcher root is not wired."
            ),
            "repair": "spark setup telegram-starter",
        }
    )
    if deep:
        smoke = collect_builder_memory_direct_smoke(
            installed=installed,
            builder_home=builder_home,
            builder_env=builder_env,
        )
        checks.append(
            {
                "name": "builder_memory_direct_smoke",
                "ok": bool(smoke.get("ok")),
                "required": True,
                "detail": str(smoke.get("detail") or ""),
                "repair": str(smoke.get("repair") or "spark setup telegram-starter"),
            }
        )

    mission_provider = (
        spawner_env.get("DEFAULT_MISSION_PROVIDER")
        or spawner_env.get("SPARK_MISSION_LLM_BOT_PROVIDER")
        or spawner_env.get("SPARK_BOT_DEFAULT_PROVIDER")
        or spawner_env.get("BOT_DEFAULT_PROVIDER")
    )
    spawner_ok = (
        bool(spawner_env.get("MISSION_CONTROL_WEBHOOK_URLS"))
        and bool(spawner_env.get("TELEGRAM_RELAY_SECRET"))
        and bool(mission_provider)
        and mission_provider not in {"none", "not_configured"}
    )
    checks.append(
        {
            "name": "spawner_mission_relay",
            "ok": spawner_ok,
            "required": True,
            "detail": (
                f"Spawner mission relay is configured with provider {mission_provider}."
                if spawner_ok
                else "Spawner mission relay or mission LLM provider is not ready."
            ),
            "repair": "spark setup --mission-llm-provider <provider>",
        }
    )

    process_ok, process_detail = process_runtime_detail(
        pids,
        expected_runtime_process_names(installed_names, setup_state if isinstance(setup_state, dict) else {}),
    )
    checks.append(
        {
            "name": "runtime_processes",
            "ok": process_ok,
            "required": True,
            "detail": process_detail,
            "repair": "spark start telegram-starter",
        }
    )

    required_ok = all(bool(check["ok"]) for check in checks if check.get("required", True))
    return {
        "ok": required_ok,
        "summary": "Spark launch verification",
        "bundle": bundle_name,
        "checks": checks,
        "provider_status": provider_payload,
        "status_repair_hints": status_payload.get("repair_hints", []),
        "next_commands": [
            "spark status",
            "spark providers status",
            "spark verify --deep",
            "spark fix telegram",
            "spark start telegram-starter",
            "spark logs spark-telegram-bot --lines 80",
            "spark logs spawner-ui --lines 80",
        ],
    }


def cmd_verify(args: argparse.Namespace) -> int:
    payload = collect_verify_payload(deep=getattr(args, "deep", False))
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload["ok"] else 1
    print(payload["summary"])
    print(f"Bundle: {payload['bundle']}")
    print("")
    for check in payload["checks"]:
        marker = "[OK]" if check["ok"] else "[FIX]"
        print(f"{marker} {check['name']}: {check['detail']}")
        if not check["ok"] and check.get("repair"):
            print(f"      {check['repair']}")
    if payload.get("status_repair_hints"):
        print("")
        print("Status repair hints:")
        for hint in payload["status_repair_hints"]:
            print(f"  - {hint}")
    print("")
    print("Useful commands:")
    for command in payload["next_commands"]:
        print(f"  {command}")
    return 0 if payload["ok"] else 1


def resolve_installed_target_modules(target: str | None) -> list[Module]:
    modules = resolve_installed_modules()
    if not modules:
        return []
    names = expand_targets(target, modules, include_all=True)
    resolved: list[Module] = []
    for name in names:
        module = modules.get(name)
        if module is None:
            raise SystemExit(f"Unknown installed module: {name}")
        resolved.append(module)
    return resolved


def reverse_dependency_map(modules: dict[str, Module]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for module in modules.values():
        for dependency in module.needs_modules:
            reverse.setdefault(dependency, set()).add(module.name)
    return reverse


def topologically_sort_modules(modules: dict[str, Module]) -> list[Module]:
    ordered: list[Module] = []
    permanent: set[str] = set()
    temporary: set[str] = set()

    def visit(name: str) -> None:
        if name in permanent:
            return
        if name in temporary:
            raise SystemExit(f"Dependency cycle detected while ordering modules: {name}")
        module = modules.get(name)
        if module is None:
            raise SystemExit(f"Cannot order missing module: {name}")
        temporary.add(name)
        for dependency in module.needs_modules:
            if dependency in modules:
                visit(dependency)
        temporary.remove(name)
        permanent.add(name)
        ordered.append(module)

    for name in sorted(modules):
        visit(name)
    return ordered


def resolve_start_modules(target: str | None, installed_modules: dict[str, Module]) -> list[Module]:
    requested_names = expand_targets(target, installed_modules, include_all=True)
    needed_names: set[str] = set()
    stack = list(requested_names)
    while stack:
        name = stack.pop()
        module = installed_modules.get(name)
        if module is None:
            raise SystemExit(f"Unknown installed module: {name}")
        if name in needed_names:
            continue
        needed_names.add(name)
        missing_dependencies = [dependency for dependency in module.needs_modules if dependency not in installed_modules]
        if missing_dependencies:
            raise SystemExit(
                f"Cannot start {module.name} because required modules are not installed: {', '.join(missing_dependencies)}"
            )
        stack.extend(module.needs_modules)
    selected_modules = {name: installed_modules[name] for name in needed_names}
    return topologically_sort_modules(selected_modules)


def resolve_stop_module_names(target: str | None, installed_modules: dict[str, Module], tracked_pids: dict[str, Any]) -> list[str]:
    if not tracked_pids:
        return []
    requested_names = expand_targets(target, installed_modules, include_all=True)
    reverse_map = reverse_dependency_map(installed_modules)
    stop_names: set[str] = set()
    stack = list(requested_names)
    while stack:
        name = stack.pop()
        if name in stop_names:
            continue
        stop_names.add(name)
        stack.extend(sorted(reverse_map.get(name, set())))

    installed_subset = {name: installed_modules[name] for name in stop_names if name in installed_modules}
    ordered_names = [module.name for module in reversed(topologically_sort_modules(installed_subset))]
    expanded_ordered_names: list[str] = []
    for name in ordered_names:
        if name == "spark-telegram-bot":
            tracked_bot_keys = tracked_process_keys_for_module(tracked_pids, "spark-telegram-bot")
            expanded_ordered_names.extend(tracked_bot_keys or [name])
        else:
            expanded_ordered_names.append(name)
    extra_names = [name for name in stop_names if name not in installed_subset]
    return expanded_ordered_names + sorted(extra_names)


def resolve_restart_modules(target: str | None, installed_modules: dict[str, Module], tracked_pids: dict[str, Any]) -> list[Module]:
    requested_names = expand_targets(target, installed_modules, include_all=True)
    restart_names = set(requested_names)
    restart_names.update(name for name in resolve_stop_module_names(target, installed_modules, tracked_pids) if name in installed_modules)

    start_names: set[str] = set()
    for name in restart_names:
        for module in resolve_start_modules(name, installed_modules):
            start_names.add(module.name)
    selected_modules = {name: installed_modules[name] for name in start_names}
    return topologically_sort_modules(selected_modules)


def load_pids() -> dict[str, Any]:
    return load_json(PID_PATH, {})


def save_pids(payload: dict[str, Any]) -> None:
    save_json(PID_PATH, payload)


@contextmanager
def pid_file_lock(timeout_seconds: float = 15.0):
    PID_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PID_LOCK_PATH.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + timeout_seconds
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise SystemExit("Timed out waiting for Spark process registry lock. Try again in a moment.")
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise SystemExit("Timed out waiting for Spark process registry lock. Try again in a moment.")
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def tracked_process_keys_for_module(pids: dict[str, Any], module_name: str) -> list[str]:
    keys: list[str] = []
    for key, record in pids.items():
        owns_key = key == module_name or key.startswith(f"{module_name}:")
        owns_record = isinstance(record, dict) and record.get("module") == module_name
        if owns_key or owns_record:
            keys.append(key)
    return sorted(keys)


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == still_active
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ready_timeout_seconds(module: Module) -> int:
    configured = module.manifest.get("healthcheck", {}).get("timeout_seconds", 10)
    try:
        return max(1, int(configured))
    except (TypeError, ValueError):
        return 10


def post_ready_watch_seconds(module: Module) -> int:
    configured = module.post_ready_watch_seconds
    if configured is not None:
        return configured
    return min(8, ready_timeout_seconds(module))


def wait_for_ready_check(
    module: Module,
    process: subprocess.Popen[Any] | None = None,
    *,
    profile: str | None = None,
) -> tuple[bool, str]:
    ready_check = module.ready_check
    if not ready_check:
        return True, "no ready check declared"

    timeout_seconds = ready_timeout_seconds(module)
    if ready_check == "process":
        if process is None:
            return False, "process ready check requires a spawned process"
        stable_until = time.time() + min(5, timeout_seconds)
        while time.time() < stable_until:
            exit_code = process.poll()
            if exit_code is not None:
                return False, f"process exited with code {exit_code}"
            time.sleep(0.2)
        return True, "process is running"

    deadline = time.time() + timeout_seconds
    last_error = "ready check did not pass before timeout"
    while time.time() < deadline:
        if process is not None:
            exit_code = process.poll()
            if exit_code is not None:
                if not ready_check.startswith(("http://", "https://")):
                    result = run_shell(
                        ready_check,
                        module.path,
                        env=module_runtime_env(module, profile),
                        timeout=timeout_seconds,
                    )
                    if result.returncode == 0:
                        return True, summarize_command_output(result)
                    ready_detail = summarize_command_output(result).rstrip(".")
                    return False, f"{ready_detail}. Process exited with code {exit_code}"
                return False, f"process exited with code {exit_code}"
        if ready_check.startswith(("http://", "https://")):
            try:
                with urllib.request.urlopen(ready_check, timeout=2) as response:
                    if 200 <= int(response.status) < 400:
                        return True, ready_check
                    last_error = f"ready check returned HTTP {response.status}"
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = str(error)
        else:
            result = run_shell(
                ready_check,
                module.path,
                env=module_runtime_env(module, profile),
                timeout=timeout_seconds,
            )
            if result.returncode == 0:
                detail = summarize_command_output(result)
                if process is not None:
                    stable_until = time.time() + post_ready_watch_seconds(module)
                    while time.time() < stable_until:
                        exit_code = process.poll()
                        if exit_code is not None:
                            return False, f"{detail.rstrip('.')}. Process exited with code {exit_code}"
                        time.sleep(0.5)
                return True, detail
            last_error = summarize_command_output(result)
        time.sleep(1)
    if ready_check.startswith(("http://", "https://")):
        return False, f"{ready_check} did not become ready within {timeout_seconds}s (last error: {last_error})"
    return False, f"ready check did not pass within {timeout_seconds}s: {last_error}"


def format_start_warning(module: Module, detail: str, process: subprocess.Popen[Any], profile: str | None = None) -> str:
    normalized = normalize_telegram_profile(profile)
    profile_hint = f" --profile {normalized}" if module.name == "spark-telegram-bot" and normalized != DEFAULT_TELEGRAM_PROFILE else ""
    log_hint = f"Run `spark logs {module.name}{profile_hint} --lines 80` for startup logs."
    exit_code = process.poll()
    if exit_code is not None:
        if "process exited with code" in detail.lower():
            return f"{detail}. {log_hint}"
        return f"{detail}. The process exited with code {exit_code}. {log_hint}"
    return f"{detail}. The process is still running and may still be booting. {log_hint}"


def windows_service_creationflags() -> int:
    return (
        int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        | int(getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0))
        | int(getattr(subprocess, "DETACHED_PROCESS", 0))
    )


def listening_pid_for_tcp_port(port: int) -> int | None:
    if os.name != "nt":
        return None
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    suffix = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address = parts[1]
        state = parts[-2].upper()
        pid_text = parts[-1]
        if state == "LISTENING" and local_address.endswith(suffix):
            try:
                return int(pid_text)
            except ValueError:
                return None
    return None


def module_runtime_listener_ports(module: Module, profile: str | None = None) -> list[int]:
    if module.name == "spark-telegram-bot":
        raw_port = module_runtime_env(module, profile).get("TELEGRAM_RELAY_PORT", "8788")
        try:
            return [int(raw_port)]
        except (TypeError, ValueError):
            return [8788]
    ready_check = module.ready_check or ""
    if ready_check.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(ready_check)
        if parsed.port:
            return [int(parsed.port)]
    return []


def discover_runtime_pid(module: Module, process: subprocess.Popen[Any], profile: str | None = None) -> int:
    for port in module_runtime_listener_ports(module, profile):
        pid = listening_pid_for_tcp_port(port)
        if pid and pid_is_running(pid):
            return pid
    if pid_is_running(process.pid):
        return int(process.pid)
    return int(process.pid)


def update_tracked_runtime_pid(process_key: str, launched_pid: int, runtime_pid: int) -> None:
    if runtime_pid == launched_pid:
        return
    with pid_file_lock():
        pids = load_pids()
        record = pids.get(process_key)
        if isinstance(record, dict) and int(record.get("pid", 0)) == int(launched_pid):
            record["pid"] = int(runtime_pid)
            record["launcher_pid"] = int(launched_pid)
            save_pids(pids)


def process_runtime_detail(pids: dict[str, Any], module_names: list[str]) -> tuple[bool, str]:
    missing: list[str] = []
    running_names: list[str] = []
    for name in module_names:
        record = pids.get(name) if isinstance(pids, dict) else None
        pid = int(record.get("pid", 0)) if isinstance(record, dict) else 0
        if pid and pid_is_running(pid):
            running_names.append(f"{name} (pid {pid})")
        else:
            missing.append(name)
    if not missing:
        return True, "Runtime processes are running under Spark supervision: " + ", ".join(running_names) + "."
    if running_names:
        return False, "Missing Spark-supervised runtime process(es): " + ", ".join(missing) + f". Running: {', '.join(running_names)}."
    return False, "Missing Spark-supervised runtime process(es): " + ", ".join(missing) + "."


def expected_runtime_process_names(installed_names: set[str], setup_state: dict[str, Any]) -> list[str]:
    names: list[str] = []
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    has_profiles = isinstance(profiles, dict) and bool(profiles)
    if "spark-telegram-bot" in installed_names and not has_profiles:
        names.append("spark-telegram-bot")
    if "spawner-ui" in installed_names:
        names.append("spawner-ui")
    if isinstance(profiles, dict) and "spark-telegram-bot" in installed_names:
        for profile, profile_state in sorted(profiles.items()):
            if isinstance(profile_state, dict):
                process_key = module_process_key("spark-telegram-bot", str(profile))
                if process_key not in names:
                    names.append(process_key)
    return names


def telegram_profile_runtime_status(setup_state: dict[str, Any], pids: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = setup_state.get("telegram_profiles")
    if not isinstance(profiles, dict):
        return []
    statuses: list[dict[str, Any]] = []
    for profile, profile_state in sorted(profiles.items()):
        if not isinstance(profile_state, dict):
            continue
        normalized = normalize_telegram_profile(str(profile))
        process_key = module_process_key("spark-telegram-bot", normalized)
        record = pids.get(process_key) if isinstance(pids, dict) else None
        pid = 0
        if isinstance(record, dict):
            try:
                pid = int(record.get("pid", 0))
            except (TypeError, ValueError):
                pid = 0
        statuses.append(
            {
                "profile": normalized,
                "process_key": process_key,
                "pid": pid or None,
                "running": bool(pid and pid_is_running(pid)),
                "relay_port": profile_state.get("relay_port"),
                "log_path": str(module_log_path("spark-telegram-bot", normalized)),
            }
        )
    return statuses


def start_module(module: Module, *, allow_boot_warnings: bool = False, profile: str | None = None) -> bool:
    command = module.run_command
    if not command:
        return True

    process_key = module_process_key(module.name, profile)
    display_name = process_key
    log_path = module_log_path(module.name, profile)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_process_log(
        module.name,
        f"starting command={command!r} cwd={module.path} ready_check={module.ready_check!r}",
        profile=profile,
    )

    subprocess_env = module_runtime_env(module, profile)
    popen_kwargs: dict[str, Any] = {
        "cwd": str(module.path),
        "shell": True,
        "stderr": subprocess.STDOUT,
        "env": subprocess_env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = windows_service_creationflags()
    else:
        popen_kwargs["start_new_session"] = True

    with pid_file_lock():
        pids = load_pids()
        existing = pids.get(process_key)
        if existing:
            existing_pid = int(existing.get("pid", 0))
            if pid_is_running(existing_pid):
                print(f"Skipping {display_name}: already running (pid {existing_pid})")
                return True
            pids.pop(process_key, None)

        log_handle = log_path.open("a", encoding="utf-8")
        popen_kwargs["stdout"] = log_handle
        try:
            process = subprocess.Popen(command, **popen_kwargs)
        finally:
            log_handle.close()
        pids[process_key] = {
            "pid": process.pid,
            "module": module.name,
            "profile": normalize_telegram_profile(profile),
            "command": command,
            "path": str(module.path),
            "started_at": timestamp_now(),
            "log_path": str(log_path),
            "ready_check": module.ready_check,
        }
        save_pids(pids)
    print(f"Started {display_name} (pid {process.pid})")
    ready, detail = wait_for_ready_check(module, process=process, profile=profile)
    if ready:
        runtime_pid = discover_runtime_pid(module, process, profile)
        update_tracked_runtime_pid(process_key, process.pid, runtime_pid)
        pid_detail = f" pid={runtime_pid}" if runtime_pid == process.pid else f" pid={runtime_pid} launcher_pid={process.pid}"
        print(f"Ready {display_name}: {detail}")
        append_process_log(module.name, f"ready{pid_detail} detail={detail}", profile=profile)
    else:
        warning = format_start_warning(module, detail, process, profile=profile)
        print(f"Start warning for {display_name}: {warning}")
        append_process_log(module.name, f"start warning pid={process.pid} detail={warning}", profile=profile)
        if process.poll() is not None:
            with pid_file_lock():
                latest_pids = load_pids()
                latest_record = latest_pids.get(process_key, {})
                if int(latest_record.get("pid", 0)) == int(process.pid):
                    latest_pids.pop(process_key, None)
                    save_pids(latest_pids)
        if allow_boot_warnings and process.poll() is None:
            return True
    return ready


def cmd_start(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = resolve_installed_modules()
    if not modules:
        print("No installed Spark modules recorded. Run `spark setup telegram-starter` first.")
        return 1
    exit_code = 0
    profile = normalize_telegram_profile(getattr(args, "profile", None))
    target_modules = resolve_start_modules(args.target, modules)
    requested_names = set(expand_targets(args.target, modules, include_all=True))
    for module in target_modules:
        if not module.run_command:
            if module.name in requested_names:
                print(f"Skipping {module.name}: no run.default command declared")
            continue
        if module.name == "spark-telegram-bot" and profile == DEFAULT_TELEGRAM_PROFILE:
            profiles = autostart_telegram_profiles()
            for telegram_profile in profiles or [DEFAULT_TELEGRAM_PROFILE]:
                if not start_module(
                    module,
                    allow_boot_warnings=getattr(args, "allow_boot_warnings", False),
                    profile=telegram_profile,
                ):
                    exit_code = 1
            continue
        module_profile = profile if module.name == "spark-telegram-bot" else DEFAULT_TELEGRAM_PROFILE
        if not start_module(module, allow_boot_warnings=getattr(args, "allow_boot_warnings", False), profile=module_profile):
            exit_code = 1
    return exit_code


def stop_module(name: str, pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            subprocess.run(["kill", str(pid)], check=False, capture_output=True)
    print(f"Stopped {name} (pid {pid})")


def stop_tracked_process_key(process_key: str) -> bool:
    with pid_file_lock():
        pids = load_pids()
        record = pids.get(process_key)
        if not isinstance(record, dict):
            return False
        pid = int(record.get("pid", 0))
        if pid and pid_is_running(pid):
            stop_module(process_key, pid)
        pids.pop(process_key, None)
        save_pids(pids)
    return True


def cmd_stop(args: argparse.Namespace) -> int:
    with pid_file_lock():
        pids = load_pids()
    if not pids:
        print("No tracked Spark processes.")
        return 0

    installed_modules = resolve_installed_modules()
    profile = normalize_telegram_profile(getattr(args, "profile", None))
    if profile != DEFAULT_TELEGRAM_PROFILE:
        requested_names = expand_targets(args.target, installed_modules, include_all=True)
        if "spark-telegram-bot" not in requested_names:
            print(f"Profile {profile} only applies to spark-telegram-bot; no profiled process stopped.")
            return 0
        target_names = [module_process_key("spark-telegram-bot", profile)]
    else:
        target_names = resolve_stop_module_names(args.target, installed_modules, pids)
    for name in target_names:
        if not stop_tracked_process_key(name):
            print(f"Skipping {name}: no tracked pid")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    installed_modules = resolve_installed_modules()
    if not installed_modules:
        print("No installed Spark modules recorded. Run `spark setup telegram-starter` first.")
        return 1
    profile = normalize_telegram_profile(getattr(args, "profile", None))
    if profile != DEFAULT_TELEGRAM_PROFILE:
        requested_names = expand_targets(args.target, installed_modules, include_all=True)
        if "spark-telegram-bot" not in requested_names:
            print(f"Profile {profile} only applies to spark-telegram-bot; restarting default target instead.")
        else:
            stop_code = cmd_stop(args)
            module = installed_modules["spark-telegram-bot"]
            start_code = 0
            if not start_module(
                module,
                allow_boot_warnings=getattr(args, "allow_boot_warnings", False),
                profile=profile,
            ):
                start_code = 1
            return start_code or stop_code
    restart_modules = resolve_restart_modules(args.target, installed_modules, load_pids())
    stop_code = cmd_stop(args)
    start_code = 0
    for module in restart_modules:
        if not module.run_command:
            print(f"Skipping {module.name}: no run.default command declared")
            continue
        if module.name == "spark-telegram-bot":
            profiles = autostart_telegram_profiles()
            for telegram_profile in profiles or [DEFAULT_TELEGRAM_PROFILE]:
                if not start_module(
                    module,
                    allow_boot_warnings=getattr(args, "allow_boot_warnings", False),
                    profile=telegram_profile,
                ):
                    start_code = 1
            continue
        if not start_module(module, allow_boot_warnings=getattr(args, "allow_boot_warnings", False)):
            start_code = 1
    return start_code or stop_code


def spark_invocation_args() -> list[str]:
    wrapper_name = "spark.cmd" if os.name == "nt" else "spark"
    spark_home_wrapper = SPARK_HOME / "bin" / wrapper_name
    if spark_home_wrapper.exists():
        return [str(spark_home_wrapper.resolve())]
    argv0 = Path(str(sys.argv[0])).expanduser()
    if argv0.exists() and argv0.suffix.lower() not in {".py", ".pyc"}:
        return [str(argv0.resolve())]
    found = shutil.which("spark")
    if found:
        return [found]
    return [sys.executable, "-m", "spark_cli.cli"]


def shell_join(args: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline([str(arg) for arg in args])
    return " ".join(shlex.quote(str(arg)) for arg in args)


def autostart_telegram_profiles() -> list[str]:
    setup_state = load_json(CONFIG_PATH, {})
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    if not isinstance(profiles, dict):
        return []
    return sorted(
        normalize_telegram_profile(profile)
        for profile, profile_state in profiles.items()
        if isinstance(profile_state, dict)
    )


def autostart_should_include_telegram_profiles(target: str) -> bool:
    return target in {"telegram-starter", "spark-telegram-bot"}


def spark_action_shell_command(action: str, target: str, *, profile: str | None = None) -> str:
    args = spark_invocation_args() + [action]
    if action == "start":
        args.append("--allow-boot-warnings")
    if profile and normalize_telegram_profile(profile) != DEFAULT_TELEGRAM_PROFILE:
        args.extend(["--profile", normalize_telegram_profile(profile)])
    args.append(target)
    return shell_join(args)


def autostart_shell_commands(action: str, target: str) -> list[str]:
    base_command = spark_action_shell_command(action, target)
    if not autostart_should_include_telegram_profiles(target):
        return [base_command]

    profiles = autostart_telegram_profiles()
    profile_commands = [
        spark_action_shell_command(action, "spark-telegram-bot", profile=profile)
        for profile in profiles
    ]
    if action == "start":
        return [base_command]
    if action == "stop":
        return profile_commands + [base_command]
    return [base_command] + profile_commands


def autostart_shell_command(action: str, target: str) -> str:
    return " && ".join(autostart_shell_commands(action, target))


def render_systemd_autostart_unit(*, target: str, start_command: str, stop_command: str) -> str:
    return f"""[Unit]
Description=Spark Telegram agent
After=default.target network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={SPARK_HOME}
Environment=SPARK_HOME={SPARK_HOME}
ExecStart=/bin/sh -lc {shlex.quote(start_command)}
ExecStop=/bin/sh -lc {shlex.quote(stop_command)}
TimeoutStartSec=180

[Install]
WantedBy=default.target
"""


def render_launch_agent_plist(*, target: str, start_command: str, stop_command: str) -> str:
    stdout_path = LOG_DIR / AUTOSTART_SERVICE_NAME / "launchd.out.log"
    stderr_path = LOG_DIR / AUTOSTART_SERVICE_NAME / "launchd.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{xml_escape(AUTOSTART_LAUNCHD_LABEL)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-lc</string>
    <string>{xml_escape(start_command)}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>SPARK_HOME</key>
    <string>{xml_escape(str(SPARK_HOME))}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{xml_escape(str(stdout_path))}</string>
  <key>StandardErrorPath</key>
  <string>{xml_escape(str(stderr_path))}</string>
  <key>AbandonProcessGroup</key>
  <true/>
</dict>
</plist>
"""


def linux_autostart_scope() -> str:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return "system"
    return "user"


def linux_autostart_path(scope: str | None = None) -> Path:
    resolved_scope = scope or linux_autostart_scope()
    if resolved_scope == "system":
        return Path("/etc/systemd/system") / f"{AUTOSTART_SERVICE_NAME}.service"
    return Path.home() / ".config" / "systemd" / "user" / f"{AUTOSTART_SERVICE_NAME}.service"


def systemctl_command(scope: str, *args: str) -> list[str]:
    if scope == "system":
        return ["systemctl", *args]
    return ["systemctl", "--user", *args]


def macos_autostart_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{AUTOSTART_LAUNCHD_LABEL}.plist"


def windows_startup_script_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{AUTOSTART_SERVICE_NAME}.cmd"


def write_windows_startup_script(path: Path, start_command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"@echo off\r\n"
        f"set \"SPARK_HOME={SPARK_HOME}\"\r\n"
        f"cd /d \"{SPARK_HOME}\"\r\n"
        f"{start_command}\r\n",
        encoding="ascii",
    )


def windows_cmd_c(command: str) -> str:
    return "cmd.exe /c " + subprocess.list2cmdline([command])


def run_autostart_helper(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def print_helper_failure(command: list[str], result: subprocess.CompletedProcess[str]) -> None:
    detail = (result.stderr or result.stdout or "").strip()
    print(f"Autostart helper failed ({shell_join(command)}): {detail or f'exit {result.returncode}'}")


def cmd_autostart_install(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    target = args.target or "telegram-starter"
    start_command = autostart_shell_command("start", target)
    stop_command = autostart_shell_command("stop", target)
    failures = 0

    if sys.platform.startswith("linux"):
        scope = linux_autostart_scope()
        service_path = linux_autostart_path(scope)
        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text(
            render_systemd_autostart_unit(
                target=target,
                start_command=start_command,
                stop_command=stop_command,
            ),
            encoding="utf-8",
        )
        print(f"Installed Spark autostart service ({scope}): {service_path}")
        for command in (
            systemctl_command(scope, "daemon-reload"),
            systemctl_command(scope, "enable", service_path.name),
        ):
            result = run_autostart_helper(command)
            if result.returncode != 0:
                failures += 1
                print_helper_failure(command, result)
        if args.now:
            command = systemctl_command(scope, "restart", service_path.name)
            result = run_autostart_helper(command)
            if result.returncode != 0:
                failures += 1
                print_helper_failure(command, result)
                print(f"Manual fallback for this session: {start_command}")
        print("Spark will start at login with: " + start_command)
        return 1 if failures else 0

    if sys.platform == "darwin":
        plist_path = macos_autostart_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / AUTOSTART_SERVICE_NAME).mkdir(parents=True, exist_ok=True)
        plist_path.write_text(
            render_launch_agent_plist(
                target=target,
                start_command=start_command,
                stop_command=stop_command,
            ),
            encoding="utf-8",
        )
        print(f"Installed Spark LaunchAgent: {plist_path}")
        uid = str(os.getuid()) if hasattr(os, "getuid") else ""
        bootstrap_domain = f"gui/{uid}" if uid else "gui"
        run_autostart_helper(["launchctl", "bootout", bootstrap_domain, str(plist_path)])
        command = ["launchctl", "bootstrap", bootstrap_domain, str(plist_path)]
        result = run_autostart_helper(command)
        if result.returncode != 0:
            failures += 1
            print_helper_failure(command, result)
        command = ["launchctl", "enable", f"{bootstrap_domain}/{AUTOSTART_LAUNCHD_LABEL}"]
        result = run_autostart_helper(command)
        if result.returncode != 0:
            failures += 1
            print_helper_failure(command, result)
        if args.now:
            command = ["launchctl", "kickstart", "-k", f"{bootstrap_domain}/{AUTOSTART_LAUNCHD_LABEL}"]
            result = run_autostart_helper(command)
            if result.returncode != 0:
                failures += 1
                print_helper_failure(command, result)
                print(f"Manual fallback for this session: {start_command}")
        print("Spark will start at login with: " + start_command)
        return 1 if failures else 0

    if sys.platform == "win32":
        task_command = windows_cmd_c(start_command)
        command = [
            "schtasks",
            "/Create",
            "/SC",
            "ONLOGON",
            "/TN",
            AUTOSTART_WINDOWS_TASK_NAME,
            "/TR",
            task_command,
            "/F",
        ]
        result = run_autostart_helper(command)
        if result.returncode != 0:
            print_helper_failure(command, result)
            startup_path = windows_startup_script_path()
            write_windows_startup_script(startup_path, start_command)
            print(f"Installed Windows Startup fallback: {startup_path}")
            if args.now:
                now_command = ["cmd", "/c", start_command]
                result = run_autostart_helper(now_command)
                if result.returncode != 0:
                    print_helper_failure(now_command, result)
                    print(f"Manual fallback for this session: {start_command}")
                    return 1
            print("Spark will start at login with: " + start_command)
            return 0
        print(f"Installed Windows logon task: {AUTOSTART_WINDOWS_TASK_NAME}")
        if args.now:
            now_command = ["schtasks", "/Run", "/TN", AUTOSTART_WINDOWS_TASK_NAME]
            result = run_autostart_helper(now_command)
            if result.returncode != 0:
                print_helper_failure(now_command, result)
                print(f"Manual fallback for this session: {start_command}")
                return 1
        print("Spark will start at login with: " + task_command)
        return 0

    raise SystemExit(f"Autostart is not supported on this platform yet: {sys.platform}")


def cmd_autostart_uninstall(_: argparse.Namespace) -> int:
    failures = 0
    if sys.platform.startswith("linux"):
        scope = linux_autostart_scope()
        service_path = linux_autostart_path(scope)
        disable_command = systemctl_command(scope, "disable", "--now", service_path.name)
        result = run_autostart_helper(disable_command)
        if result.returncode != 0:
            failures += 1
            print_helper_failure(disable_command, result)
        if service_path.exists():
            service_path.unlink()
            print(f"Removed Spark autostart service: {service_path}")
        reload_command = systemctl_command(scope, "daemon-reload")
        result = run_autostart_helper(reload_command)
        if result.returncode != 0:
            if service_path.exists():
                failures += 1
            print_helper_failure(reload_command, result)
        return 1 if failures else 0

    if sys.platform == "darwin":
        plist_path = macos_autostart_path()
        uid = str(os.getuid()) if hasattr(os, "getuid") else ""
        bootstrap_domain = f"gui/{uid}" if uid else "gui"
        if plist_path.exists():
            result = run_autostart_helper(["launchctl", "bootout", bootstrap_domain, str(plist_path)])
            if result.returncode != 0:
                print_helper_failure(["launchctl", "bootout", bootstrap_domain, str(plist_path)], result)
            plist_path.unlink()
            print(f"Removed Spark LaunchAgent: {plist_path}")
        return 0

    if sys.platform == "win32":
        result = run_autostart_helper(["schtasks", "/Delete", "/TN", AUTOSTART_WINDOWS_TASK_NAME, "/F"])
        if result.returncode != 0:
            print_helper_failure(["schtasks", "/Delete", "/TN", AUTOSTART_WINDOWS_TASK_NAME, "/F"], result)
            failures += 1
        else:
            print(f"Removed Windows logon task: {AUTOSTART_WINDOWS_TASK_NAME}")
        startup_path = windows_startup_script_path()
        if startup_path.exists():
            startup_path.unlink()
            print(f"Removed Windows Startup fallback: {startup_path}")
            failures = 0 if failures else failures
        return 1 if failures else 0

    raise SystemExit(f"Autostart is not supported on this platform yet: {sys.platform}")


def cmd_autostart_status(_: argparse.Namespace) -> int:
    profiles = autostart_telegram_profiles()
    profile_text = ", ".join(profiles) if profiles else "none"
    if sys.platform.startswith("linux"):
        scope = linux_autostart_scope()
        service_path = linux_autostart_path(scope)
        print(f"Linux systemd {scope} service: {service_path}")
        print("Installed: " + ("yes" if service_path.exists() else "no"))
        print(f"Telegram profiles in autostart: {profile_text}")
        if service_path.exists():
            result = run_autostart_helper(systemctl_command(scope, "is-enabled", service_path.name))
            enabled = (result.stdout or result.stderr or "").strip() or f"exit {result.returncode}"
            print(f"Enabled: {enabled}")
        return 0
    if sys.platform == "darwin":
        plist_path = macos_autostart_path()
        print(f"macOS LaunchAgent: {plist_path}")
        installed = plist_path.exists()
        print("Installed: " + ("yes" if installed else "no"))
        print(f"Telegram profiles in autostart: {profile_text}")
        if installed:
            try:
                with plist_path.open("rb") as handle:
                    plist = plistlib.load(handle)
            except (OSError, plistlib.InvalidFileException) as exc:
                print(f"Current Spark home: unknown (could not read LaunchAgent: {exc})")
            else:
                env = plist.get("EnvironmentVariables", {}) if isinstance(plist, dict) else {}
                configured_home = env.get("SPARK_HOME") if isinstance(env, dict) else None
                if configured_home:
                    current_home = str(SPARK_HOME)
                    if str(Path(str(configured_home)).expanduser()) == current_home:
                        print("Current Spark home: yes")
                    else:
                        print("Current Spark home: no")
                        print(f"LaunchAgent Spark home: {configured_home}")
        return 0
    if sys.platform == "win32":
        result = run_autostart_helper(["schtasks", "/Query", "/TN", AUTOSTART_WINDOWS_TASK_NAME])
        print(f"Windows task: {AUTOSTART_WINDOWS_TASK_NAME}")
        task_installed = result.returncode == 0
        startup_path = windows_startup_script_path()
        startup_installed = startup_path.exists()
        print("Installed: " + ("yes" if task_installed or startup_installed else "no"))
        print("Task installed: " + ("yes" if task_installed else "no"))
        print(f"Startup fallback: {startup_path}")
        print("Startup fallback installed: " + ("yes" if startup_installed else "no"))
        print(f"Telegram profiles in autostart: {profile_text}")
        return 0
    raise SystemExit(f"Autostart is not supported on this platform yet: {sys.platform}")


def module_log_path(module_name: str, profile: str | None = None) -> Path:
    normalized = normalize_telegram_profile(profile)
    if module_name == "spark-telegram-bot" and normalized != DEFAULT_TELEGRAM_PROFILE:
        return LOG_DIR / module_name / f"{normalized}.log"
    return LOG_DIR / module_name / "process.log"


def append_process_log(module_name: str, message: str, profile: str | None = None) -> None:
    path = module_log_path(module_name, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(f"[spark-cli {timestamp_now()}] {message.rstrip()}\n")


def tail_log_lines(path: Path, line_count: int) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    if line_count <= 0:
        return lines
    return lines[-line_count:]


def console_safe_text(text: str, encoding: str | None = None) -> str:
    output_encoding = encoding or getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(output_encoding, errors="replace").decode(output_encoding, errors="replace")


def write_console_text(text: str) -> None:
    sys.stdout.write(console_safe_text(text))


def follow_log_file(path: Path) -> None:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, os.SEEK_END)
        try:
            while True:
                chunk = handle.readline()
                if not chunk:
                    time.sleep(0.5)
                    continue
                write_console_text(chunk)
                sys.stdout.flush()
        except KeyboardInterrupt:
            return


def load_user_config() -> dict[str, Any]:
    if not USER_CONFIG_PATH.exists():
        return {}
    data = load_json(USER_CONFIG_PATH, {})
    return data if isinstance(data, dict) else {}


def save_user_config(config: dict[str, Any]) -> None:
    save_json(USER_CONFIG_PATH, config)


def dotted_get(config: dict[str, Any], key: str, default: Any = None) -> Any:
    parts = key.split(".")
    current: Any = config
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def dotted_set(config: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    current = config
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def dotted_unset(config: dict[str, Any], key: str) -> bool:
    parts = key.split(".")
    current: Any = config
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if isinstance(current, dict) and parts[-1] in current:
        current.pop(parts[-1])
        return True
    return False


def coerce_config_value(raw: str) -> Any:
    """Parse a CLI-supplied value into JSON-native types where possible."""
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def cmd_config_get(args: argparse.Namespace) -> int:
    value = dotted_get(load_user_config(), args.key)
    if value is None:
        print(f"{args.key} is not set")
        return 1
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2))
    else:
        print(value)
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    config = load_user_config()
    value = coerce_config_value(args.value)
    dotted_set(config, args.key, value)
    save_user_config(config)
    print(f"Set {args.key} = {json.dumps(value)}")
    return 0


def cmd_config_unset(args: argparse.Namespace) -> int:
    config = load_user_config()
    if not dotted_unset(config, args.key):
        print(f"{args.key} was not set")
        return 1
    save_user_config(config)
    print(f"Unset {args.key}")
    return 0


def cmd_config_list(_: argparse.Namespace) -> int:
    config = load_user_config()
    if not config:
        print("No user config set.")
        return 0
    print(json.dumps(config, indent=2))
    return 0


INIT_SPARK_TOML_TEMPLATE = """[module]
name = "{name}"
version = "0.1.0"
kind = "service"
plane = "execution"
description = "{description}"
license = "UNLICENSED"

[runtime]
kind = "{runtime_kind}"
version = "{runtime_version}"

[install.dev]
commands = []

[provides]
capabilities = []

[needs]
modules = []
capabilities = []
secrets = []

[claims]
secrets = []
ports = []
routes = []

[healthcheck]
command = "{healthcheck_command}"
timeout_seconds = 10
success_hint = "{name} is healthy."
failure_hint = "Run the healthcheck command from the module home for detail."

[paths]
home = "~/.spark/modules/{name}"
state = "~/.spark/state/{name}"
logs = "~/.spark/logs/{name}"
"""


INIT_README_TEMPLATE = """# {name}

{description}

## Quick install

    spark install {target_hint}

## Healthcheck

    {healthcheck_command}

## Layout

* `spark.toml` -- manifest consumed by the Spark installer
* edit `[install.dev].commands`, `[healthcheck].command`, and source files before shipping
"""


INIT_GITIGNORE_PYTHON = """__pycache__/
*.py[cod]
.venv/
.env
dist/
build/
*.egg-info/
"""


INIT_GITIGNORE_NODE = """node_modules/
dist/
.env
npm-debug.log*
"""


INIT_VALID_NAME = re.compile(r"^[a-z][a-z0-9\-]*$")


def validate_init_module_name(name: str) -> None:
    if not INIT_VALID_NAME.match(name):
        raise SystemExit(
            f"Module name `{name}` is invalid. Use lowercase letters, digits, and dashes; must start with a letter."
        )


def render_init_spark_toml(name: str, kind: str, description: str) -> str:
    if kind == "python":
        runtime_kind = "python"
        runtime_version = ">=3.11"
        healthcheck = "python -c \\\"print('ok')\\\""
    elif kind == "node":
        runtime_kind = "node"
        runtime_version = ">=22"
        healthcheck = "node -e \\\"console.log('ok')\\\""
    else:
        raise SystemExit(f"Unsupported kind: {kind}. Use python or node.")
    return INIT_SPARK_TOML_TEMPLATE.format(
        name=name,
        description=description,
        runtime_kind=runtime_kind,
        runtime_version=runtime_version,
        healthcheck_command=healthcheck,
    )


def scaffold_module_files(target_dir: Path, name: str, kind: str, description: str) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    spark_toml = target_dir / "spark.toml"
    readme = target_dir / "README.md"
    gitignore = target_dir / ".gitignore"

    spark_toml.write_text(render_init_spark_toml(name, kind, description), encoding="utf-8")
    healthcheck_command = "python -c \"print('ok')\"" if kind == "python" else "node -e \"console.log('ok')\""
    readme.write_text(
        INIT_README_TEMPLATE.format(
            name=name,
            description=description,
            target_hint=str(target_dir),
            healthcheck_command=healthcheck_command,
        ),
        encoding="utf-8",
    )
    gitignore.write_text(
        INIT_GITIGNORE_PYTHON if kind == "python" else INIT_GITIGNORE_NODE,
        encoding="utf-8",
    )
    return [spark_toml, readme, gitignore]


def cmd_init(args: argparse.Namespace) -> int:
    name = args.name.strip()
    validate_init_module_name(name)
    target_dir = Path(args.path).resolve() if args.path else Path(name).resolve()
    if target_dir.exists() and any(target_dir.iterdir()) and not args.force:
        raise SystemExit(f"{target_dir} exists and is not empty; pass --force to scaffold into it anyway.")
    description = args.description or f"Spark {args.kind} module."
    created = scaffold_module_files(target_dir, name, args.kind, description)

    print(f"Created new Spark {args.kind} module at {target_dir}:")
    for path in created:
        print(f"  {path}")
    print("")
    print("Next:")
    print(f"  python -m spark_cli.cli install {target_dir}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    registry = load_registry_definition()
    entries = registry.get("modules", {}) or {}
    installed = load_json(REGISTRY_PATH, {})
    query = (args.query or "").strip().lower()

    hits: list[tuple[str, str, bool, bool]] = []
    for name, metadata in entries.items():
        summary = str(metadata.get("summary", ""))
        blessed = bool(metadata.get("blessed"))
        if query and query not in name.lower() and query not in summary.lower():
            continue
        hits.append((name, summary, blessed, name in installed))

    if not hits:
        print("No matching modules." if query else "Registry has no modules.")
        return 1 if query else 0

    for name, summary, blessed, installed_flag in sorted(hits):
        badges: list[str] = []
        badges.append("blessed" if blessed else "community")
        if installed_flag:
            badges.append("installed")
        badge_text = ",".join(badges)
        print(f"{name:<30} [{badge_text}] {summary}")
    return 0


def cmd_secrets_list(_: argparse.Namespace) -> int:
    index = list_stored_secrets()
    if not index:
        print("No stored secrets.")
        return 0
    print(f"{len(index)} secret(s) stored:")
    for secret_id, backend in sorted(index.items()):
        print(f"  {secret_id}\t[{backend}]")
    return 0


def cmd_secrets_set(args: argparse.Namespace) -> int:
    if args.value is not None:
        value = args.value
    elif stdin_is_tty():
        value = read_secret_interactive(f"  Paste value for {args.secret_id} (typing is masked): ")
    else:
        value = sys.stdin.read().strip()
    if not value:
        raise SystemExit(f"Refusing to store empty value for {args.secret_id}.")
    backend = store_secret(args.secret_id, value, preferred=args.backend)
    print(f"Stored {args.secret_id} in {backend}.")
    return 0


def cmd_secrets_get(args: argparse.Namespace) -> int:
    value = fetch_secret(args.secret_id)
    if value is None:
        raise SystemExit(f"No value stored for {args.secret_id}.")
    if args.reveal:
        print(value)
    else:
        masked = value[:4] + "..." + value[-2:] if len(value) > 6 else "***"
        print(f"{args.secret_id} -> {masked} (pass --reveal to print full value)")
    return 0


def cmd_secrets_delete(args: argparse.Namespace) -> int:
    if delete_secret(args.secret_id):
        print(f"Deleted {args.secret_id}.")
        return 0
    print(f"No value stored for {args.secret_id}.")
    return 1


def cmd_logs(args: argparse.Namespace) -> int:
    installed = resolve_installed_modules()
    if args.target not in installed:
        raise SystemExit(f"Unknown installed module: {args.target}")
    profile = normalize_telegram_profile(getattr(args, "profile", None))
    if profile != DEFAULT_TELEGRAM_PROFILE and args.target != "spark-telegram-bot":
        raise SystemExit("--profile only applies to spark-telegram-bot logs.")
    path = module_log_path(args.target, profile)
    if not path.exists():
        display_name = module_process_key(args.target, profile)
        print(f"No logs yet for {display_name} at {path}")
        print("Start the module first with `spark start`.")
        return 1
    for line in tail_log_lines(path, args.lines):
        write_console_text(line if line.endswith("\n") else line + "\n")
    if args.follow:
        follow_log_file(path)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = resolve_installed_target_modules(args.target)
    if not modules:
        print("No installed Spark modules recorded.")
        return 0
    print_install_summary(modules)
    for module in modules:
        with pid_file_lock():
            pids = load_pids()
            process_keys = tracked_process_keys_for_module(pids, module.name)
        for process_key in process_keys:
            with pid_file_lock():
                record = load_pids().get(process_key, {})
            pid = int(record.get("pid", 0)) if isinstance(record, dict) else 0
            if pid and pid_is_running(pid):
                print(f"Stopping {process_key} before update so install commands can replace locked files.")
            stop_tracked_process_key(process_key)
        if module_is_git_managed(module.path):
            ok, detail = pull_module_source(module.path)
            print(f"git pull {module.name}: {'ok' if ok else 'failed'} - {detail}")
            if not ok and not args.skip_install_commands:
                raise SystemExit(f"Aborting update for {module.name} after git pull failure.")
        if not args.skip_install_commands:
            execute_install_commands(module)
        run_module_hook(module, "post_install")
        existing_record = load_json(REGISTRY_PATH, {}).get(module.name, {})
        installed_via = dict(existing_record.get("installed_via", {}))
        install_module_record(
            module,
            operation="update",
            source_kind=str(installed_via.get("kind", "installed")),
            source_target=str(installed_via.get("target", module.path)),
            bundle_name=installed_via.get("bundle"),
            skip_install_commands=args.skip_install_commands,
        )
        sync_generated_env_to_module(module)
        print(f"Updated {module.name} from {module.path}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = resolve_installed_target_modules(args.target)
    if not modules:
        print("No installed Spark modules recorded.")
        return 0
    installed_modules = resolve_installed_modules()
    blockers = detect_uninstall_blockers(modules, installed_modules)
    if blockers and not args.force:
        raise SystemExit("Cannot uninstall because other installed modules depend on it: " + "; ".join(blockers))

    removed_names: list[str] = []
    for module in modules:
        run_module_hook(module, "pre_uninstall")
        with pid_file_lock():
            process_keys = tracked_process_keys_for_module(load_pids(), module.name)
        for process_key in process_keys:
            stop_tracked_process_key(process_key)
        generated_path = generated_module_env_path(module)
        if generated_path.exists():
            generated_path.unlink()
        env_path = module_env_path(module)
        if env_path is not None:
            remove_managed_env_block(env_path)
        if module_is_git_managed(module.path):
            remove_module_clone(module.name)
        remove_module_record(module.name)
        run_module_hook(module, "post_uninstall")
        removed_names.append(module.name)
        print(f"Uninstalled {module.name}")
    update_setup_state_after_uninstall(removed_names)
    return 0


def onboarding_guide_payload() -> dict[str, Any]:
    return {
        "title": "Spark starter guide",
        "goal": "Install once, configure one Telegram bot, choose LLM providers by role, then talk to Spark from Telegram.",
        "operating_systems": ["Windows PowerShell/CMD", "macOS Terminal", "Linux shell", "WSL Ubuntu shell"],
        "starter_bundle": [
            {
                "module": "spark-telegram-bot",
                "role": "Telegram front door. Owns the bot token, runs long polling, and receives your chat commands.",
            },
            {
                "module": "spark-intelligence-builder",
                "role": "Runtime brain. Handles identity, memory bridge, provider routing, and domain-chip activation.",
            },
            {
                "module": "domain-chip-memory",
                "role": "Default memory chip. Provides memory contracts, benchmark checks, and memory-oriented skills.",
            },
            {
                "module": "spark-researcher",
                "role": "Research and advisory runtime. Helps with research, evidence packets, and domain-chip authoring.",
            },
            {
                "module": "spawner-ui",
                "role": "Local mission control. Creates and tracks missions, projects, and execution workflows.",
            },
        ],
        "setup": {
            "interactive": "spark setup",
            "botfather": [
                "Open Telegram and message @BotFather.",
                "Send /newbot and follow BotFather's prompts.",
                "Copy the token BotFather gives you.",
                "Start your new bot, send /myid, and copy your numeric Telegram id.",
                "Run spark setup again with the bot token and admin id if you did not provide them during install.",
            ],
            "llm_roles": [
                {"role": "chat", "use": "Telegram chat replies and normal conversation."},
                {"role": "builder", "use": "Builder reasoning, orchestration, and Spark runtime decisions."},
                {"role": "memory", "use": "Memory synthesis, recall shaping, and domain-chip memory work."},
                {"role": "mission", "use": "Spawner missions, coding/build work, and execution tasks."},
            ],
            "llm_examples": [
                "spark setup",
                "spark setup --llm-provider codex --codex-model gpt-5.5",
                "spark setup --llm-provider openai",
                "spark setup --llm-provider openai --openai-api-key <OPENAI_API_KEY> --openai-model gpt-5.5",
                "spark setup --llm-provider anthropic",
                "spark setup --llm-provider anthropic --anthropic-api-key <ANTHROPIC_API_KEY>",
                "spark setup --llm-provider zai --zai-api-key <ZAI_API_KEY>",
                "spark setup --llm-provider ollama --ollama-url http://localhost:11434 --ollama-model <MODEL>",
                "spark setup --chat-llm-provider openai --builder-llm-provider openai --memory-llm-provider ollama --mission-llm-provider openai",
            ],
            "llm_auth_note": "The easiest path is `spark setup` and the guided picker. OpenAI can use a signed-in Codex CLI / ChatGPT session or OPENAI_API_KEY. Anthropic can use Claude Code or ANTHROPIC_API_KEY. Z.AI uses ZAI_API_KEY. Ollama is local. If your default chat LLM is not a local executor, Spark uses Codex or Claude for mission/build execution when available.",
        },
        "start": [
            "spark status",
            "spark autostart install --now",
            "spark start telegram-starter",
        ],
        "multi_bot_profiles": [
            "Use a profile when you want a second Telegram bot on the same Spark install.",
            "Each profile gets its own bot token, local relay port, pid, and log file.",
            "Profiles still share the same local Builder, memory, LLM roles, and Spawner unless you intentionally split those later.",
            "Example: spark setup --profile qa-bot --bot-token @clipboard --admin-telegram-ids <YOUR_TELEGRAM_ID>",
            "Then run: spark start spark-telegram-bot --profile qa-bot",
        ],
        "access_levels": [
            {"level": "1", "name": "Chat Only", "use": "Conversation, memory, recall, and diagnostics. No Spawner builds."},
            {"level": "2", "name": "Build When Asked", "use": "Spark can use Spawner only when you clearly ask it to build or run a mission."},
            {"level": "3", "name": "Research + Build", "use": "Default. Adds public links, docs, and GitHub research. Spark can still build when you ask."},
            {"level": "4", "name": "Full Access", "use": "Adds operating-system access for local project builds, debugging, repo inspection, and deeper missions. Destructive actions still need explicit approval."},
        ],
        "telegram_commands": [
            { "command": "/start", "use": "Show the basic command surface." },
            { "command": "/myid", "use": "Show your numeric Telegram id for admin setup." },
            { "command": "/diagnose", "use": "Check Telegram, LLM, memory, Builder, and mission relay health." },
            { "command": "/remember <note>", "use": "Save a memory through Spark's memory path when available." },
            { "command": "/recall <query>", "use": "Search your Spark memory when available." },
            { "command": "/run <goal>", "use": "Create a Spawner mission from Telegram." },
            { "command": "/board", "use": "Show current mission board/status." },
            { "command": "/access <1|2|3|4>", "use": "Choose how much tool access Spark has in this Telegram chat." },
            { "command": "/mission status <id>", "use": "Inspect a mission." },
            { "command": "normal message", "use": "Ask Spark to answer through the configured LLM provider." },
        ],
        "operator_commands": [
            { "command": "spark status", "use": "Human-readable health check and repair hints." },
            { "command": "spark verify", "use": "Launch-readiness proof for modules, LLM roles, Telegram long polling, Builder memory, Spawner relay, and running processes." },
            { "command": "spark fix telegram", "use": "Targeted quiet-bot repair checklist: token, admin ids, Builder bridge, LLM roles, process, and logs." },
            { "command": "spark doctor --json", "use": "Structured diagnostics for agents and support." },
            { "command": "spark autostart install --now", "use": "Turn on the Telegram agent now and every time this computer logs in." },
            { "command": "spark autostart status", "use": "Check whether login autostart is installed." },
            { "command": "spark logs spark-telegram-bot", "use": "Read Telegram gateway logs." },
            { "command": "spark logs spark-telegram-bot --profile qa-bot", "use": "Read logs for an extra Telegram bot profile." },
            { "command": "spark logs spawner-ui", "use": "Read mission-control logs." },
            { "command": "spark secrets list", "use": "Confirm configured secret ids without printing secret values." },
            { "command": "spark setup", "use": "Rerun onboarding safely when changing bot, admin ids, or LLM provider." },
        ],
        "troubleshooting": [
            "Bot receives no messages: make sure only one polling process is running, then restart spark-telegram-bot.",
            "Second bot receives no messages: run spark restart spark-telegram-bot --profile <profile> and check spark logs spark-telegram-bot --profile <profile>.",
            "Bot is quiet and you are not sure why: run spark fix telegram.",
            "Bot says admin only: send /myid, add that numeric id during spark setup, then restart.",
            "LLM does not answer: rerun spark setup with providers for chat, builder, memory, and mission, then run spark status.",
            "Fresh install feels incomplete: run spark verify and follow the first [FIX] line.",
            "/run fails: start spawner-ui and check spark logs spawner-ui.",
            "Memory does not work: run spark status and repair Builder/domain-chip-memory hints first.",
        ],
    }


def cmd_guide(args: argparse.Namespace) -> int:
    payload = onboarding_guide_payload()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0

    print(payload["title"])
    print(payload["goal"])
    print("Works on: " + ", ".join(payload["operating_systems"]))
    print("")
    print("1. Set up Telegram")
    for step in payload["setup"]["botfather"]:
        print(f"   - {step}")
    print("")
    print("2. Pick LLM providers")
    for item in payload["setup"]["llm_roles"]:
        print(f"   - {item['role']}: {item['use']}")
    print(f"   {payload['setup']['llm_auth_note']}")
    for command in payload["setup"]["llm_examples"]:
        print(f"   {command}")
    print("")
    print("3. Start Spark")
    for command in payload["start"]:
        print(f"   {command}")
    print("")
    print("4. Talk to Spark in Telegram")
    for item in payload["telegram_commands"]:
        print(f"   {item['command']}: {item['use']}")
    print("")
    print("5. Optional: run another Telegram bot")
    for item in payload["multi_bot_profiles"]:
        print(f"   - {item}")
    print("")
    print("6. Choose Spark access level")
    for item in payload["access_levels"]:
        print(f"   Level {item['level']} - {item['name']}: {item['use']}")
    print("   Change it in Telegram with /access <1|2|3|4>.")
    print("")
    print("7. How the modules work together")
    for item in payload["starter_bundle"]:
        print(f"   {item['module']}: {item['role']}")
    print("")
    print("Useful Spark CLI commands")
    for item in payload["operator_commands"]:
        print(f"   {item['command']}: {item['use']}")
    print("")
    print("If something feels stuck")
    for item in payload["troubleshooting"]:
        print(f"   - {item}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spark", description="Spark installer and operator CLI spike")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List local Spark modules with manifests")
    list_parser.set_defaults(func=cmd_list)

    install_parser = subparsers.add_parser("install", help="Install a module by registry name or local repo path")
    install_parser.add_argument("target")
    install_parser.add_argument("--skip-install-commands", action="store_true")
    install_parser.add_argument("--skip-runtime-check", action="store_true", help="Skip [runtime].version constraint enforcement")
    install_parser.add_argument("--trust", action="store_true", help="Approve running install commands and hooks for non-blessed modules without prompting")
    install_parser.add_argument("--resume", action="store_true", help="Skip install steps that succeeded on a prior attempt")
    install_parser.set_defaults(func=cmd_install)

    setup_parser = subparsers.add_parser("setup", help="Configure a starter bundle")
    setup_parser.add_argument(
        "bundle",
        nargs="?",
        default="telegram-starter",
        choices=sorted(load_registry_definition().get("bundles", {}).keys()),
        help="Bundle to configure (default: telegram-starter)",
    )
    setup_parser.add_argument("--skip-install-commands", action="store_true")
    setup_parser.add_argument(
        "--run-install-commands",
        action="store_true",
        help="Re-run dependency install commands for already installed modules",
    )
    setup_parser.add_argument("--skip-runtime-check", action="store_true", help="Skip [runtime].version constraint enforcement")
    setup_parser.add_argument("--trust", action="store_true", help="Approve running install commands and hooks for non-blessed bundle modules without prompting")
    setup_parser.add_argument("--resume", action="store_true", help="Skip install steps that succeeded on a prior attempt")
    setup_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip interactive preflight and secret prompts (require --secret for every required secret).",
    )
    setup_parser.add_argument("--secret", action="append", help="Provide manifest secret values as key=value; use @clipboard or @env:NAME for secret input")
    setup_parser.add_argument("--bot-token", help="Telegram BotFather token, @clipboard, or @env:NAME")
    setup_parser.add_argument("--admin-telegram-ids")
    setup_parser.add_argument("--telegram-relay-secret")
    setup_parser.add_argument("--telegram-relay-port", type=int, help="Local Telegram mission relay port for a non-default profile")
    setup_parser.add_argument(
        "--profile",
        default=DEFAULT_TELEGRAM_PROFILE,
        help="Configure an extra Telegram bot profile without replacing the default bot",
    )
    setup_parser.add_argument("--spawner-ui-url", default="http://127.0.0.1:5173")
    setup_parser.add_argument("--llm-provider", choices=LLM_PROVIDER_CHOICES, help="Default provider for all Spark LLM roles unless a role-specific provider is set")
    setup_parser.add_argument("--chat-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for Telegram chat replies")
    setup_parser.add_argument("--builder-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for Builder reasoning and orchestration")
    setup_parser.add_argument("--memory-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for memory synthesis and recall")
    setup_parser.add_argument("--mission-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for Spawner missions and coding/build work")
    setup_parser.add_argument("--zai-api-key", help="Z.AI / GLM coding endpoint API key, @clipboard, or @env:NAME")
    setup_parser.add_argument("--zai-base-url", default="https://api.z.ai/api/coding/paas/v4/")
    setup_parser.add_argument("--zai-model", default="glm-5.1")
    setup_parser.add_argument("--openai-api-key", help="OpenAI API key, @clipboard, or @env:NAME")
    setup_parser.add_argument("--openai-base-url", default="https://api.openai.com/v1")
    setup_parser.add_argument("--openai-model", default="gpt-5.5")
    setup_parser.add_argument("--anthropic-api-key", help="Anthropic API key, @clipboard, or @env:NAME")
    setup_parser.add_argument("--anthropic-base-url", default="https://api.anthropic.com")
    setup_parser.add_argument("--anthropic-model", default="claude-sonnet-4.5")
    setup_parser.add_argument("--ollama-url", default="http://localhost:11434")
    setup_parser.add_argument("--ollama-model", default="kimi-k2.5:cloud")
    setup_parser.add_argument("--codex-model", default="gpt-5.5")
    setup_parser.set_defaults(func=cmd_setup)

    status_parser = subparsers.add_parser("status", help="Run module healthchecks")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subparsers.add_parser("doctor", help="Run diagnostic status and emit structured output")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    verify_parser = subparsers.add_parser("verify", help="Verify launch-critical Spark wiring end to end")
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.add_argument("--deep", action="store_true", help="Run live write/read memory smoke checks in addition to static wiring checks")
    verify_parser.set_defaults(func=cmd_verify)

    fix_parser = subparsers.add_parser("fix", help="Run targeted repair guidance for common Spark issues")
    fix_parser.add_argument("target", nargs="?", choices=["telegram"], default="telegram")
    fix_parser.add_argument("--json", action="store_true")
    fix_parser.set_defaults(func=cmd_fix)

    providers_parser = subparsers.add_parser("providers", help="Inspect Spark LLM provider choices and role wiring")
    providers_sub = providers_parser.add_subparsers(dest="providers_command", required=True)
    providers_list_parser = providers_sub.add_parser("list", help="List supported LLM providers and setup paths")
    providers_list_parser.add_argument("--json", action="store_true")
    providers_list_parser.set_defaults(func=cmd_providers)
    providers_status_parser = providers_sub.add_parser("status", help="Show chat/build/memory/mission provider readiness")
    providers_status_parser.add_argument("--json", action="store_true")
    providers_status_parser.set_defaults(func=cmd_providers)

    update_parser = subparsers.add_parser("update", help="Refresh installed modules from their current source paths")
    update_parser.add_argument("target", nargs="?")
    update_parser.add_argument("--skip-install-commands", action="store_true")
    update_parser.set_defaults(func=cmd_update)

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove installed modules from Spark state and generated config")
    uninstall_parser.add_argument("target", nargs="?")
    uninstall_parser.add_argument("--force", action="store_true")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    start_parser = subparsers.add_parser("start", help="Start startable modules")
    start_parser.add_argument("--allow-boot-warnings", action="store_true", help=argparse.SUPPRESS)
    start_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Telegram bot profile to start")
    start_parser.add_argument("target", nargs="?")
    start_parser.set_defaults(func=cmd_start)

    stop_parser = subparsers.add_parser("stop", help="Stop tracked Spark processes")
    stop_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Telegram bot profile to stop")
    stop_parser.add_argument("target", nargs="?")
    stop_parser.set_defaults(func=cmd_stop)

    restart_parser = subparsers.add_parser("restart", help="Restart startable modules")
    restart_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Telegram bot profile to restart")
    restart_parser.add_argument("target", nargs="?")
    restart_parser.set_defaults(func=cmd_restart)

    autostart_parser = subparsers.add_parser("autostart", help="Start Spark automatically when this computer logs in")
    autostart_subparsers = autostart_parser.add_subparsers(dest="autostart_command", required=True)
    autostart_install_parser = autostart_subparsers.add_parser("install", help="Install OS login autostart")
    autostart_install_parser.add_argument("target", nargs="?", default="telegram-starter")
    autostart_install_parser.add_argument("--now", action="store_true", help="Start Spark immediately after installing autostart")
    autostart_install_parser.set_defaults(func=cmd_autostart_install)
    autostart_uninstall_parser = autostart_subparsers.add_parser("uninstall", help="Remove OS login autostart")
    autostart_uninstall_parser.set_defaults(func=cmd_autostart_uninstall)
    autostart_status_parser = autostart_subparsers.add_parser("status", help="Show OS login autostart status")
    autostart_status_parser.set_defaults(func=cmd_autostart_status)

    guide_parser = subparsers.add_parser("guide", help="Show first-run BotFather, LLM, module, and Telegram command guide")
    guide_parser.add_argument("--json", action="store_true", help="Emit the guide as structured JSON")
    guide_parser.set_defaults(func=cmd_guide)

    init_parser = subparsers.add_parser("init", help="Scaffold a new Spark module in a directory")
    init_parser.add_argument("name", help="Module name (lowercase + dashes)")
    init_parser.add_argument("--kind", choices=["python", "node"], default="python", help="Runtime kind (default: python)")
    init_parser.add_argument("--path", help="Target directory (default: ./<name>)")
    init_parser.add_argument("--description", help="One-line module description for spark.toml and README")
    init_parser.add_argument("--force", action="store_true", help="Scaffold into a non-empty directory")
    init_parser.set_defaults(func=cmd_init)

    search_parser = subparsers.add_parser("search", help="Search the local blessed registry for modules")
    search_parser.add_argument("query", nargs="?", help="Filter by substring match against name or summary")
    search_parser.set_defaults(func=cmd_search)

    config_parser = subparsers.add_parser("config", help="Read or write user config at ~/.spark/config/config.json")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)

    config_get_parser = config_sub.add_parser("get", help="Print a config value by dotted key")
    config_get_parser.add_argument("key")
    config_get_parser.set_defaults(func=cmd_config_get)

    config_set_parser = config_sub.add_parser("set", help="Set a config value; JSON-parses value if possible")
    config_set_parser.add_argument("key")
    config_set_parser.add_argument("value")
    config_set_parser.set_defaults(func=cmd_config_set)

    config_unset_parser = config_sub.add_parser("unset", help="Remove a config value by dotted key")
    config_unset_parser.add_argument("key")
    config_unset_parser.set_defaults(func=cmd_config_unset)

    config_list_parser = config_sub.add_parser("list", help="Dump full user config as JSON")
    config_list_parser.set_defaults(func=cmd_config_list)

    secrets_parser = subparsers.add_parser("secrets", help="Manage stored secrets (Windows Credential Manager or file fallback)")
    secrets_sub = secrets_parser.add_subparsers(dest="secrets_command", required=True)

    secrets_list_parser = secrets_sub.add_parser("list", help="List stored secret ids and their backend")
    secrets_list_parser.set_defaults(func=cmd_secrets_list)

    secrets_set_parser = secrets_sub.add_parser("set", help="Store or rotate a secret")
    secrets_set_parser.add_argument("secret_id")
    secrets_set_parser.add_argument("--value", help="Pass the value directly (otherwise prompted or read from stdin)")
    secrets_set_parser.add_argument("--backend", choices=["keychain", "file"], default="keychain")
    secrets_set_parser.set_defaults(func=cmd_secrets_set)

    secrets_get_parser = secrets_sub.add_parser("get", help="Read a stored secret (masked by default)")
    secrets_get_parser.add_argument("secret_id")
    secrets_get_parser.add_argument("--reveal", action="store_true", help="Print the full value")
    secrets_get_parser.set_defaults(func=cmd_secrets_get)

    secrets_delete_parser = secrets_sub.add_parser("delete", help="Remove a stored secret")
    secrets_delete_parser.add_argument("secret_id")
    secrets_delete_parser.set_defaults(func=cmd_secrets_delete)

    logs_parser = subparsers.add_parser("logs", help="Show process logs for an installed module")
    logs_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Telegram bot profile logs to read")
    logs_parser.add_argument("target")
    logs_parser.add_argument("-n", "--lines", type=int, default=200, help="Lines of history to show before following (default: 200, 0 = all)")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Tail the log and stream new lines")
    logs_parser.set_defaults(func=cmd_logs)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_state_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
