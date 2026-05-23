from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import hashlib
import io
import ipaddress
import json
import os
import plistlib
import re
import secrets as py_secrets
import shlex
import shutil
import signal
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from xml.sax.saxutils import escape as xml_escape

import tomllib

from .runtime_policy import run_runtime_command, runtime_command_argv, split_single_argv_command
from .security.approval import CommandContext, approval_required_for_command
from .security.prompt_injection import scan_prompt_injection_text
from .security.url_policy import UrlPolicy, validate_url_safety
from .system_map import compile_summary, compile_system_map, write_compiled_outputs

CLI_MAX_SUPPORTED_SCHEMA = 1
DPAPI_SECRET_PREFIX = "dpapi:v1:"
INSECURE_FILE_SECRET_PREFIX = "insecure-local:v1:"
ALLOW_INSECURE_FILE_SECRETS_ENV = "SPARK_ALLOW_INSECURE_FILE_SECRETS"
PRIVATE_FILE_MODE = 0o600
GIT_SHORTHAND_HOSTS = {"github.com", "gitlab.com"}


SPARK_HOME = Path(os.environ.get("SPARK_HOME", Path.home() / ".spark")).expanduser()
STATE_DIR = SPARK_HOME / "state"
CONFIG_DIR = SPARK_HOME / "config"
MODULE_CONFIG_DIR = CONFIG_DIR / "modules"
LOG_DIR = SPARK_HOME / "logs"
REGISTRY_PATH = STATE_DIR / "installed.json"
CONFIG_PATH = STATE_DIR / "setup.json"
SETUP_PENDING_PATH = STATE_DIR / "setup.pending.json"
TELEGRAM_FIRST_MESSAGE_EVENTS_PATH = STATE_DIR / "onboarding" / "telegram-first-message.jsonl"
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
INSTALLER_MANIFEST_PATH = REPO_ROOT / "scripts" / "installer-manifest.json"
INSTALLER_SCRIPT_PATHS = {
    "install.sh": REPO_ROOT / "scripts" / "install.sh",
    "install.ps1": REPO_ROOT / "scripts" / "install.ps1",
}
HOSTED_INSTALLER_URLS = {
    "install.sh": "https://agent.sparkswarm.ai/install.sh",
    "install.ps1": "https://agent.sparkswarm.ai/install.ps1",
}
HOSTED_INSTALLER_CHECKSUMS_URL = "https://agent.sparkswarm.ai/install/checksums.txt"
HOSTED_INSTALLER_COMMANDS_URL = "https://agent.sparkswarm.ai/install/commands.json"
HOSTED_RELEASE_MANIFEST_URL = "https://agent.sparkswarm.ai/install/release-manifest.json"
DEFAULT_TELEGRAM_PROFILE = "default"
DEFAULT_PRIMARY_TELEGRAM_PROFILE = "primary"
PRIMARY_TELEGRAM_PROFILE_KEY = "primary_telegram_profile"
TELEGRAM_PROFILE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$")
AUTOSTART_TARGET_PATTERN = re.compile(r"^[a-z0-9-]+$")
GIT_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
SHELL_INSTALLER_RELEASE_PATTERN = re.compile(r'SPARK_CLI_RELEASE_NAME="\$\{SPARK_CLI_RELEASE_NAME:-([^}]+)\}"')
SHELL_INSTALLER_REF_PATTERN = re.compile(r'SPARK_DEFAULT_CLI_REF="([0-9a-fA-F]{40})"')
POWERSHELL_INSTALLER_RELEASE_PATTERN = re.compile(r'\$SparkCliReleaseName\s*=\s*"([^"]+)"')
POWERSHELL_INSTALLER_REF_PATTERN = re.compile(r'\[string\]\$Ref\s*=\s*"([0-9a-fA-F]{40})"')
TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b")
TELEGRAM_BOT_TOKEN_TIMEOUT_SECONDS = 10
MEMORY_SIDECAR_CHOICES = {"graphiti-kuzu"}
MEMORY_SIDECAR_DISABLE_CHOICES = {"none", "off", "disabled"}
DEFAULT_GRAPHITI_KUZU_DB_PATH = "{home}/sidecars/graphiti/kuzu/graphiti.kuzu"
DEFAULT_GRAPHITI_GROUP_ID = "spark-memory"
VOICE_MODULE_NAME = "spark-voice-comms"
TELEGRAM_VOICE_BUNDLE = "telegram-voice-starter"
SAFE_PARENT_ENV_KEYS = {
    "APPDATA",
    "COMSPEC",
    "EVENTS_API_KEY",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOCALAPPDATA",
    "MCP_API_KEY",
    "PATH",
    "PATHEXT",
    "PORT",
    "SHELL",
    "SPARK_ALLOWED_HOSTS",
    "SPARK_ALLOW_HOSTED_FULL_ACCESS",
    "SPARK_BRIDGE_API_KEY",
    "SPARK_LIVE_CONTAINER",
    "SPARK_SPAWNER_HOST",
    "SPARK_SPAWNER_PORT",
    "SPARK_UI_API_KEY",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
    "USERNAME",
    "USERPROFILE",
    "WINDIR",
}
SAFE_PARENT_ENV_PREFIXES = ("XDG_",)
STATIC_PROVIDER_ENV_BLOCKLIST = {
    "ANTHROPIC_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "GOOGLE_API_KEY",
    "KIMI_API_KEY",
    "MINIMAX_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_URL",
    "TELEGRAM_API_BASE",
    "TELEGRAM_BOT_TOKEN",
    "ZAI_API_KEY",
    "ZAI_BASE_URL",
}
WRITE_DENIED_HOME_PREFIXES = (
    ".aws",
    ".codex",
    ".config/gh",
    ".config/gcloud",
    ".docker",
    ".gnupg",
    ".hermes",
    ".kube",
    ".ssh",
)
WRITE_DENIED_HOME_PATHS = (
    ".spark/config/secrets.local.json",
)
WRITE_DENIED_POSIX_PREFIXES = (
    "/etc",
    "/root",
    "/var/run/docker.sock",
)
TRUST_TIERS = ("builtin", "trusted", "community", "untrusted")
TRUST_BLOCK_THRESHOLD = {
    "builtin": "critical",
    "trusted": "critical",
    "community": "high",
    "untrusted": "medium",
}
CHIP_SCAN_SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
CHIP_SCAN_SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "site-packages",
}
CHIP_SCAN_SKIP_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "uv.lock",
    "yarn.lock",
}
CHIP_SCAN_FIXTURE_DIRS = {
    "__tests__",
    "fixtures",
    "test",
    "tests",
}
CHIP_SCAN_TEXT_SUFFIXES = {
    "",
    ".bat",
    ".cmd",
    ".env",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mdx",
    ".mjs",
    ".ps1",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
CHIP_SCAN_EXECUTABLE_SUFFIXES = {
    ".com",
    ".dll",
    ".dylib",
    ".exe",
    ".pyd",
    ".so",
}
CHIP_SCAN_MAX_FILE_BYTES = 256 * 1024
CHIP_SCAN_MAX_FILES = 500
CHIP_SCAN_MAX_TOTAL_BYTES = 4 * 1024 * 1024
CHIP_SCAN_PATTERNS = (
    (
        "embedded-private-key",
        "critical",
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)?PRIVATE KEY-----"),
        "private key material is embedded in the module",
    ),
    (
        "shell-pipe-installer",
        "high",
        re.compile(r"\b(?:curl|wget|iwr|Invoke-WebRequest)\b[^\n\r|;&]*(?:\||;|&&)[^\n\r]*(?:bash|sh|iex|Invoke-Expression)\b", re.IGNORECASE),
        "remote download is piped into a shell/interpreter",
    ),
    (
        "secret-file-access",
        "high",
        re.compile(r"(?:readFileSync|open|Get-Content|cat)\s*\(?[^\n\r]*(?:\.ssh|id_rsa|secrets\.local\.json|\.aws|\.gnupg|\.env)", re.IGNORECASE),
        "code appears to read credential files directly",
    ),
    (
        "dangerous-recursive-delete",
        "high",
        re.compile(r"\b(?:rm\s+-rf|Remove-Item\b[^\n\r]*\s-Recurse)\b[^\n\r]*(?:~|/|\\|C:)", re.IGNORECASE),
        "code contains a broad recursive delete command",
    ),
    (
        "python-shell-true",
        "medium",
        re.compile(r"subprocess\.(?:run|Popen|call|check_call|check_output)\([^\n\r]*shell\s*=\s*True", re.IGNORECASE),
        "Python subprocess uses shell=True",
    ),
    (
        "encoded-payload-execution",
        "high",
        re.compile(r"(?:base64\s+-(?:d|decode)|FromBase64String|atob)\b[^\n\r]*(?:\||;|&&|`|\))?[^\n\r]*(?:bash|sh|iex|Invoke-Expression|eval|exec)\b", re.IGNORECASE),
        "encoded payload appears to be decoded and executed",
    ),
    (
        "environment-dump",
        "medium",
        re.compile(r"\b(?:printenv|env\s*(?:>|>>|\|)|Get-ChildItem\s+Env:|process\.env|os\.environ)\b[^\n\r]*(?:fetch|axios|curl|wget|Invoke-WebRequest|http://|https://|writeFileSync|open\()", re.IGNORECASE),
        "code appears to dump environment variables to a file or network sink",
    ),
    (
        "network-exfiltration",
        "high",
        re.compile(r"\b(?:curl|wget|Invoke-WebRequest|fetch|axios|requests\.(?:post|put|request))\b[^\n\r]*(?:\.env|secrets\.local\.json|id_rsa|\.ssh|AWS_SECRET_ACCESS_KEY|TELEGRAM_BOT_TOKEN|API_KEY|TOKEN)", re.IGNORECASE),
        "code appears to send secrets or credential files over the network",
    ),
    (
        "install-script-hook",
        "high",
        re.compile(r'"(?:preinstall|install|postinstall)"\s*:\s*"[^"]*(?:curl|wget|Invoke-WebRequest|bash|sh|powershell|node\s+-e|python\s+-c|rm\s+-rf)', re.IGNORECASE),
        "package install hook runs shell/network code",
    ),
)

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
class ChipScanFinding:
    category: str
    severity: str
    path: str
    detail: str

    def format(self) -> str:
        return f"[{self.severity}] {self.category} in {self.path}: {self.detail}"


@dataclass
class SetupBundlePlan:
    modules: dict[str, Module]
    bundle: list[Module]
    ingress_owner: Module
    installed_modules: dict[str, Module]


def load_registry_definition() -> dict[str, Any]:
    registry = load_json(LOCAL_REGISTRY_PATH, {"modules": {}, "bundles": {}})
    validate_registry_definition(registry)
    return registry


def validate_registry_definition(registry: dict[str, Any]) -> None:
    modules = registry.get("modules", {})
    if not isinstance(modules, dict):
        raise SystemExit("Registry `modules` must be an object.")
    for name, metadata in modules.items():
        if not isinstance(metadata, dict):
            raise SystemExit(f"Registry entry `{name}` must be an object.")
        source = str(metadata.get("source", "")).strip()
        if not bool(metadata.get("blessed", False)) or not is_git_source(source):
            continue
        if not validate_commit_pin(str(metadata.get("commit", ""))):
            raise SystemExit(f"Blessed git registry entry `{name}` must include a full commit pin.")


def is_git_source(source: str) -> bool:
    value = (source or "").strip()
    if not value:
        return False
    if value.startswith(("http://", "https://", "git://", "ssh://", "git@")):
        return True
    if value.endswith(".git"):
        return True
    if is_hosted_git_shorthand(value):
        return True
    return False


def is_hosted_git_shorthand(value: str) -> bool:
    parts = value.strip().split("/")
    return len(parts) >= 3 and parts[0].lower() in GIT_SHORTHAND_HOSTS and all(parts[:3])


def normalize_git_url(source: str) -> str:
    value = source.strip()
    if is_hosted_git_shorthand(value):
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


def validate_commit_pin(commit: str | None) -> str | None:
    value = (commit or "").strip()
    if not value:
        return None
    if not GIT_COMMIT_SHA_PATTERN.fullmatch(value):
        raise SystemExit("Registry commit pins must be full 40-character Git SHA-1 values.")
    return value.lower()


def run_git_or_exit(name: str, args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        git_command(*args),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "unknown git error"
        raise SystemExit(f"git operation failed for {name}: {detail}")
    return result


def verify_pinned_commit(name: str, target: Path, commit: str, *, require_signed_commit: bool) -> None:
    verify_result = subprocess.run(
        git_command("-C", str(target), "verify-commit", commit),
        capture_output=True,
        text=True,
    )
    if require_signed_commit and verify_result.returncode != 0:
        detail = (verify_result.stderr or verify_result.stdout).strip() or "commit is not signed or cannot be verified"
        raise SystemExit(f"git signature verification failed for {name} at {commit}: {detail}")
    run_git_or_exit(name, ["-C", str(target), "checkout", "--detach", commit])
    resolved = run_git_or_exit(name, ["-C", str(target), "rev-parse", "HEAD"]).stdout.strip().lower()
    if resolved != commit:
        raise SystemExit(f"git checkout mismatch for {name}: expected {commit}, got {resolved}")


@dataclass
class ModuleProvenanceResult:
    name: str
    source: str
    commit: str
    ok: bool
    signature_enforced: bool
    attestation_present: bool
    detail: str
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "commit": self.commit,
            "ok": self.ok,
            "signature_enforced": self.signature_enforced,
            "attestation_present": self.attestation_present,
            "detail": self.detail,
            "warnings": self.warnings,
        }


class ReportOnlyModuleProvenanceVerifier:
    """Non-enforcing verifier surface for future Sigstore/attestation checks."""

    def attestation_warnings(self, metadata: dict[str, Any], *, source: str, commit: str) -> list[str]:
        raw = metadata.get("attestation")
        if raw is None and metadata.get("attestation_ref"):
            return []
        if raw is None:
            return ["module attestation is not declared yet"]
        if not isinstance(raw, dict):
            return ["module attestation must be an object"]
        warnings: list[str] = []
        attestation_type = str(raw.get("type") or "").strip()
        if attestation_type != "git-commit-pin-v1":
            warnings.append("module attestation type must be git-commit-pin-v1")
        attested_source = str(raw.get("source") or "").strip()
        if attested_source != source:
            warnings.append("module attestation source does not match registry source")
        attested_commit = str(raw.get("commit") or "").strip().lower()
        if attested_commit != commit.lower():
            warnings.append("module attestation commit does not match registry commit")
        return warnings

    def verify_registry_entry(self, name: str, metadata: dict[str, Any]) -> ModuleProvenanceResult:
        source = str(metadata.get("source", "")).strip()
        commit = str(metadata.get("commit", "")).strip()
        signature_enforced = bool(metadata.get("require_signed_commit", False))
        attestation_present = bool(metadata.get("attestation") or metadata.get("attestation_ref"))
        warnings: list[str] = []
        ok = True
        if not is_git_source(source):
            ok = False
            warnings.append("module source is not a git URL")
        try:
            pinned_commit = validate_commit_pin(commit)
        except SystemExit:
            ok = False
            warnings.append("module is missing a full commit pin")
        else:
            if not pinned_commit:
                ok = False
                warnings.append("module is missing a full commit pin")
        if not signature_enforced:
            warnings.append("commit signature enforcement is report-only")
        warnings.extend(self.attestation_warnings(metadata, source=source, commit=commit))
        if any("attestation" in warning for warning in warnings):
            ok = False
        detail = (
            "Commit pin and attestation metadata are present; signature verification is report-only."
            if ok
            else "Module provenance metadata is incomplete."
        )
        return ModuleProvenanceResult(
            name=name,
            source=source,
            commit=commit,
            ok=ok,
            signature_enforced=signature_enforced,
            attestation_present=attestation_present,
            detail=detail,
            warnings=warnings,
        )


def clone_module_source(
    name: str,
    source: str,
    *,
    commit: str | None = None,
    require_signed_commit: bool = False,
) -> Path:
    target = clone_target_for_module(name)
    if (target / "spark.toml").exists() and (target / ".git").exists():
        pinned_commit = validate_commit_pin(commit)
        if pinned_commit:
            resolved = subprocess.run(
                git_command("-C", str(target), "rev-parse", "HEAD"),
                capture_output=True,
                text=True,
            )
            if resolved.returncode != 0 or resolved.stdout.strip().lower() != pinned_commit:
                raise SystemExit(
                    f"Installed clone for {name} is not at pinned commit {pinned_commit}. "
                    "Run `spark uninstall` for the module and reinstall it."
                )
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not (target / ".git").exists():
        raise SystemExit(
            f"Cannot clone {name}: {target} exists but is not a git checkout. Remove it first."
        )
    url = normalize_git_url(source)
    pinned_commit = validate_commit_pin(commit)
    if pinned_commit:
        target.mkdir(parents=True, exist_ok=True)
        run_git_or_exit(name, ["-C", str(target), "init", "-q"])
        run_git_or_exit(name, ["-C", str(target), "remote", "add", "origin", url])
        run_git_or_exit(name, ["-C", str(target), "fetch", "--depth=1", "origin", pinned_commit])
        verify_pinned_commit(name, target, pinned_commit, require_signed_commit=require_signed_commit)
        return target
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


def update_module_source(module: Module) -> tuple[bool, str]:
    registry_metadata = load_registry_definition().get("modules", {}).get(module.name, {})
    source = str(registry_metadata.get("source", ""))
    pinned_commit = validate_commit_pin(str(registry_metadata.get("commit", "")))
    if not (is_git_source(source) and pinned_commit):
        return pull_module_source(module.path)

    status = subprocess.run(
        git_command("-C", str(module.path), "status", "--porcelain"),
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return False, summarize_command_output(status)
    if status.stdout.strip():
        return False, "working tree has local changes; commit or stash them before updating"

    current = subprocess.run(
        git_command("-C", str(module.path), "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
    )
    if current.returncode != 0:
        return False, summarize_command_output(current)
    current_commit = current.stdout.strip().lower()
    if current_commit == pinned_commit:
        return True, f"already at pinned commit {pinned_commit[:12]}"

    fetch = subprocess.run(
        git_command("-C", str(module.path), "fetch", "--depth=1", "origin", pinned_commit),
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        return False, summarize_command_output(fetch)

    if bool(registry_metadata.get("require_signed_commit", False)):
        verify = subprocess.run(
            git_command("-C", str(module.path), "verify-commit", pinned_commit),
            capture_output=True,
            text=True,
        )
        if verify.returncode != 0:
            return False, summarize_command_output(verify)

    checkout = subprocess.run(
        git_command("-C", str(module.path), "checkout", "--detach", pinned_commit),
        capture_output=True,
        text=True,
    )
    if checkout.returncode != 0:
        return False, summarize_command_output(checkout)

    resolved = subprocess.run(
        git_command("-C", str(module.path), "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
    )
    if resolved.returncode != 0:
        return False, summarize_command_output(resolved)
    if resolved.stdout.strip().lower() != pinned_commit:
        return False, f"checkout mismatch: expected {pinned_commit}, got {resolved.stdout.strip()}"
    return True, f"checked out pinned commit {current_commit[:12]}..{pinned_commit[:12]}"


def is_dirty_update_failure(detail: str) -> bool:
    lowered = str(detail or "").lower()
    return (
        "working tree has local changes" in lowered
        or "commit or stash" in lowered
        or "local changes would be overwritten" in lowered
    )


def module_git_status(module: Module) -> tuple[bool, str]:
    result = subprocess.run(
        git_command("-C", str(module.path), "status", "--porcelain"),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stdout.strip() if result.returncode == 0 else summarize_command_output(result)


def dirty_update_modules(modules: list[Module]) -> list[tuple[Module, str]]:
    dirty: list[tuple[Module, str]] = []
    for module in modules:
        if not module_is_git_managed(module.path):
            continue
        ok, detail = module_git_status(module)
        if not ok:
            dirty.append((module, detail))
        elif detail:
            dirty.append((module, detail))
    return dirty


def stash_module_local_changes(module: Module) -> tuple[bool, str]:
    label = datetime.now(timezone.utc).strftime("spark-update-local-runtime-%Y%m%dT%H%M%SZ")
    result = subprocess.run(
        git_command("-C", str(module.path), "stash", "push", "-u", "-m", label),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, summarize_command_output(result) or label


def print_dirty_update_preflight(dirty: list[tuple[Module, str]]) -> None:
    print("Update preflight found local runtime edits before touching services:")
    for module, detail in dirty:
        summary = " ".join(str(detail or "").splitlines()).strip()
        if len(summary) > 140:
            summary = f"{summary[:137]}..."
        print(f"  - {module.name}: {summary or 'working tree has local changes'}")
    print("")
    print("Choose one:")
    print("  spark update --stash-local-runtime")
    print("  spark update --skip-dirty")
    print("  commit or stash the module edits manually, then run spark update --continue")


def update_should_restart_live(args: argparse.Namespace, stopped_processes: list[str]) -> bool:
    if not stopped_processes:
        return False
    if getattr(args, "no_live_restart", False):
        return False
    return os.environ.get("SPARK_AUTOSTART", "0").strip().lower() in {"1", "true", "yes", "on"}


def print_update_live_status_summary() -> int:
    payload = collect_status_payload()
    ok = bool(payload.get("ok"))
    print("")
    print("Post-update live state:")
    print(f"  Spark Live: {'OK' if ok else 'needs attention'}")
    profiles = payload.get("telegram_profiles")
    if isinstance(profiles, list):
        running = [item for item in profiles if isinstance(item, dict) and item.get("running")]
        stopped = [item for item in profiles if isinstance(item, dict) and not item.get("running")]
        print(f"  Telegram profiles: {len(running)} running, {len(stopped)} stopped")
    modules = payload.get("modules") if isinstance(payload.get("modules"), list) else []
    for name in ["spawner-ui", "spark-telegram-bot"]:
        module = next((item for item in modules if isinstance(item, dict) and item.get("name") == name), None)
        if isinstance(module, dict):
            state = "OK" if module.get("healthy") else "attention"
            print(f"  {name}: {state}")
    if not ok and payload.get("repair_hints"):
        print("  Repair:")
        for hint in payload.get("repair_hints", [])[:2]:
            print(f"    - {hint}")
    return 0 if ok else 1


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
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


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


def split_windows_path_entries(path_value: str | None) -> list[str]:
    return [part for part in (path_value or "").split(";") if part and part.strip()]


def remove_windows_path_entry(path_value: str | None, entry: Path) -> tuple[str, bool]:
    target = str(entry).rstrip("\\/").casefold()
    kept: list[str] = []
    removed = False
    for part in split_windows_path_entries(path_value):
        if part.strip().rstrip("\\/").casefold() == target:
            removed = True
            continue
        kept.append(part)
    return ";".join(kept), removed


def remove_spark_bin_from_windows_user_path(spark_home: Path = SPARK_HOME) -> bool:
    bin_dir = spark_home / "bin"
    user_path = os.environ.get("Path", "")
    if sys.platform == "win32":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                user_path, _ = winreg.QueryValueEx(key, "Path")
        except (OSError, ImportError):
            user_path = os.environ.get("Path", "")
    new_path, removed = remove_windows_path_entry(user_path, bin_dir)
    if removed and sys.platform == "win32":
        os.environ["Path"] = new_path
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
        except (OSError, ImportError) as exc:
            raise SystemExit(f"Could not update Windows user PATH: {exc}") from exc
    return removed


def safe_spark_home_for_purge(spark_home: Path = SPARK_HOME) -> Path:
    resolved = spark_home.expanduser().resolve()
    home = Path.home().expanduser().resolve()
    repo_root = REPO_ROOT.resolve()
    root = Path(resolved.anchor).resolve()
    if resolved == root or resolved == home or resolved == repo_root:
        raise SystemExit(f"Refusing to purge unsafe Spark home path: {resolved}")
    return resolved


def purge_spark_home(spark_home: Path = SPARK_HOME) -> bool:
    target = safe_spark_home_for_purge(spark_home)
    if not target.exists():
        return False
    remove_tree(target)
    return True


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


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt32() -> Any:
    return ctypes.windll.crypt32


def _kernel32() -> Any:
    return ctypes.windll.kernel32


def dpapi_protect(value: str) -> str:
    if os.name != "nt":
        if not allow_insecure_file_secrets():
            raise RuntimeError(
                "File secret backend is disabled because this OS has no built-in Spark file encryption. "
                "Install/configure a keyring backend, or set "
                f"{ALLOW_INSECURE_FILE_SECRETS_ENV}=1 only for disposable local tests."
            )
        return INSECURE_FILE_SECRET_PREFIX + base64.b64encode(value.encode("utf-8")).decode("ascii")
    raw = value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    in_blob = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = _DataBlob()
    if not _crypt32().CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise OSError("CryptProtectData failed")
    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _kernel32().LocalFree(out_blob.pbData)
    return DPAPI_SECRET_PREFIX + base64.b64encode(protected).decode("ascii")


def dpapi_unprotect(value: str) -> str:
    if value.startswith(INSECURE_FILE_SECRET_PREFIX):
        encoded = value[len(INSECURE_FILE_SECRET_PREFIX) :]
        return base64.b64decode(encoded).decode("utf-8")
    if os.name != "nt" or not value.startswith(DPAPI_SECRET_PREFIX):
        return value
    protected = base64.b64decode(value[len(DPAPI_SECRET_PREFIX) :])
    buffer = ctypes.create_string_buffer(protected)
    in_blob = _DataBlob(len(protected), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = _DataBlob()
    if not _crypt32().CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise OSError("CryptUnprotectData failed")
    try:
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _kernel32().LocalFree(out_blob.pbData)
    return raw.decode("utf-8")


def allow_insecure_file_secrets() -> bool:
    value = os.environ.get(ALLOW_INSECURE_FILE_SECRETS_ENV, "").strip().lower()
    return value in {"1", "true", "yes"}


def harden_secret_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if os.name != "nt" or not path.exists():
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME', '')}:F"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        pass


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
    try:
        file_secrets[secret_id] = dpapi_protect(value)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    save_json(SECRETS_FILE_PATH, file_secrets)
    harden_secret_file(SECRETS_FILE_PATH)
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
        value = load_json(SECRETS_FILE_PATH, {}).get(secret_id)
        return dpapi_unprotect(value) if isinstance(value, str) else None
    return None


def is_telegram_bot_token_secret(secret_id: str) -> bool:
    return secret_id == "telegram.bot_token" or (
        secret_id.startswith("telegram.profiles.") and secret_id.endswith(".bot_token")
    )


def validate_telegram_bot_token(token: str, *, secret_id: str = "telegram.bot_token") -> dict[str, Any]:
    """Validate a Telegram bot token with getMe before persisting it."""
    token = extract_telegram_bot_token(token)
    quoted_token = urllib.parse.quote(token, safe=":")
    url = f"https://api.telegram.org/bot{quoted_token}/getMe"
    repair_command = telegram_token_repair_command(secret_id)
    try:
        with urllib.request.urlopen(url, timeout=TELEGRAM_BOT_TOKEN_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in {401, 404}:
            raise SystemExit(
                f"Telegram rejected the bot token for {secret_id}. Nothing was changed. "
                f"Open @BotFather, copy only the new token, then rerun `{repair_command}` and paste it when Spark asks. "
                "Use --skip-telegram-token-check only for offline development."
            )
        raise SystemExit(
            f"Telegram token validation failed for {secret_id}: HTTP {error.code}. "
            "Nothing was changed. Try again, or use --skip-telegram-token-check only for offline development."
        )
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"Telegram token validation could not reach Telegram for {secret_id}: {error.__class__.__name__}. "
            "Nothing was changed. Check the network, then retry; use --skip-telegram-token-check only for offline development."
        )
    if not payload.get("ok"):
        description = str(payload.get("description") or "token rejected")
        raise SystemExit(
            f"Telegram rejected the bot token for {secret_id}: {description}. Nothing was changed. "
            f"Open @BotFather, copy only the new token, then rerun `{repair_command}` and paste it when Spark asks."
        )
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def validate_new_telegram_bot_tokens(args: argparse.Namespace, secret_values: dict[str, str]) -> None:
    if getattr(args, "skip_telegram_token_check", False):
        return
    validated_values: set[str] = set()
    for secret_id, token in sorted(secret_values.items()):
        if not token or not is_telegram_bot_token_secret(secret_id):
            continue
        token = extract_telegram_bot_token(token)
        secret_values[secret_id] = token
        if fetch_secret(secret_id) == token:
            continue
        if token in validated_values:
            continue
        validate_telegram_bot_token(token, secret_id=secret_id)
        validated_values.add(token)


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
            harden_secret_file(SECRETS_FILE_PATH)
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


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _path_is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attrs = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def assert_no_linked_write_path(path: Path) -> None:
    expanded = path.expanduser()
    chain = [*reversed(expanded.parent.parents), expanded.parent]
    if expanded.exists() or expanded.is_symlink():
        chain.append(expanded)
    for item in chain:
        if not item.exists() and not item.is_symlink():
            continue
        if _path_is_reparse_point(item):
            raise SystemExit(f"Refusing private write through linked path: {item}")


def installer_release_pins() -> dict[str, Any]:
    shell = INSTALLER_SCRIPT_PATHS["install.sh"].read_text(encoding="utf-8")
    powershell = INSTALLER_SCRIPT_PATHS["install.ps1"].read_text(encoding="utf-8")
    return installer_release_pins_from_text(shell, powershell)


def installer_release_pins_from_text(shell: str, powershell: str) -> dict[str, Any]:
    shell_release = SHELL_INSTALLER_RELEASE_PATTERN.search(shell)
    shell_ref = SHELL_INSTALLER_REF_PATTERN.search(shell)
    powershell_release = POWERSHELL_INSTALLER_RELEASE_PATTERN.search(powershell)
    powershell_ref = POWERSHELL_INSTALLER_REF_PATTERN.search(powershell)
    return {
        "releaseName": shell_release.group(1) if shell_release else "",
        "ref": shell_ref.group(1).lower() if shell_ref else "",
        "installers": {
            "install.sh": {
                "releaseName": shell_release.group(1) if shell_release else "",
                "ref": shell_ref.group(1).lower() if shell_ref else "",
            },
            "install.ps1": {
                "releaseName": powershell_release.group(1) if powershell_release else "",
                "ref": powershell_ref.group(1).lower() if powershell_ref else "",
            },
        },
    }


def installer_pin_for_script(name: str, text: str) -> dict[str, str]:
    release_pattern = SHELL_INSTALLER_RELEASE_PATTERN if name == "install.sh" else POWERSHELL_INSTALLER_RELEASE_PATTERN
    ref_pattern = SHELL_INSTALLER_REF_PATTERN if name == "install.sh" else POWERSHELL_INSTALLER_REF_PATTERN
    release = release_pattern.search(text)
    ref = ref_pattern.search(text)
    return {
        "releaseName": release.group(1) if release else "",
        "ref": ref.group(1).lower() if ref else "",
    }


def current_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    commit = result.stdout.strip().lower()
    if result.returncode != 0 or not GIT_COMMIT_SHA_PATTERN.fullmatch(commit):
        return ""
    return commit


def local_git_commit_exists(ref: str) -> bool:
    normalized = (ref or "").strip().lower()
    if not GIT_COMMIT_SHA_PATTERN.fullmatch(normalized):
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{normalized}^{{commit}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def installer_manifest_payload() -> dict[str, Any]:
    return {
        "schema": 1,
        "source": {
            "repository": "https://github.com/vibeforge1111/spark-cli",
            **{key: value for key, value in installer_release_pins().items() if key in {"releaseName", "ref"}},
        },
        "installers": {
            name: {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
            }
            for name, path in INSTALLER_SCRIPT_PATHS.items()
        },
    }


def hosted_installer_bytes(name: str, url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "spark-cli/0.1 installer-integrity",
            "Accept": "text/plain,*/*",
        },
    )
    with installer_urlopen(request, timeout=20) as response:
        return response.read()


def hosted_installer_sha256(name: str, url: str) -> str:
    return sha256_bytes(hosted_installer_bytes(name, url))


def hosted_installer_checksums() -> dict[str, str]:
    request = urllib.request.Request(
        HOSTED_INSTALLER_CHECKSUMS_URL,
        headers={
            "User-Agent": "spark-cli/0.1 installer-integrity",
            "Accept": "text/plain,*/*",
        },
    )
    with installer_urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    checksums: dict[str, str] = {}
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        digest, relpath = line.split(maxsplit=1)
        checksums[Path(relpath).name] = digest.lower()
    return checksums


def hosted_json_payload(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "spark-cli/0.1 installer-integrity",
            "Accept": "application/json,*/*",
        },
    )
    with installer_urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    parsed = json.loads(payload)
    return parsed if isinstance(parsed, dict) else {}


def installer_ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi  # type: ignore[import-not-found]
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def installer_urlopen(request: urllib.request.Request, *, timeout: int):
    context = installer_ssl_context()
    if context is None:
        return urllib.request.urlopen(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def collect_installer_integrity_payload(*, hosted: bool = False) -> dict[str, Any]:
    manifest = load_json(INSTALLER_MANIFEST_PATH, {})
    installers = manifest.get("installers") if isinstance(manifest, dict) else None
    manifest_source = manifest.get("source") if isinstance(manifest, dict) else None
    expected_release = str(manifest_source.get("releaseName", "")) if isinstance(manifest_source, dict) else ""
    expected_ref = str(manifest_source.get("ref", "")).lower() if isinstance(manifest_source, dict) else ""
    expected_hosted_release = expected_release
    expected_hosted_ref = expected_ref
    hosted_source_basis = "committed_manifest"
    local_source = installer_release_pins()
    checks: list[dict[str, Any]] = []
    source_ok = (
        bool(expected_release)
        and bool(expected_ref)
        and expected_release == local_source["installers"]["install.sh"]["releaseName"]
        and expected_release == local_source["installers"]["install.ps1"]["releaseName"]
        and expected_ref == local_source["installers"]["install.sh"]["ref"]
        and expected_ref == local_source["installers"]["install.ps1"]["ref"]
    )
    checks.append(
        {
            "name": "local_release_metadata",
            "ok": source_ok,
            "expected_release": expected_release,
            "actual_release": local_source["releaseName"],
            "expected_ref": expected_ref,
            "actual_ref": local_source["ref"],
            "detail": (
                "Installer release pins match committed installer manifest metadata."
                if source_ok
                else "Installer release pins do not match committed installer manifest metadata."
            ),
        }
    )
    hosted_expected: dict[str, str] = {}
    hosted_metadata_error = ""
    hosted_release_name = ""
    hosted_release_ref = ""
    hosted_release_manifest: dict[str, Any] = {}
    hosted_release_manifest_error = ""
    committed_expected: dict[str, str] = {}
    if hosted:
        try:
            hosted_expected = hosted_installer_checksums()
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            hosted_metadata_error = str(exc)
        try:
            hosted_release_manifest = hosted_json_payload(HOSTED_RELEASE_MANIFEST_URL)
            spark_cli = (
                hosted_release_manifest.get("sparkCli")
                if isinstance(hosted_release_manifest.get("sparkCli"), dict)
                else {}
            )
            hosted_release_name = str(spark_cli.get("releaseName", ""))
            hosted_release_ref = str(spark_cli.get("commit", "")).lower()
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
            hosted_release_manifest_error = str(exc)
        current_ref = current_git_commit()
        if hosted_release_ref and hosted_release_ref == current_ref and hosted_release_ref != expected_ref:
            expected_hosted_release = hosted_release_name
            expected_hosted_ref = hosted_release_ref
            hosted_source_basis = "installed_checkout"
    local_ref_skipped = hosted and hosted_source_basis == "installed_checkout"
    local_ref_ok = local_ref_skipped or (bool(expected_ref) and local_git_commit_exists(expected_ref))
    checks.append(
        {
            "name": "local_release_ref_reachable",
            "ok": local_ref_ok,
            "expected_ref": expected_ref,
            "detail": (
                "Installer source commit reachability was skipped because hosted metadata matches the installed checkout."
                if local_ref_skipped
                else (
                    "Installer source commit exists in the local Spark CLI checkout."
                    if local_ref_ok
                    else "Installer source commit is not reachable in the local Spark CLI checkout; a fresh install may fail."
                )
            ),
        }
    )
    for name, path in INSTALLER_SCRIPT_PATHS.items():
        expected = ""
        if isinstance(installers, dict) and isinstance(installers.get(name), dict):
            expected = str(installers[name].get("sha256", "")).lower()
        committed_expected[name] = expected
        actual = sha256_file(path).lower() if path.exists() else ""
        local_ok = bool(expected) and actual == expected
        checks.append(
            {
                "name": f"local_{name}",
                "ok": local_ok,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "detail": (
                    f"{name} matches committed installer manifest."
                    if local_ok
                    else f"{name} does not match committed installer manifest."
                ),
            }
        )
        if hosted:
            url = HOSTED_INSTALLER_URLS[name]
            expected_hosted = hosted_expected.get(name, "")
            hosted_pins = {"releaseName": "", "ref": ""}
            if hosted_metadata_error:
                hosted_hash = "<fetch failed>"
                hosted_ok = False
                detail = f"Could not fetch hosted installer checksum metadata: {hosted_metadata_error}"
            else:
                try:
                    hosted_payload = hosted_installer_bytes(name, url)
                    hosted_hash = sha256_bytes(hosted_payload).lower()
                    hosted_text = hosted_payload.decode("utf-8-sig", errors="replace")
                    hosted_pins = installer_pin_for_script(name, hosted_text)
                    hosted_checksum_ok = (
                        bool(expected_hosted)
                        and hosted_hash == expected_hosted
                        and (expected_hosted == expected or hosted_source_basis == "installed_checkout")
                    )
                    hosted_release_ok = hosted_pins["releaseName"] == expected_hosted_release
                    hosted_ref_ok = hosted_pins["ref"] == expected_hosted_ref
                    hosted_ok = hosted_checksum_ok and hosted_release_ok and hosted_ref_ok
                    detail = (
                        f"{url} matches hosted checksum metadata and installs the expected Spark CLI source."
                        if hosted_ok
                        else f"{url} does not match hosted checksum metadata or expected Spark CLI source pins."
                    )
                except (OSError, urllib.error.URLError, TimeoutError) as exc:
                    hosted_hash = "<fetch failed>"
                    hosted_ok = False
                    detail = f"Could not fetch {url}: {exc}"
            checks.append(
                {
                    "name": f"hosted_{name}",
                    "ok": hosted_ok,
                    "expected_sha256": expected_hosted,
                    "actual_sha256": hosted_hash,
                    "hosted_metadata_sha256": expected_hosted,
                    "committed_manifest_sha256": expected,
                    "expected_release": expected_hosted_release,
                    "actual_release": hosted_pins.get("releaseName", ""),
                    "expected_ref": expected_hosted_ref,
                    "actual_ref": hosted_pins.get("ref", ""),
                    "expected_source_basis": hosted_source_basis,
                    "url": url,
                    "checksum_url": HOSTED_INSTALLER_CHECKSUMS_URL,
                    "detail": (
                        detail
                        if hosted_ok
                        else (
                            f"{detail} Expected hosted sha {expected_hosted or '<missing>'}; "
                            f"committed manifest sha {expected or '<missing>'}; "
                            f"hosted metadata sha {expected_hosted or '<missing>'}; "
                            f"hosted byte sha {hosted_hash}; "
                            f"expected source {expected_hosted_release}@{expected_hosted_ref}; "
                            f"hosted script source {hosted_pins.get('releaseName', '')}@{hosted_pins.get('ref', '')}."
                        )
                    ),
                }
            )
    if hosted:
        if hosted_release_manifest_error:
            checks.append(
                {
                    "name": "hosted_release_manifest",
                    "ok": False,
                    "url": HOSTED_RELEASE_MANIFEST_URL,
                    "detail": f"Could not fetch hosted release manifest: {hosted_release_manifest_error}",
                }
            )
        else:
            spark_cli = (
                hosted_release_manifest.get("sparkCli")
                if isinstance(hosted_release_manifest.get("sparkCli"), dict)
                else {}
            )
            release_ok = spark_cli.get("releaseName") == expected_hosted_release and hosted_release_ref == expected_hosted_ref
            checks.append(
                {
                    "name": "hosted_release_manifest",
                    "ok": release_ok,
                    "expected_release": expected_hosted_release,
                    "actual_release": str(spark_cli.get("releaseName", "")),
                    "expected_ref": expected_hosted_ref,
                    "actual_ref": hosted_release_ref,
                    "expected_source_basis": hosted_source_basis,
                    "url": HOSTED_RELEASE_MANIFEST_URL,
                    "detail": (
                        "Hosted release manifest has the current release name and expected Spark CLI commit."
                        if release_ok
                        else "Hosted release manifest is stale or does not match the expected Spark CLI commit."
                    ),
                }
            )
        try:
            commands = hosted_json_payload(HOSTED_INSTALLER_COMMANDS_URL)
            source = commands.get("source") if isinstance(commands.get("source"), dict) else {}
            command_hashes = commands.get("checksums", {}).get("sha256", {}) if isinstance(commands.get("checksums"), dict) else {}
            command_ref = str(source.get("ref", "")).lower()
            commands_ok = (
                source.get("releaseName") == expected_hosted_release
                and command_ref == expected_hosted_ref
                and (not hosted_release_ref or command_ref == hosted_release_ref)
                and command_hashes == hosted_expected
                and (command_hashes == committed_expected or hosted_source_basis == "installed_checkout")
            )
            commands_detail = "Hosted command metadata matches installer hashes and release pins."
            if not commands_ok:
                commands_detail = (
                    "Hosted command metadata is stale or does not match installer hashes and release pins. "
                    f"Expected hashes {hosted_expected}; hosted hashes {command_hashes}; "
                    f"expected release/ref {expected_hosted_release}@{expected_hosted_ref}; "
                    f"hosted command release/ref {source.get('releaseName')}@{command_ref}; "
                    f"hosted release-manifest ref {hosted_release_ref or '<missing>'}."
                )
            checks.append(
                {
                    "name": "hosted_commands_metadata",
                    "ok": commands_ok,
                    "expected_release": expected_hosted_release,
                    "actual_release": str(source.get("releaseName", "")),
                    "expected_ref": expected_hosted_ref,
                    "actual_ref": command_ref,
                    "expected_source_basis": hosted_source_basis,
                    "url": HOSTED_INSTALLER_COMMANDS_URL,
                    "detail": commands_detail,
                }
            )
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
            checks.append(
                {
                    "name": "hosted_commands_metadata",
                    "ok": False,
                    "url": HOSTED_INSTALLER_COMMANDS_URL,
                    "detail": f"Could not fetch hosted command metadata: {exc}",
                }
            )
    try:
        manifest_label = str(INSTALLER_MANIFEST_PATH.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        manifest_label = str(INSTALLER_MANIFEST_PATH)
    return {
        "ok": all(check["ok"] for check in checks),
        "summary": "Spark installer integrity verification",
        "manifest": manifest_label,
        "checks": checks,
    }


def collect_module_provenance_payload(
    *,
    registry: dict[str, Any] | None = None,
    verifier: ReportOnlyModuleProvenanceVerifier | None = None,
) -> dict[str, Any]:
    registry_payload = registry if registry is not None else load_registry_definition()
    modules = registry_payload.get("modules", {}) if isinstance(registry_payload, dict) else {}
    verifier = verifier or ReportOnlyModuleProvenanceVerifier()
    checks: list[dict[str, Any]] = []
    for name, metadata in sorted(modules.items()):
        if not isinstance(metadata, dict) or not bool(metadata.get("blessed", False)):
            continue
        result = verifier.verify_registry_entry(str(name), metadata)
        checks.append(result.as_dict())
    return {
        "ok": all(check["ok"] for check in checks),
        "summary": "Spark module provenance report",
        "mode": "metadata_required",
        "enforcement": {
            "commit_pins": "required",
            "signed_commits": "report_only",
            "attestations": "required",
        },
        "checks": checks,
    }


def resolve_remote_git_ref(source: str, ref: str = "HEAD") -> str:
    remote_ref = (ref or "HEAD").strip() or "HEAD"
    result = subprocess.run(
        git_command("ls-remote", normalize_git_url(source), remote_ref),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "unknown git error"
        raise RuntimeError(detail)
    first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
    commit = first_line.split()[0].strip().lower() if first_line else ""
    if not validate_commit_pin(commit):
        raise RuntimeError(f"remote {remote_ref} did not resolve to a full commit SHA")
    return commit


def resolve_remote_git_head(source: str) -> str:
    return resolve_remote_git_ref(source, "HEAD")


def collect_registry_pin_drift_payload(
    *,
    registry: dict[str, Any] | None = None,
    resolver: Callable[..., str] | None = None,
) -> dict[str, Any]:
    registry_payload = registry if registry is not None else load_registry_definition()
    modules = registry_payload.get("modules", {}) if isinstance(registry_payload, dict) else {}
    resolver = resolver or resolve_remote_git_ref
    checks: list[dict[str, Any]] = []
    for name, metadata in sorted(modules.items()):
        if not isinstance(metadata, dict) or not bool(metadata.get("blessed", False)):
            continue
        source = str(metadata.get("source", "")).strip()
        if not is_git_source(source):
            continue
        pinned = str(metadata.get("commit", "")).strip().lower()
        remote_ref = str(metadata.get("verify_ref") or metadata.get("release_ref") or "HEAD").strip() or "HEAD"
        try:
            validate_commit_pin(pinned)
            try:
                remote = resolver(source, remote_ref).strip().lower()
            except TypeError:
                if remote_ref != "HEAD":
                    raise
                remote = resolver(source).strip().lower()
            validate_commit_pin(remote)
        except (RuntimeError, SystemExit) as error:
            checks.append(
                {
                    "name": str(name),
                    "source": source,
                    "pinned_commit": pinned,
                    "remote_ref": remote_ref,
                    "remote_head": "",
                    "ok": False,
                    "detail": f"Could not verify remote {remote_ref}: {error}",
                }
            )
            continue
        ok = pinned == remote
        remote_label = "remote HEAD" if remote_ref == "HEAD" else f"remote {remote_ref}"
        checks.append(
            {
                "name": str(name),
                "source": source,
                "pinned_commit": pinned,
                "remote_ref": remote_ref,
                "remote_head": remote,
                "ok": ok,
                "detail": f"registry pin matches {remote_label}" if ok else f"registry pin lags or diverges from {remote_label}",
            }
        )
    return {
        "ok": all(check["ok"] for check in checks),
        "summary": "Spark registry pin drift verification",
        "checks": checks,
    }


def atomic_write_json(path: Path, payload: Any) -> None:
    assert_no_linked_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{py_secrets.token_hex(4)}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(temp_path, PRIVATE_FILE_MODE)
        except OSError:
            pass
        os.replace(temp_path, path)
        try:
            os.chmod(path, PRIVATE_FILE_MODE)
        except OSError:
            pass
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def save_json(path: Path, payload: Any) -> None:
    atomic_write_json(path, payload)


def load_module(path: Path) -> Module:
    manifest_path = path / "spark.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    name = str(manifest.get("module", {}).get("name") or path.name)
    return Module(name=name, path=path, manifest=manifest)


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_onboarding_session_code() -> str:
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"
    return "ember-" + "".join(py_secrets.choice(alphabet) for _ in range(4))


def save_pending_setup_state(stage: str, detail: str, setup_state: dict[str, Any] | None = None) -> None:
    pending = {
        "event": "setup_pending",
        "updated_at": timestamp_now(),
        "stage": stage,
        "detail": detail,
        "ready": ["Spark command installed"],
        "still_needed": [
            "Telegram bot was not verified",
            "Spark modules may not be installed",
            "Spark bot is not running",
        ],
        "next": "spark setup telegram-starter --resume",
    }
    if isinstance(setup_state, dict):
        pending["bundle"] = setup_state.get("bundle")
        pending["modules"] = setup_state.get("modules")
        pending["telegram_ingress_owner"] = setup_state.get("telegram_ingress_owner")
        pending["onboarding_session"] = setup_state.get("onboarding_session")
    save_json(SETUP_PENDING_PATH, pending)


def clear_pending_setup_state() -> None:
    try:
        SETUP_PENDING_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def load_pending_setup_state() -> dict[str, Any]:
    if not SETUP_PENDING_PATH.exists():
        return {}
    pending = load_json(SETUP_PENDING_PATH, {})
    return pending if isinstance(pending, dict) else {}


def print_setup_failure_truth_screen(detail: str) -> None:
    print("")
    print("Spark is not ready yet.")
    print("")
    print("Ready:")
    print("  Spark command installed")
    print("")
    print("Still needed:")
    print("  Telegram bot was not verified")
    print("  Spark bot is not running")
    print("")
    print("Next:")
    print("  spark setup telegram-starter --resume")
    print("  spark fix telegram")
    if detail:
        print("")
        print(f"Why setup stopped: {detail}")


def read_telegram_first_message_events(path: Path | None = None) -> list[dict[str, Any]]:
    event_path = path or TELEGRAM_FIRST_MESSAGE_EVENTS_PATH
    if not event_path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in event_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    except OSError:
        return []
    return events


def telegram_first_message_seen(
    session: str,
    path: Path | None = None,
) -> dict[str, Any]:
    normalized = str(session or "").strip()
    for event in reversed(read_telegram_first_message_events(path)):
        if event.get("event") != "telegram_first_message":
            continue
        if normalized and str(event.get("session") or "").strip() != normalized:
            continue
        return {
            "received": True,
            "replied": bool(event.get("replied")),
            "session": str(event.get("session") or ""),
            "chat_id": event.get("chat_id"),
            "user_id": event.get("user_id"),
            "event": event,
        }
    return {"received": False, "replied": False, "session": normalized}


def wait_for_telegram_first_message(
    session: str,
    timeout_seconds: int,
    path: Path | None = None,
    *,
    poll_seconds: float = 1.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, int(timeout_seconds))
    while True:
        result = telegram_first_message_seen(session, path)
        if result.get("received"):
            result["timed_out"] = False
            return result
        if time.monotonic() >= deadline:
            result["timed_out"] = True
            return result
        time.sleep(max(0.1, poll_seconds))


def first_message_wait_seconds(args: argparse.Namespace, interactive: bool) -> int:
    if not getattr(args, "wait_first_message", True):
        return 0
    explicit = getattr(args, "wait_first_message_seconds", None)
    if explicit is not None:
        return max(0, int(explicit))
    return 60 if interactive else 0


def print_first_message_wait_result(result: dict[str, Any]) -> None:
    if result.get("received") and result.get("replied"):
        print("[OK] Spark heard you.")
        print("[OK] Spark replied.")
        print("[OK] You are connected.")
        return
    if result.get("received"):
        print("[FIX] Spark heard your first Telegram message, but no reply was recorded.")
        print("      Run: spark fix telegram")
        return
    print("[FIX] Spark did not hear the first Telegram message before the wait timed out.")
    print("      Check the bot token, admin id, and running process.")
    print("      Run: spark fix telegram")


def maybe_offer_first_message_repair(result: dict[str, Any], interactive: bool) -> None:
    if result.get("received") and result.get("replied"):
        return
    if not interactive:
        return
    try:
        answer = input("Run Telegram repair guidance now? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("")
        return
    if answer in {"", "y", "yes"}:
        cmd_fix(argparse.Namespace(target="telegram", json=False, redact_logs=False))


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
        "use `@env:NAME`, `@file:/path/to/secret`, or pass the value directly."
    )


def extract_telegram_bot_token(value: str) -> str:
    """Return a Telegram bot token, tolerating copied BotFather surrounding text."""
    stripped = value.strip().strip("\"'")
    if TELEGRAM_BOT_TOKEN_PATTERN.fullmatch(stripped):
        return stripped
    matches = TELEGRAM_BOT_TOKEN_PATTERN.findall(stripped)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit("Found more than one Telegram bot token. Copy or paste only the token for the bot you want to connect.")
    return stripped


def telegram_token_repair_command(secret_id: str) -> str:
    prefix = "telegram.profiles."
    suffix = ".bot_token"
    if secret_id.startswith(prefix) and secret_id.endswith(suffix):
        profile = secret_id[len(prefix) : -len(suffix)]
        return f"spark telegram connect {profile}"
    return "spark telegram connect"


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
    if stripped.lower().startswith("@file:"):
        secret_path = stripped[6:].strip()
        if not secret_path:
            raise SystemExit("Invalid secret reference: @file: requires a path.")
        try:
            return Path(secret_path).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(f"Could not read secret file {secret_path}: {exc}") from exc
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
    allow_missing: bool = False,
    existing_values: dict[str, str] | None = None,
) -> dict[str, str]:
    secret_values = dict(existing_values or {})
    secret_values.update(parse_secret_pairs(getattr(args, "secret", None)))
    legacy_map = {
        "telegram.bot_token": getattr(args, "bot_token", None),
        "telegram.admin_ids": getattr(args, "admin_telegram_ids", None),
        "telegram.relay_secret": getattr(args, "telegram_relay_secret", None),
        "llm.zai.api_key": getattr(args, "zai_api_key", None),
        "llm.openai.api_key": getattr(args, "openai_api_key", None),
        "llm.anthropic.api_key": getattr(args, "anthropic_api_key", None),
        "llm.openrouter.api_key": getattr(args, "openrouter_api_key", None),
        "llm.huggingface.api_key": getattr(args, "huggingface_api_key", None),
        "llm.kimi.api_key": getattr(args, "kimi_api_key", None),
        "llm.minimax.api_key": getattr(args, "minimax_api_key", None),
        "voice.elevenlabs.api_key": getattr(args, "elevenlabs_api_key", None),
    }
    for key, value in legacy_map.items():
        if value:
            resolved_value = resolve_secret_input(str(value))
            if is_telegram_bot_token_secret(key):
                resolved_value = extract_telegram_bot_token(resolved_value)
            secret_values.setdefault(key, resolved_value)

    requirements = collect_secret_requirements(modules)
    if getattr(args, "external_telegram_ingress", False):
        requirements.pop("telegram.bot_token", None)
        requirements.pop("telegram.admin_ids", None)
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
    if missing and not allow_missing:
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


def telegram_relay_secret_is_valid(value: str | None) -> bool:
    if not value:
        return False
    return 24 <= len(value) <= 256 and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


def modules_need_telegram_relay_secret(modules: Iterable[Module]) -> bool:
    return any("telegram.relay_secret" in module.needed_secrets for module in modules)


def generated_env_telegram_relay_secret(modules: Iterable[Module]) -> str | None:
    values: set[str] = set()
    for module in modules:
        value = read_generated_env(generated_module_env_path(module)).get("TELEGRAM_RELAY_SECRET", "").strip()
        if telegram_relay_secret_is_valid(value):
            values.add(value)
    if len(values) == 1:
        return next(iter(values))
    return None


def remember_setup_secret_key(secret_id: str) -> None:
    setup_state = load_json(CONFIG_PATH, {})
    if not isinstance(setup_state, dict):
        return
    secret_keys = setup_state.get("secret_keys")
    if isinstance(secret_keys, list):
        keys = {str(key) for key in secret_keys}
    else:
        keys = set()
    if secret_id in keys and secret_keys == sorted(keys):
        return
    keys.add(secret_id)
    setup_state["secret_keys"] = sorted(keys)
    save_json(CONFIG_PATH, setup_state)


def ensure_runtime_telegram_relay_secret(modules: Iterable[Module]) -> None:
    """Repair the machine-generated local relay credential before startup."""
    module_list = list(modules)
    if not modules_need_telegram_relay_secret(module_list):
        return

    secret_id = "telegram.relay_secret"
    existing = fetch_secret(secret_id)
    if telegram_relay_secret_is_valid(existing):
        remember_setup_secret_key(secret_id)
        return

    recovered = generated_env_telegram_relay_secret(module_list)
    value = recovered or py_secrets.token_urlsafe(32)
    store_secret(secret_id, value, preferred="keychain")
    remember_setup_secret_key(secret_id)


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

    Interactive Windows/POSIX terminals get one asterisk per typed/pasted
    character so users can tell input landed without exposing the value. Weird
    terminals fall back to the standard hidden getpass prompt.
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
    if sys.platform != "win32" and stdin_is_tty() and stdout_is_tty():
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
        except (AttributeError, ImportError, OSError):
            return getpass.getpass(prompt)
        try:
            original_attrs = termios.tcgetattr(fd)
        except termios.error:
            return getpass.getpass(prompt)
        chars: list[str] = []
        sys.stdout.write(prompt)
        sys.stdout.flush()
        try:
            tty.setcbreak(fd)
            while True:
                char = sys.stdin.read(1)
                if char in {"", "\x04"}:
                    raise EOFError
                if char in {"\r", "\n"}:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "".join(chars)
                if char == "\x03":
                    raise KeyboardInterrupt
                if char in {"\b", "\x7f"}:
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                chars.append(char)
                sys.stdout.write("*")
                sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
    return getpass.getpass(prompt)


def setup_is_interactive(args: argparse.Namespace) -> bool:
    if getattr(args, "non_interactive", False):
        return False
    return stdin_is_tty()


def detect_claude_code() -> dict[str, Any]:
    if os.name == "nt":
        for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not raw_dir:
                continue
            candidate = Path(raw_dir) / "claude.ps1"
            if candidate.exists():
                return {"present": True, "path": str(candidate)}
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


def provider_env_blocklist() -> set[str]:
    blocked = set(STATIC_PROVIDER_ENV_BLOCKLIST)
    for spec in LLM_PROVIDER_ENV.values():
        for key in ("api_key_env", "base_url_env"):
            value = spec.get(key)
            if value:
                blocked.add(str(value))
    return blocked


def provider_secret_env_blocklist() -> set[str]:
    blocked = {
        key
        for key in STATIC_PROVIDER_ENV_BLOCKLIST
        if any(marker in key.upper() for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))
    }
    for spec in LLM_PROVIDER_ENV.values():
        value = spec.get("api_key_env")
        if value:
            blocked.add(str(value))
    return blocked


def is_safe_parent_env_key(key: str) -> bool:
    normalized = key.upper()
    return normalized in SAFE_PARENT_ENV_KEYS or any(normalized.startswith(prefix) for prefix in SAFE_PARENT_ENV_PREFIXES)


def safe_parent_env(base: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if base is None else base
    blocked = provider_env_blocklist()
    return {
        key: value
        for key, value in source.items()
        if is_safe_parent_env_key(key) and key.upper() not in blocked
    }


def strip_reserved_workspace_env(values: dict[str, str]) -> dict[str, str]:
    blocked = provider_env_blocklist()
    return {key: value for key, value in values.items() if key.upper() not in blocked}


def resolve_policy_path(path: Path) -> Path:
    expanded = path.expanduser() if isinstance(path, Path) else Path(path).expanduser()
    real_path = expanded.__class__(os.path.realpath(os.fspath(expanded)))
    return real_path.resolve(strict=False)


def policy_home_path(home: Path | None = None) -> Path:
    if home is not None:
        return resolve_policy_path(home)
    try:
        return resolve_policy_path(Path.home())
    except RuntimeError:
        return resolve_policy_path(SPARK_HOME.parent)


def policy_path_is_same_or_child(candidate: Path, parent: Path) -> bool:
    candidate_text = os.path.normcase(os.path.normpath(os.fspath(resolve_policy_path(candidate))))
    parent_text = os.path.normcase(os.path.normpath(os.fspath(resolve_policy_path(parent))))
    try:
        return os.path.commonpath([candidate_text, parent_text]) == parent_text
    except ValueError:
        return False


def write_denied_prefixes(home: Path | None = None) -> list[Path]:
    home_path = policy_home_path(home)
    denied = [home_path / relative for relative in WRITE_DENIED_HOME_PREFIXES]
    if sys.platform != "win32":
        denied.extend(Path(prefix) for prefix in WRITE_DENIED_POSIX_PREFIXES)
    else:
        path_type = home_path.__class__
        appdata = os.environ.get("APPDATA")
        if appdata:
            denied.extend([path_type(appdata) / "gh", path_type(appdata) / "gcloud"])
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            denied.extend([path_type(local_appdata) / "GitHub CLI", path_type(local_appdata) / "Google" / "Cloud SDK"])
        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "SYSTEMROOT", "WINDIR"):
            value = os.environ.get(key)
            if value:
                denied.append(path_type(value))
    return [resolve_policy_path(path) for path in denied]


def write_denied_paths(home: Path | None = None) -> list[Path]:
    home_path = policy_home_path(home)
    return [resolve_policy_path(home_path / relative) for relative in WRITE_DENIED_HOME_PATHS]


def path_is_write_denied(path: Path) -> tuple[bool, str]:
    candidate = resolve_policy_path(path)
    for denied_path in write_denied_paths():
        if os.path.normcase(os.path.normpath(os.fspath(candidate))) == os.path.normcase(os.path.normpath(os.fspath(denied_path))):
            return True, str(denied_path)
    for denied_prefix in write_denied_prefixes():
        if policy_path_is_same_or_child(candidate, denied_prefix):
            return True, str(denied_prefix)
    return False, ""


def spark_write_safe_root() -> Path | None:
    raw = os.environ.get("SPARK_WRITE_SAFE_ROOT", "").strip()
    if not raw:
        return None
    return resolve_policy_path(Path(raw))


def require_write_allowed(path: Path, *, safe_root: Path | None = None, subject: str = "path") -> None:
    candidate = resolve_policy_path(path)
    denied, reason = path_is_write_denied(candidate)
    if denied:
        raise SystemExit(f"Refusing {subject}: `{candidate}` is inside denied write path `{reason}`.")
    if safe_root is not None and not policy_path_is_same_or_child(candidate, safe_root):
        raise SystemExit(f"Refusing {subject}: `{candidate}` is outside Spark write boundary `{safe_root}`.")


def write_boundary_env(base: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    denied_paths = [*write_denied_paths(), *write_denied_prefixes()]
    env["SPARK_WRITE_DENIED_PATHS"] = os.pathsep.join(str(path) for path in denied_paths)
    safe_root = spark_write_safe_root()
    if safe_root is not None:
        env["SPARK_WRITE_SAFE_ROOT"] = str(safe_root)
    return env


def shell_command_env(*, filtered: bool = False) -> dict[str, str]:
    env = safe_parent_env() if filtered else os.environ.copy()
    managed_node_dir = SPARK_HOME / "tools" / "node-v22.18.0-win-x64"
    if os.name == "nt" and managed_node_dir.exists():
        env["PATH"] = str(managed_node_dir) + os.pathsep + env.get("PATH", "")
    python_path = sys.executable if os.path.exists(sys.executable) else resolve_runtime_binary("python")
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
    print("Spark checked your computer:")
    ready: list[str] = []
    optional: list[str] = []
    blocking: list[str] = []
    cc = detect_claude_code()
    if cc["present"]:
        ready.append("claude on PATH")
    else:
        optional.append("claude - needed only if you choose Claude")
    codex = detect_codex_cli()
    if codex["present"]:
        ready.append("codex on PATH")
    else:
        optional.append("codex - needed only if you choose Codex")
    for runtime_name in required_runtimes_for_modules(bundle):
        info = detect_runtime_binary(runtime_name)
        if info["present"]:
            version = info.get("version") or "version unknown"
            ready.append(f"{runtime_name} {version}")
        else:
            blocking.append(f"{runtime_name} not on PATH")
    print("")
    print("Ready:")
    for item in ready or ["none yet"]:
        print(f"  {item}")
    print("")
    print("Optional:")
    for item in optional or ["none"]:
        print(f"  {item}")
    print("")
    print("Blocking issues:")
    for item in blocking or ["none"]:
        print(f"  {item}")
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
    if secret_id == "telegram.bot_token":
        print("")
        print("Connect Telegram so Spark has a place to talk with you.")
        print("  1. Open Telegram")
        print("  2. Message @BotFather")
        print("  3. Send /newbot")
        print("  4. Copy the token BotFather gives you")
        print("  5. Paste it here")
    if secret_id == "telegram.admin_ids":
        print("")
        print("Now Spark needs your Telegram user ID.")
        print("This tells Spark who is allowed to control your bot.")
        print("")
        print("To find it:")
        print("  1. Open Telegram")
        print("  2. Message @userinfobot")
        print("  3. Copy the number shown as Id")
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
    print("Spark setup wizard")
    print("  Spark collects Telegram values locally, then helps you choose how it thinks.")
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


def telegram_profile_should_autostart(profile_state: Any) -> bool:
    return not (isinstance(profile_state, dict) and profile_state.get("autostart") is False)


def primary_telegram_profile(setup_state: dict[str, Any] | None = None) -> str:
    state = setup_state if isinstance(setup_state, dict) else load_json(CONFIG_PATH, {})
    if not isinstance(state, dict):
        return DEFAULT_PRIMARY_TELEGRAM_PROFILE
    configured = state.get(PRIMARY_TELEGRAM_PROFILE_KEY)
    if isinstance(configured, str) and configured.strip():
        return normalize_telegram_profile(configured)
    profiles = state.get("telegram_profiles")
    if isinstance(profiles, dict) and profiles:
        for profile in sorted(profiles):
            if isinstance(profiles.get(profile), dict):
                return normalize_telegram_profile(str(profile))
    return DEFAULT_PRIMARY_TELEGRAM_PROFILE


def telegram_profile_relay_port(
    setup_state: dict[str, Any] | None,
    profile: str | None,
    default: int = 8788,
) -> int:
    normalized = normalize_telegram_profile(profile)
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    if isinstance(profiles, dict):
        profile_state = profiles.get(normalized)
        if isinstance(profile_state, dict):
            try:
                relay_port = int(profile_state.get("relay_port", 0))
            except (TypeError, ValueError):
                relay_port = 0
            if relay_port > 0:
                return relay_port
    return default


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
    env: dict[str, str] = {}
    bot_token = fetch_secret(telegram_profile_secret_id(normalized, "bot_token"))
    relay_secret = fetch_secret(telegram_profile_secret_id(normalized, "relay_secret"))
    if bot_token:
        env["BOT_TOKEN"] = bot_token
    if relay_secret:
        env["TELEGRAM_RELAY_SECRET"] = relay_secret
    return env


def validate_telegram_profile_token_identity(profile: str | None) -> None:
    """Fail closed when a named Telegram profile's token points at the wrong bot."""
    normalized = normalize_telegram_profile(profile)
    if telegram_profile_is_default(normalized):
        return
    setup_state = load_json(CONFIG_PATH, {})
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    profile_state = profiles.get(normalized) if isinstance(profiles, dict) else None
    if not isinstance(profile_state, dict):
        return
    expected_username = str(profile_state.get("telegram_username") or "").strip().lstrip("@")
    expected_id = str(profile_state.get("telegram_bot_id") or "").strip()
    if not expected_username and not expected_id:
        return
    token = fetch_secret(telegram_profile_secret_id(normalized, "bot_token"))
    if not token:
        raise SystemExit(
            f"Telegram profile `{normalized}` has no stored bot token. "
            f"Reconnect it with `spark telegram connect {normalized}`."
        )
    identity = validate_telegram_bot_token(token, secret_id=telegram_profile_secret_id(normalized, "bot_token"))
    actual_username = str(identity.get("username") or "").strip().lstrip("@")
    actual_id = str(identity.get("id") or "").strip()
    username_mismatch = expected_username and actual_username.lower() != expected_username.lower()
    id_mismatch = expected_id and actual_id != expected_id
    if username_mismatch or id_mismatch:
        expected_label = f"@{expected_username}" if expected_username else f"id {expected_id}"
        actual_label = f"@{actual_username}" if actual_username else f"id {actual_id or 'unknown'}"
        raise SystemExit(
            f"Refusing to start Telegram profile `{normalized}`: stored token belongs to {actual_label}, "
            f"but this profile is locked to {expected_label}. "
            f"Reconnect the intended bot with `spark telegram connect {normalized}`."
        )


def spark_builder_home() -> Path:
    return STATE_DIR / "spark-intelligence"


def write_generated_env(path: Path, values: dict[str, str]) -> None:
    require_write_allowed(path, subject="generated module env write")
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
        values[key.strip().lstrip("\ufeff")] = value
    return values


def module_runtime_env(module: Module, profile: str | None = None) -> dict[str, str]:
    env = shell_command_env(filtered=True)
    env.update(strip_reserved_workspace_env(read_generated_env(generated_module_env_path(module))))
    if module.name == "spark-telegram-bot" and not telegram_profile_is_default(profile):
        env.update(strip_reserved_workspace_env(read_generated_env(generated_module_env_path(module, profile))))
    env.update(keychain_env_for_module(module))
    if module.name == "spark-telegram-bot":
        env.update(keychain_env_for_telegram_profile(profile))
    return write_boundary_env(env)


LLM_PROVIDER_ENV: dict[str, dict[str, str]] = {
    "openrouter": {
        "api_key_secret": "llm.openrouter.api_key",
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url_arg": "openrouter_base_url",
        "base_url_env": "OPENROUTER_BASE_URL",
        "base_url_default": "https://openrouter.ai/api/v1",
        "model_arg": "openrouter_model",
        "model_env": "OPENROUTER_MODEL",
        "model_default": "openai/gpt-5.5",
        "bot_provider": "openrouter",
    },
    "huggingface": {
        "api_key_secret": "llm.huggingface.api_key",
        "api_key_env": "HF_TOKEN",
        "base_url_arg": "huggingface_base_url",
        "base_url_env": "HUGGINGFACE_BASE_URL",
        "base_url_default": "https://router.huggingface.co/v1",
        "model_arg": "huggingface_model",
        "model_env": "HUGGINGFACE_MODEL",
        "model_default": "google/gemma-4-26B-A4B-it:fastest",
        "bot_provider": "huggingface",
    },
    "kimi": {
        "api_key_secret": "llm.kimi.api_key",
        "api_key_env": "KIMI_API_KEY",
        "base_url_arg": "kimi_base_url",
        "base_url_env": "KIMI_BASE_URL",
        "base_url_default": "https://api.moonshot.ai/v1",
        "model_arg": "kimi_model",
        "model_env": "KIMI_MODEL",
        "model_default": "kimi-k2.6",
        "bot_provider": "kimi",
    },
    "lmstudio": {
        "base_url_arg": "lmstudio_base_url",
        "base_url_env": "LMSTUDIO_BASE_URL",
        "base_url_default": "http://localhost:1234/v1",
        "model_arg": "lmstudio_model",
        "model_env": "LMSTUDIO_MODEL",
        "model_default": "local-model",
        "bot_provider": "lmstudio",
    },
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
        "bot_provider": "openai",
    },
    "anthropic": {
        "api_key_secret": "llm.anthropic.api_key",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_arg": "anthropic_base_url",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "base_url_default": "https://api.anthropic.com",
        "model_arg": "anthropic_model",
        "model_env": "ANTHROPIC_MODEL",
        "model_default": "sonnet",
        "bot_provider": "claude",
    },
    "minimax": {
        "api_key_secret": "llm.minimax.api_key",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url_arg": "minimax_base_url",
        "base_url_env": "MINIMAX_BASE_URL",
        "base_url_default": "https://api.minimax.io/v1",
        "model_arg": "minimax_model",
        "model_env": "MINIMAX_MODEL",
        "model_default": "MiniMax-M2.7",
        "bot_provider": "minimax",
    },
    "ollama": {
        "base_url_arg": "ollama_url",
        "base_url_env": "OLLAMA_URL",
        "base_url_default": "http://localhost:11434",
        "model_arg": "ollama_model",
        "model_env": "OLLAMA_MODEL",
        "model_default": "llama3.2:3b",
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
LLM_PROVIDER_WIZARD_ORDER = ("codex", "anthropic", "zai", "kimi", "openrouter", "huggingface", "minimax", "lmstudio", "ollama", "openai")
LLM_ROLE_LABELS = {
    "chat": "Telegram chat replies",
    "builder": "Agent runtime reasoning",
    "memory": "memory synthesis and recall",
    "mission": "Mission Control builds and longer work",
}
LLM_PROVIDER_LABELS = {
    "openai": "OpenAI API",
    "codex": "OpenAI Codex",
    "anthropic": "Anthropic Claude",
    "openrouter": "OpenRouter",
    "huggingface": "Hugging Face router",
    "kimi": "Kimi / Moonshot",
    "lmstudio": "LM Studio local",
    "zai": "Z.AI GLM",
    "minimax": "MiniMax",
    "ollama": "Ollama local",
}
LLM_PROVIDER_AUTH_HINTS = {
    "openai": "OPENAI_API_KEY",
    "codex": "OpenAI Codex CLI OAuth",
    "anthropic": "Anthropic Claude Code `claude -p` sign-in path",
    "openrouter": "OPENROUTER_API_KEY",
    "huggingface": "HF_TOKEN",
    "kimi": "KIMI_API_KEY or MOONSHOT_API_KEY",
    "lmstudio": "local LM Studio server",
    "zai": "ZAI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "ollama": "local Ollama server",
}
LLM_PROVIDER_GUIDANCE: dict[str, dict[str, Any]] = {
    "codex": {
        "lane": "paid/subscription",
        "best_for": "Best first pick if you already use OpenAI Codex or ChatGPT. Uses the OpenAI Codex CLI sign-in path instead of asking for an OpenAI API key.",
        "recommended_models": ["gpt-5.5"],
        "getting_started": "Install OpenAI Codex CLI, sign in with `codex login`, then run `spark setup --llm-provider codex`.",
        "notes": "This is the OAuth-style route for OpenAI Codex and ChatGPT users. No OpenAI API key copy-paste is needed.",
    },
    "openai": {
        "lane": "api/paid",
        "best_for": "OpenAI API users who specifically want an API-key route instead of OpenAI Codex CLI sign-in.",
        "recommended_models": ["gpt-5.5", "gpt-5.4-mini", "gpt-5.4-nano"],
        "getting_started": "Create an OpenAI API key, then run `spark setup --llm-provider openai --openai-api-key <key>`.",
        "notes": "Most non-technical ChatGPT users should start with `codex`; this route is for API billing/accounts.",
    },
    "anthropic": {
        "lane": "paid/subscription",
        "best_for": "Best first pick if you already use Anthropic Claude. Spark can call Anthropic Claude Code through `claude -p` after you sign in.",
        "recommended_models": ["sonnet", "opus"],
        "getting_started": "Install Anthropic Claude Code, run `claude` once to sign in, verify `claude -p \"hello\"`, then run `spark setup --llm-provider anthropic`.",
        "notes": "Claude Code accepts stable aliases like `sonnet` and `opus`; use full Anthropic model IDs only when you know your installed Claude Code supports them. API keys remain supported for advanced users.",
    },
    "openrouter": {
        "lane": "api/paid gateway",
        "best_for": "Trying many commercial/open models behind one API key.",
        "recommended_models": ["openai/gpt-5.5", "anthropic/claude-sonnet-4"],
        "getting_started": "Create an OpenRouter key, then run `spark setup --llm-provider openrouter --openrouter-api-key <key>`.",
        "notes": "Good if you want one billing/gateway surface and model fallback experiments.",
    },
    "zai": {
        "lane": "api/paid",
        "best_for": "Strong API-key path for users who already have Z.AI GLM access and want one provider for Agent and Mission.",
        "recommended_models": ["glm-5.1"],
        "getting_started": "Create a Z.AI GLM key, then run `spark setup --llm-provider zai --zai-api-key <key>`.",
        "notes": "Good default when you already have a Z.AI GLM key. Spark keeps this explicit so old Ollama/local settings cannot hijack the route.",
    },
    "kimi": {
        "lane": "api/paid",
        "best_for": "Moonshot/Kimi users who want an OpenAI-compatible Kimi route for Agent and Mission.",
        "recommended_models": ["kimi-k2.6", "moonshot-v1-128k"],
        "getting_started": "Create a Moonshot/Kimi key, then run `spark setup --llm-provider kimi --kimi-api-key <key>`.",
        "notes": "Uses Moonshot's OpenAI-compatible endpoint at https://api.moonshot.ai/v1. You can override the model with --kimi-model.",
    },
    "minimax": {
        "lane": "api/paid",
        "best_for": "MiniMax users who already have a MiniMax API key and want an OpenAI-compatible route.",
        "recommended_models": ["MiniMax-M2.7"],
        "getting_started": "Create a MiniMax key, then run `spark setup --llm-provider minimax --minimax-api-key <key>`.",
        "notes": "Best as a choose-your-provider route, not a forced default.",
    },
    "huggingface": {
        "lane": "api/token gateway",
        "best_for": "Trying hosted open models through Hugging Face's OpenAI-compatible router.",
        "recommended_models": ["google/gemma-4-26B-A4B-it:fastest", "google/gemma-4-31B-it:fastest"],
        "getting_started": "Create a Hugging Face token, then run `spark setup --llm-provider huggingface --huggingface-api-key <key>`.",
        "notes": "Gemma 4 26B is the chat default; 31B is the heavier mission recommendation.",
    },
    "lmstudio": {
        "lane": "local/free after download",
        "best_for": "Non-technical local model users who want a desktop app and OpenAI-compatible localhost server.",
        "recommended_models": ["a loaded LM Studio chat model", "google/gemma-3-27b-it", "qwen3:30b class models if your machine can handle them"],
        "getting_started": "Install LM Studio, load a chat model, start its local server, then run `spark setup --llm-provider lmstudio --lmstudio-model <loaded-model-id>`.",
        "notes": "Private/local, but quality depends heavily on your machine and selected model.",
    },
    "ollama": {
        "lane": "local/free after download",
        "best_for": "Terminal-friendly local models and private/offline memory or lightweight chat.",
        "recommended_models": ["llama3.2:3b", "gemma3:12b", "gemma3:27b", "qwen3:30b"],
        "getting_started": "Install Ollama, run `ollama pull llama3.2:3b`, then run `spark setup --llm-provider ollama`.",
        "notes": "Small models are easy to run; larger models are better for reasoning but need more RAM/VRAM.",
    },
}


def describe_llm_provider_setup(provider: str) -> str:
    spec = LLM_PROVIDER_ENV[provider]
    auth_hint = LLM_PROVIDER_AUTH_HINTS[provider]
    guidance = LLM_PROVIDER_GUIDANCE.get(provider, {})
    lane = guidance.get("lane", "provider")
    best_for = guidance.get("best_for", "")
    status = ""
    if provider == "openai":
        status = "use OPENAI_API_KEY, or point --openai-base-url at an OpenAI-compatible server"
    elif provider == "codex":
        status = "OpenAI Codex CLI detected" if detect_codex_cli()["present"] else "run `codex login` to sign in first"
    elif provider == "anthropic":
        status = "Anthropic Claude Code detected; Spark can call it with `claude -p`" if detect_claude_code()["present"] else "use ANTHROPIC_API_KEY or run `claude` to sign in"
    elif provider == "ollama":
        status = "local Ollama server"
    elif provider == "openrouter":
        status = "unified OpenAI-compatible model gateway"
    elif provider == "huggingface":
        status = "Hugging Face OpenAI-compatible chat router"
    elif provider == "kimi":
        status = "Moonshot OpenAI-compatible Kimi API"
    elif provider == "lmstudio":
        status = "local OpenAI-compatible server at http://localhost:1234/v1"
    elif provider == "zai":
        status = "uses the Z.AI GLM coding endpoint API key"
    elif provider == "minimax":
        status = "uses the MiniMax OpenAI-compatible API key"
    detail = f"{LLM_PROVIDER_LABELS[provider]} ({spec['model_default']}; {auth_hint}; {lane}; {status})"
    if best_for:
        detail = f"{detail} - {best_for}"
    return detail


def provider_recommendations_payload() -> dict[str, Any]:
    return {
        "summary": "Spark LLM recommendations",
        "default_rule": "Choose one default provider for Agent and Mission, or split them during setup. Agent means Telegram chat, runtime reasoning, memory, and recall. Mission means Spawner/Mission Control builds, research, coding, and longer tracked work.",
        "paths": {
            "already_have_subscription": ["codex", "anthropic"],
            "already_have_api_key": ["zai", "kimi", "openrouter", "huggingface", "minimax", "openai", "anthropic"],
            "want_local_private": ["lmstudio", "ollama"],
            "not_sure": ["codex", "anthropic", "zai", "lmstudio"],
        },
        "providers": [
            {
                "id": provider,
                "label": LLM_PROVIDER_LABELS[provider],
                "default_model": LLM_PROVIDER_ENV[provider]["model_default"],
                **LLM_PROVIDER_GUIDANCE[provider],
            }
            for provider in LLM_PROVIDER_WIZARD_ORDER
        ],
    }

SPARK_TERMINAL_COLORS = {
    "bg": "#171918",
    "bg_deep": "#0E1018",
    "surface": "#181C26",
    "accent": "#2FCA94",
    "accent_dim": "#1F8C66",
    "iris": "#B8A8DC",
    "text": "#F0F0F4",
    "muted": "#8890B0",
}


def terminal_supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = value.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raise ValueError(f"Invalid RGB hex color: {value}")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def terminal_style(text: str, *, fg: str | None = None, bg: str | None = None, bold: bool = False) -> str:
    if not terminal_supports_color():
        return text
    parts: list[str] = []
    if bold:
        parts.append("1")
    if fg:
        r, g, b = _hex_to_rgb(SPARK_TERMINAL_COLORS.get(fg, fg))
        parts.append(f"38;2;{r};{g};{b}")
    if bg:
        r, g, b = _hex_to_rgb(SPARK_TERMINAL_COLORS.get(bg, bg))
        parts.append(f"48;2;{r};{g};{b}")
    if not parts:
        return text
    return f"\033[{';'.join(parts)}m{text}\033[0m"


def terminal_color(text: str, code: str) -> str:
    if code == "spark-title":
        return terminal_style(text, fg="accent", bg="bg", bold=True)
    if code == "spark-section":
        return terminal_style(text, fg="accent", bold=True)
    if code == "spark-provider":
        return terminal_style(text, fg="iris")
    if not terminal_supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def setup_has_llm_provider_selection(args: argparse.Namespace) -> bool:
    if getattr(args, "llm_provider", None):
        return True
    if getattr(args, "agent_llm_provider", None):
        return True
    return any(getattr(args, f"{role}_llm_provider", None) for role in LLM_ROLES)


def provider_requires_wizard_api_key(provider: str) -> bool:
    if provider in {"zai", "kimi", "minimax", "openrouter", "huggingface"}:
        return True
    if provider == "openai":
        return True
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


def prompt_for_provider_choice_from(prompt: str, default: str, options: Iterable[str]) -> str | None:
    ordered = [provider for provider in options if provider in LLM_PROVIDER_CHOICES]
    provider_by_number = {str(index): provider for index, provider in enumerate(ordered, start=1)}
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return None
    if not answer:
        answer = default
    if answer in {"0", "skip", "none", "not_configured"}:
        return "not_configured"
    provider = provider_by_number.get(answer, answer)
    if provider not in ordered:
        print(f"  Unknown provider `{answer}`.")
        return None
    return provider


def prompt_for_provider_role_mode(default_provider: str) -> str:
    label = LLM_PROVIDER_LABELS.get(default_provider, default_provider)
    print("")
    print("How should Spark use this provider?")
    print("  1. Same provider for Agent and Mission (recommended)")
    print("     Agent = Telegram chat, runtime reasoning, memory, and recall.")
    print("     Mission = Spawner/Mission Control builds, research, coding, and longer tracked work.")
    print(f"     This uses {label} for both.")
    print("  2. Use this provider for Agent, choose a different Mission provider now.")
    print("  3. Choose Agent and Mission providers separately.")
    try:
        answer = input("Provider layout [1/Same provider]: ").strip().lower()
    except (EOFError, StopIteration):
        return "same"
    if not answer:
        return "same"
    if answer in {"1", "same", "default", "all"}:
        return "same"
    if answer in {"2", "mission", "split", "different"}:
        return "mission"
    if answer in {"3", "both", "custom", "agent"}:
        return "custom"
    print(f"  Unknown layout `{answer}`. Using the same provider for Agent and Mission.")
    return "same"


def selected_llm_providers(args: argparse.Namespace, secret_values: dict[str, str]) -> list[str]:
    providers: list[str] = []
    for provider in resolve_llm_roles(args, secret_values).values():
        if provider != "not_configured" and provider not in providers:
            providers.append(provider)
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
        if provider in {"zai", "kimi", "minimax", "openrouter", "huggingface"}:
            print(f"  Endpoint: {spec['base_url_default']}")
            print(f"  Model: {spec['model_default']} (override with --{provider}-model if needed)")
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


def prompt_for_simple_provider_choice(default_provider: str) -> str | None:
    default_label = LLM_PROVIDER_LABELS.get(default_provider, default_provider)
    print("")
    print("Choose the LLM Spark will use")
    print("How should Spark think?")
    print("  1. Use my ChatGPT/Codex sign-in")
    print("  2. Use my Claude sign-in")
    print("  3. Use an API key")
    print("  4. Use a local model")
    print("  5. Skip for now")
    try:
        answer = input(f"Provider path [1/{default_label}]: ").strip().lower()
    except EOFError:
        return None
    if not answer:
        return default_provider
    if answer in {"1", "codex", "chatgpt", "openai codex"}:
        return "codex"
    if answer in {"2", "claude", "anthropic"}:
        return "anthropic"
    if answer in {"5", "0", "skip", "none", "not_configured"}:
        return "not_configured"
    if answer in {"3", "api", "api key", "key"}:
        print("")
        print("API key providers:")
        api_providers = ("zai", "kimi", "openrouter", "huggingface", "minimax", "openai", "anthropic")
        for index, provider in enumerate(api_providers, start=1):
            print(f"  {index}. {describe_llm_provider_setup(provider)}")
        provider = prompt_for_provider_choice_from("API provider [type number/name]: ", "zai", api_providers)
        return provider
    if answer in {"4", "local", "local model"}:
        print("")
        print("Local model providers:")
        local_providers = ("lmstudio", "ollama")
        for index, provider in enumerate(local_providers, start=1):
            print(f"  {index}. {describe_llm_provider_setup(provider)}")
        provider = prompt_for_provider_choice_from("Local provider [type number/name]: ", "lmstudio", local_providers)
        return provider
    if answer in LLM_PROVIDER_CHOICES:
        return answer
    print(f"  Unknown provider path `{answer}`.")
    return None


def print_selected_provider_status(provider: str) -> None:
    print("")
    print(f"Selected: {LLM_PROVIDER_LABELS.get(provider, provider)}")
    if provider == "codex":
        status = "found on PATH" if detect_codex_cli()["present"] else "not found on PATH"
        print("Requirement: codex must be installed and signed in")
        print(f"Status: {status}")
    elif provider == "anthropic":
        status = "found on PATH" if detect_claude_code()["present"] else "API key or Claude Code sign-in needed"
        print("Requirement: Claude Code sign-in or an Anthropic API key")
        print(f"Status: {status}")
    elif provider in {"lmstudio", "ollama"}:
        print("Requirement: local model server must be running when Spark replies")
        print("Status: checked later by spark providers test")
    else:
        print("Requirement: API key")
        print("Status: Spark will ask for it now if it is not already stored")


def run_llm_provider_wizard(args: argparse.Namespace, secret_values: dict[str, str]) -> dict[str, str]:
    if setup_has_llm_provider_selection(args):
        return collect_provider_api_keys(selected_llm_providers(args, secret_values), secret_values)
    recommended_provider = "codex" if detect_codex_cli()["present"] else "openai"
    provider = prompt_for_simple_provider_choice(recommended_provider)
    if provider is None:
        return secret_values
    if provider == "not_configured":
        return secret_values
    setattr(args, "llm_provider", provider)
    print_selected_provider_status(provider)

    role_mode = prompt_for_provider_role_mode(provider)
    if role_mode == "mission":
        mission_provider = prompt_for_provider_choice("Mission provider [type number/name]: ", provider)
        if mission_provider and mission_provider != "not_configured":
            setattr(args, "mission_llm_provider", mission_provider)
    elif role_mode == "custom":
        agent_provider = prompt_for_provider_choice("Agent provider [Enter to keep default]: ", provider)
        mission_provider = prompt_for_provider_choice("Mission provider [Enter to keep default]: ", provider)
        if agent_provider and agent_provider != "not_configured":
            setattr(args, "agent_llm_provider", agent_provider)
        if mission_provider and mission_provider != "not_configured":
            setattr(args, "mission_llm_provider", mission_provider)

    roles = resolve_llm_roles(args, secret_values)
    print("")
    print("Spark provider layout selected:")
    agent_roles = ("chat", "builder", "memory")
    agent_providers = {roles[role] for role in agent_roles}
    if len(agent_providers) == 1:
        agent_provider = next(iter(agent_providers))
        print(f"  Agent (chat + runtime + memory): {LLM_PROVIDER_LABELS.get(agent_provider, agent_provider)}")
    else:
        print("  Agent (expert split):")
        for role in agent_roles:
            role_provider = roles[role]
            print(f"    {role}: {LLM_PROVIDER_LABELS.get(role_provider, role_provider)}")
    mission_provider = roles["mission"]
    print(f"  Mission (Spawner builds + tracked work): {LLM_PROVIDER_LABELS.get(mission_provider, mission_provider)}")
    print("  Tip: rerun `spark setup` anytime to keep one provider, split Agent/Mission, or use expert role flags.")
    return collect_provider_api_keys(selected_llm_providers(args, secret_values), secret_values)


def resolve_llm_provider(args: argparse.Namespace, secret_values: dict[str, str]) -> str:
    requested = getattr(args, "llm_provider", None)
    if requested:
        return str(requested)
    explicit_key_providers = [
        provider
        for provider, spec in LLM_PROVIDER_ENV.items()
        if provider != "not_configured"
        and spec.get("api_key_secret")
        and getattr(args, str(spec.get("api_key_secret")).split(".")[1] + "_api_key", None)
    ]
    if len(explicit_key_providers) == 1:
        return explicit_key_providers[0]
    existing_setup = load_json(CONFIG_PATH, {})
    existing_llm = existing_setup.get("llm") if isinstance(existing_setup, dict) else None
    existing_provider = existing_llm.get("provider") if isinstance(existing_llm, dict) else None
    if existing_provider in LLM_PROVIDER_CHOICES:
        return str(existing_provider)
    return "not_configured"


def default_mission_llm_provider(default_provider: str) -> str:
    """Use the user's chosen provider for missions unless they explicitly split roles."""
    return default_provider


def openai_base_url_kind(base_url: str | None) -> str:
    if not base_url:
        return "default"
    default_base = str(LLM_PROVIDER_ENV["openai"]["base_url_default"]).rstrip("/")
    normalized = str(base_url).strip().rstrip("/")
    if not normalized or normalized == default_base:
        return "default"
    parsed = urllib.parse.urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "local"
    return "remote_custom"


def resolve_llm_roles(args: argparse.Namespace, secret_values: dict[str, str]) -> dict[str, str]:
    default_provider = resolve_llm_provider(args, secret_values)
    agent_provider = getattr(args, "agent_llm_provider", None)
    roles: dict[str, str] = {}
    for role in LLM_ROLES:
        explicit = getattr(args, f"{role}_llm_provider", None)
        if explicit:
            roles[role] = str(explicit)
        elif role == "mission":
            roles[role] = default_mission_llm_provider(default_provider)
        elif agent_provider:
            roles[role] = str(agent_provider)
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
    if provider == "openai":
        base_kind = openai_base_url_kind(env.get("OPENAI_BASE_URL"))
        if base_kind == "local":
            return "local"
        return "not_configured"
    if provider == "anthropic" and detect_claude_code()["present"]:
        return "claude_oauth"
    if provider in {"lmstudio", "ollama"}:
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

    selected_provider_names = sorted(set(roles.values()))

    for provider_name in selected_provider_names:
        provider_spec = LLM_PROVIDER_ENV[provider_name]
        api_key_secret = provider_spec.get("api_key_secret")
        api_key_env = provider_spec.get("api_key_env")
        if api_key_secret and api_key_env and secret_values.get(api_key_secret):
            env[api_key_env] = secret_values[api_key_secret]

    for provider_name in selected_provider_names:
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
        if not any(secret_marker in key.upper() for secret_marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))
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
            "base_url": env.get(f"SPARK_{role.upper()}_LLM_BASE_URL", ""),
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
    relay_base = spawner_ui_url or "http://127.0.0.1:3333"
    parsed = urllib.parse.urlparse(relay_base)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "127.0.0.1"
    return f"{scheme}://{host}:8788/spawner-events"


HOSTED_SPAWNER_PARENT_ENV_KEYS = (
    "SPARK_HOSTED_PRIVATE_PREVIEW",
    "SPARK_WORKSPACE_ID",
    "SPARK_UI_API_KEY",
    "SPARK_BRIDGE_API_KEY",
    "SPARK_ALLOWED_HOSTS",
)


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
    workspace_root = str(SPARK_HOME / "workspaces")
    setup_state = load_json(CONFIG_PATH, {})
    primary_profile = primary_telegram_profile(setup_state)
    primary_relay_port = telegram_profile_relay_port(setup_state, primary_profile)

    gateway_env = {
        "BOT_TOKEN": secret_values.get("telegram.bot_token", ""),
        "ADMIN_TELEGRAM_IDS": secret_values.get("telegram.admin_ids", ""),
        "SPARK_BUILDER_REPO": str(builder.path),
        "SPARK_BUILDER_HOME": str(builder_home),
        "SPARK_BUILDER_PYTHON": str(Path(sys.executable)),
        "SPARK_BUILDER_BRIDGE_MODE": "required",
        "SPAWNER_UI_URL": args.spawner_ui_url or "http://127.0.0.1:3333",
        "TELEGRAM_GATEWAY_MODE": "polling",
        "TELEGRAM_RELAY_PORT": str(primary_relay_port),
        "SPARK_TELEGRAM_PROFILE": primary_profile,
        "TELEGRAM_RELAY_SECRET": relay_secret,
        "SPARK_ONBOARDING_SESSION": str(getattr(args, "onboarding_session", "") or ""),
        "SPARK_ONBOARDING_EVENT_PATH": str(TELEGRAM_FIRST_MESSAGE_EVENTS_PATH),
        "SPARK_WORKSPACE_ROOT": workspace_root,
        "SPARK_ACCESS_LEVEL_DEFAULT": "4",
        "SPARK_ACCESS_DEFAULT_LANE": "spark_workspace",
    }
    if character is not None:
        gateway_env["SPARK_CHARACTER_ROOT"] = str(character.path)
    gateway_env.update(
        telegram_specialization_runtime_env_refs_from_installed(installed_records_from_modules(modules_by_name))
    )
    gateway_env.update(llm_env)

    webhook_urls = telegram_profile_webhook_urls() or [default_telegram_webhook_url(args.spawner_ui_url)]
    spawner_env = {
        "MISSION_CONTROL_WEBHOOK_URLS": ",".join(webhook_urls),
        "SPARK_WORKSPACE_ROOT": workspace_root,
        "SPAWNER_WORKSPACE_ROOT": workspace_root,
        "SPAWNER_STATE_DIR": str(STATE_DIR / "spawner-ui"),
        "SPARK_ACCESS_LEVEL_DEFAULT": "4",
        "SPARK_ACCESS_DEFAULT_LANE": "spark_workspace",
        "SPARK_WORKSPACE_BOUNDARY_KIND": "workspace_write",
        "SPARK_CODEX_SANDBOX": "workspace-write",
    }
    for key in HOSTED_SPAWNER_PARENT_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            spawner_env[key] = value
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
        "SPARK_WORKSPACE_ROOT": workspace_root,
        "SPARK_ACCESS_LEVEL_DEFAULT": "4",
        "SPARK_ACCESS_DEFAULT_LANE": "spark_workspace",
        **llm_metadata_env,
    }
    if researcher is not None:
        builder_env["SPARK_RESEARCHER_ROOT"] = str(researcher.path)
    if character is not None:
        builder_env["SPARK_CHARACTER_ROOT"] = str(character.path)
    if memory is not None:
        builder_env["SPARK_DOMAIN_CHIP_MEMORY_ROOT"] = str(memory.path)
    voice = modules_by_name.get(VOICE_MODULE_NAME)
    if voice is not None:
        builder_env["SPARK_VOICE_COMMS_ROOT"] = str(voice.path)
        if secret_values.get("voice.elevenlabs.api_key"):
            builder_env["ELEVENLABS_API_KEY"] = secret_values["voice.elevenlabs.api_key"]
            builder_env.setdefault("SPARK_TELEGRAM_VOICE_TTS_PROVIDER", "elevenlabs")
            builder_env.setdefault("SPARK_TELEGRAM_VOICE_TTS_SECRET_ENV_REF", "ELEVENLABS_API_KEY")
            builder_env.setdefault("SPARK_TELEGRAM_VOICE_TTS_ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

    return {
        gateway.name: gateway_env,
        spawner.name: spawner_env,
        builder.name: builder_env,
    }


def should_preserve_level5_guardrails(module_name: str) -> bool:
    if module_name not in {"spawner-ui", "spark-telegram-bot"}:
        return False
    from .sandbox.access import LEVEL5_ENV, level5_guardrails_configured_by_audit

    existing = read_generated_env(MODULE_CONFIG_DIR / f"{module_name}.env")
    already_enabled = all(existing.get(key) == value for key, value in LEVEL5_ENV.items())
    return already_enabled or level5_guardrails_configured_by_audit(home=SPARK_HOME)


def preserve_level5_guardrails(module_name: str, env_values: dict[str, str]) -> dict[str, str]:
    if not should_preserve_level5_guardrails(module_name):
        return env_values
    from .sandbox.access import LEVEL5_ENV

    return {**env_values, **LEVEL5_ENV}


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
        bot_token = extract_telegram_bot_token(resolve_secret_input(str(bot_token_arg)))
    else:
        bot_token = fetch_secret(telegram_profile_secret_id(profile, "bot_token"))
    if not bot_token:
        raise SystemExit(
            "Missing profile bot token. Run `spark telegram connect <profile>` and paste the BotFather token when Spark asks."
        )
    profile_secret_id = telegram_profile_secret_id(profile, "bot_token")
    bot_identity: dict[str, Any] | None = None
    if not getattr(args, "skip_telegram_token_check", False) and fetch_secret(profile_secret_id) != bot_token:
        bot_identity = validate_telegram_bot_token(bot_token, secret_id=profile_secret_id)

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
    backend = store_secret(profile_secret_id, bot_token, preferred="keychain")

    webhook_url = f"http://127.0.0.1:{relay_port}/spawner-events"
    append_spawner_webhook_url(spawner, webhook_url)

    profiles = setup_state.setdefault("telegram_profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        setup_state["telegram_profiles"] = profiles
    existing_profile_state = profiles.get(profile) if isinstance(profiles.get(profile), dict) else {}
    profile_state = {
        "module": "spark-telegram-bot",
        "env_file": str(generated_module_env_path(gateway, profile)),
        "relay_port": relay_port,
        "webhook_url": webhook_url,
        "bot_token_secret": profile_secret_id,
        "admin_ids_configured": bool(profile_env.get("ADMIN_TELEGRAM_IDS")),
        "configured_at": timestamp_now(),
    }
    if bot_identity:
        if bot_identity.get("username"):
            profile_state["telegram_username"] = str(bot_identity["username"]).lstrip("@")
        if bot_identity.get("id") is not None:
            profile_state["telegram_bot_id"] = str(bot_identity["id"])
    if getattr(args, "telegram_autostart", None) is not None:
        profile_state["autostart"] = bool(getattr(args, "telegram_autostart"))
    elif isinstance(existing_profile_state, dict) and "autostart" in existing_profile_state:
        profile_state["autostart"] = existing_profile_state["autostart"]
    profiles[profile] = profile_state
    if not isinstance(setup_state.get(PRIMARY_TELEGRAM_PROFILE_KEY), str):
        setup_state[PRIMARY_TELEGRAM_PROFILE_KEY] = profile
    save_json(CONFIG_PATH, setup_state)

    print(f"Telegram profile configured: {profile}")
    print(f"Profile env: {generated_module_env_path(gateway, profile)}")
    print(f"Secret {profile_secret_id} -> {backend}")
    if bot_identity and bot_identity.get("username"):
        print(f"Connected Telegram bot: @{bot_identity['username']}")
    print(f"Spawner mission relay URL added: {webhook_url}")
    print("Start it with:")
    print(f"  spark start spark-telegram-bot --profile {profile}")
    print("Read its logs with:")
    print(f"  spark logs spark-telegram-bot --profile {profile}")
    return 0


def cmd_telegram_connect(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    profile = normalize_telegram_profile(getattr(args, "profile", None) or primary_telegram_profile())
    token = getattr(args, "token", None)
    if not token:
        token = read_secret_interactive(f"Paste BotFather token for {profile} (typing is masked): ")
    args.profile = profile
    args.bot_token = token
    args.telegram_relay_port = getattr(args, "telegram_relay_port", None)
    args.skip_telegram_token_check = getattr(args, "skip_telegram_token_check", False)
    configure_telegram_profile(args)
    if getattr(args, "no_restart", False):
        print("Token saved. Restart later with:")
        print(f"  spark restart spark-telegram-bot --profile {profile}")
        return 0
    print("")
    print(f"Restarting Telegram profile {profile} now...")
    return cmd_restart(
        argparse.Namespace(
            target="spark-telegram-bot",
            profile=profile,
            allow_boot_warnings=False,
        )
    )


def initialize_builder_runtime_home(
    modules_by_name: dict[str, Module],
    secret_values: dict[str, str] | None = None,
    setup_state: dict[str, Any] | None = None,
) -> list[str]:
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

            sidecar_state = setup_state.get("memory_sidecars") if isinstance(setup_state, dict) else None
            graphiti_state = sidecar_state.get("graphiti") if isinstance(sidecar_state, dict) else None
            if isinstance(graphiti_state, dict) and graphiti_state.get("enabled") is True:
                backend = str(graphiti_state.get("backend") or "kuzu")
                db_path = resolve_builder_graphiti_db_path(builder_home, graphiti_state.get("db_path"))
                db_path.parent.mkdir(parents=True, exist_ok=True)
                config_manager.set_path("spark.memory.sidecars.graphiti.enabled", True)
                config_manager.set_path("spark.memory.sidecars.graphiti.backend", backend)
                config_manager.set_path("spark.memory.sidecars.graphiti.db_path", str(db_path))
                config_manager.set_path(
                    "spark.memory.sidecars.graphiti.group_id",
                    str(graphiti_state.get("group_id") or DEFAULT_GRAPHITI_GROUP_ID),
                )
                notes.append(f"enabled Graphiti {backend} memory sidecar at {db_path}")
            elif isinstance(graphiti_state, dict) and graphiti_state.get("enabled") is False:
                config_manager.set_path("spark.memory.sidecars.graphiti.enabled", False)
                notes.append("disabled optional Graphiti memory sidecar")

        voice = modules_by_name.get(VOICE_MODULE_NAME)
        if voice is not None:
            add_attachment_root(config_manager, target="chips", root=str(voice.path))
            config_manager.set_path("spark.voice.enabled", True)
            config_manager.set_path("spark.voice.comms_root", str(voice.path))
            activate_chip(config_manager, chip_key=VOICE_MODULE_NAME)
            sync_attachment_snapshot(config_manager=config_manager, state_db=state_db)
            notes.append(f"activated {VOICE_MODULE_NAME} at {voice.path}")

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
    *,
    bundle_name: str | None = None,
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
            subject = (
                f"bundle `{bundle_name}` requires module `{candidate.name}`, which needs required capability `{capability}`"
                if bundle_name
                else f"{candidate.name} needs required capability `{capability}`"
            )
            repair = (
                f"spark setup {bundle_name}"
                if bundle_name
                else f"spark install {sorted(suggestions)[0]}"
                if suggestions
                else f"install a module that provides `{capability}`"
            )
            if suggestions:
                errors.append(
                    f"{subject}; provider module(s): {', '.join(sorted(suggestions))}; repair: {repair}"
                )
            else:
                errors.append(
                    f"{subject}; no discoverable module provides it; repair: {repair}"
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
    assert_no_linked_write_path(path)
    require_write_allowed(path, safe_root=spark_write_safe_root(), subject="module env write")
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
    assert_no_linked_write_path(path)
    require_write_allowed(path, safe_root=spark_write_safe_root(), subject="module env cleanup")
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
    if not modules:
        print("No installed Spark modules recorded.")
        print("Run `spark setup telegram-starter` to install the starter bundle.")
        return 0
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
            clone_path = clone_module_source(
                target,
                source,
                commit=str(registry_metadata.get("commit", "")),
                require_signed_commit=bool(registry_metadata.get("require_signed_commit", False)),
            )
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
    registry_commit = str(registry_metadata.get("commit") or "").strip().lower()
    registry_source = str(registry_metadata.get("source") or "").strip()
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

    record = {
        **existing,
        "path": str(module.path),
        "source": str(module.path),
        "registry_source": registry_source,
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
    if registry_commit:
        record["registry_commit"] = registry_commit
    installed[module.name] = record
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
    installed.setdefault("registry_source", str(registry_metadata.get("source") or ""))
    installed.setdefault("registry_commit", str(registry_metadata.get("commit") or "").strip().lower())
    installed.setdefault("version", module.version)
    installed.setdefault("kind", module.kind)
    installed.setdefault("plane", module.plane)
    installed.setdefault("summary", str(registry_metadata.get("summary") or module.manifest.get("module", {}).get("description", "")))
    installed.setdefault("blessed", bool(registry_metadata.get("blessed", False)))
    for key in ("path", "source"):
        if key in installed:
            installed[key] = public_local_path_ref(str(installed[key]))
    return public_diagnostic_payload(installed)


def public_local_path_ref(path: str | Path) -> str:
    raw = str(path or "")
    if not raw:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw, flags=re.IGNORECASE):
        return raw
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return raw.replace("\\", "/")
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        resolved = candidate.absolute()
    for root, label in ((SPARK_HOME, "<spark-home>"), (REPO_ROOT, "<spark-cli>")):
        try:
            root_resolved = root.resolve(strict=False)
            relative = resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        relative_text = relative.as_posix()
        return label if relative_text == "." else f"{label}/{relative_text}"
    return f"<local-path>/{candidate.name}"


def public_diagnostic_payload(value: Any) -> Any:
    if isinstance(value, dict):
        payload: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"path", "log_path", "source", "source_target", "target"} and isinstance(item, str):
                payload[key_text] = public_local_path_ref(item)
            else:
                payload[key_text] = public_diagnostic_payload(item)
        return payload
    if isinstance(value, list):
        return [public_diagnostic_payload(item) for item in value]
    if isinstance(value, str):
        return redact_shareable_text(value)
    return value


def remove_module_record(module_name: str) -> None:
    installed = load_json(REGISTRY_PATH, {})
    installed.pop(module_name, None)
    save_json(REGISTRY_PATH, installed)


def is_blessed_registry_entry(target: str) -> bool:
    metadata = load_registry_definition().get("modules", {}).get(target)
    if not metadata:
        return False
    return bool(metadata.get("blessed"))


def module_trust_tier(module: Module, target: str | None = None) -> str:
    registry_modules = load_registry_definition().get("modules", {})
    metadata = registry_modules.get(module.name) or (registry_modules.get(target) if target else {}) or {}
    configured = metadata.get("trust_tier") or module.manifest.get("trust", {}).get("tier")
    if metadata.get("blessed") and not configured:
        return "trusted"
    tier = str(configured or "community").strip().lower()
    return tier if tier in TRUST_TIERS else "community"


def chip_scan_blocks_tier(severity: str, trust_tier: str) -> bool:
    threshold = TRUST_BLOCK_THRESHOLD.get(trust_tier, "high")
    return CHIP_SCAN_SEVERITY_RANK.get(severity, 0) >= CHIP_SCAN_SEVERITY_RANK[threshold]


def chip_scan_relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def chip_scan_text(path_label: str, text: str) -> list[ChipScanFinding]:
    findings: list[ChipScanFinding] = []
    for category, severity, pattern, detail in CHIP_SCAN_PATTERNS:
        if pattern.search(text):
            findings.append(ChipScanFinding(category, severity, path_label, detail))
    for finding in scan_prompt_injection_text(path_label, text):
        findings.append(ChipScanFinding(finding.category, finding.severity, finding.path, finding.detail))
    return findings


def chip_scan_is_fixture_path(path_label: str) -> bool:
    parts = {part.lower() for part in Path(path_label).parts}
    return bool(parts & CHIP_SCAN_FIXTURE_DIRS)


def normalize_fixture_finding(finding: ChipScanFinding) -> ChipScanFinding:
    if finding.category in {"embedded-private-key", "network-exfiltration", "environment-dump"} and chip_scan_is_fixture_path(finding.path):
        return ChipScanFinding(
            finding.category,
            "low",
            finding.path,
            f"{finding.detail}; appears in test/fixture code and is not installed as runtime secret material",
        )
    return finding


def chip_scan_package_json(path_label: str, text: str) -> list[ChipScanFinding]:
    if Path(path_label).name != "package.json":
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return []
    findings: list[ChipScanFinding] = []
    for script_name in ("preinstall", "install", "postinstall", "prepare"):
        command = scripts.get(script_name)
        if not isinstance(command, str) or not command.strip():
            continue
        lowered = command.lower()
        severity = "medium"
        detail = f"package.json script `{script_name}` runs during dependency install"
        if any(token in lowered for token in ("curl", "wget", "invoke-webrequest", "powershell", " bash", " sh", "node -e", "python -c")):
            severity = "high"
            detail = f"package.json script `{script_name}` can run shell/network code during dependency install"
        findings.append(ChipScanFinding("package-install-script", severity, path_label, detail))
    return findings


def chip_scan_file(root: Path, path: Path) -> list[ChipScanFinding]:
    relative = chip_scan_relative_path(root, path)
    suffix = path.suffix.lower()
    findings: list[ChipScanFinding] = []
    try:
        stat_result = path.stat()
    except OSError as error:
        return [ChipScanFinding("unreadable-file", "medium", relative, error.__class__.__name__)]
    if suffix in CHIP_SCAN_EXECUTABLE_SUFFIXES:
        findings.append(ChipScanFinding("executable-binary", "high", relative, "binary executable is present in the module"))
    if stat_result.st_size > CHIP_SCAN_MAX_FILE_BYTES:
        return findings
    if path.name in CHIP_SCAN_SKIP_FILES or suffix not in CHIP_SCAN_TEXT_SUFFIXES:
        return findings
    try:
        data = path.read_bytes()
    except OSError as error:
        return [*findings, ChipScanFinding("unreadable-file", "medium", relative, error.__class__.__name__)]
    if b"\0" in data:
        return findings
    text = data.decode("utf-8", errors="replace")
    return [normalize_fixture_finding(finding) for finding in [*findings, *chip_scan_text(relative, text), *chip_scan_package_json(relative, text)]]


def scan_module_trust(module: Module, *, trust_tier: str | None = None) -> list[ChipScanFinding]:
    root = resolve_policy_path(module.path)
    if not root.exists():
        return []
    tier = trust_tier or module_trust_tier(module)
    findings: list[ChipScanFinding] = []
    total_bytes = 0
    scanned_files = 0
    path_type = root.__class__
    for current_root, dir_names, file_names in os.walk(root):
        current = path_type(current_root)
        dir_names[:] = [name for name in dir_names if name not in CHIP_SCAN_SKIP_DIRS]
        for name in list(dir_names):
            directory = current / name
            if not directory.is_symlink():
                continue
            target = resolve_policy_path(directory)
            if not policy_path_is_same_or_child(target, root):
                findings.append(
                    ChipScanFinding(
                        "symlink-escape",
                        "high",
                        chip_scan_relative_path(root, directory),
                        f"symlink target leaves module root: {target}",
                    )
                )
            dir_names.remove(name)
        for file_name in file_names:
            path = current / file_name
            if path.is_symlink():
                target = resolve_policy_path(path)
                if not policy_path_is_same_or_child(target, root):
                    findings.append(
                        ChipScanFinding(
                            "symlink-escape",
                            "high",
                            chip_scan_relative_path(root, path),
                            f"symlink target leaves module root: {target}",
                        )
                    )
                continue
            scanned_files += 1
            if scanned_files > CHIP_SCAN_MAX_FILES:
                findings.append(ChipScanFinding("module-size", "medium", ".", "module has too many files to scan completely"))
                return findings
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass
            if total_bytes > CHIP_SCAN_MAX_TOTAL_BYTES:
                findings.append(ChipScanFinding("module-size", "medium", ".", "module exceeds scanner byte budget"))
                return findings
            findings.extend(chip_scan_file(root, path))
    if tier == "builtin":
        return [finding for finding in findings if finding.severity == "critical"]
    return findings


def enforce_module_trust_scan(module: Module, target: str | None = None) -> None:
    tier = module_trust_tier(module, target)
    findings = scan_module_trust(module, trust_tier=tier)
    blocked = [finding for finding in findings if chip_scan_blocks_tier(finding.severity, tier)]
    if blocked:
        detail = "\n  - ".join(finding.format() for finding in blocked[:8])
        extra = "" if len(blocked) <= 8 else f"\n  - ...and {len(blocked) - 8} more"
        raise SystemExit(
            f"Module `{module.name}` failed the {tier} trust-tier scan:\n  - {detail}{extra}\n"
            "Review the module contents or move it to a stricter trust boundary before installing/running it."
        )


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
    enforce_module_trust_scan(module, target)
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
        result = run_install_command(command, module.path)
        if result.returncode != 0:
            raise SystemExit(
                f"{module.name} install command failed: {summarize_command_output(result)}"
            )


def run_module_hook(module: Module, hook_name: str) -> None:
    command = module.hook_command(hook_name)
    if not command:
        return
    result = run_runtime_command(command, module.path, env=module_runtime_env(module))
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
    runtime_env = module_runtime_env(module)
    if module.name == "spawner-ui" and spawner_should_use_liveness_endpoint(runtime_env):
        health_url = spawner_runtime_health_url(module, runtime_env)
        failure_hint = str(module.manifest.get("healthcheck", {}).get("failure_hint", "")).strip() or None
        success_hint = str(module.manifest.get("healthcheck", {}).get("success_hint", "")).strip() or None
        try:
            request = urllib.request.Request(health_url, headers=ready_check_headers(health_url))
            with urllib.request.urlopen(request, timeout=ready_timeout_seconds(module)) as response:
                healthy = 200 <= int(response.status) < 300
                detail = f"Spawner UI live health {'OK' if healthy else 'failed'}: HTTP {response.status}"
        except Exception as exc:
            healthy = False
            detail = f"Spawner UI live health failed: {exc}"
        return {
            "name": module.name,
            "version": module.version,
            "kind": module.kind,
            "plane": module.plane,
            "healthy": healthy,
            "detail": detail,
            "healthcheck_command": f"GET {health_url}",
            "failure_hint": failure_hint,
            "success_hint": success_hint,
        }
    if module.name == "spark-telegram-bot" and telegram_ingress_is_external():
        return {
            "name": module.name,
            "version": module.version,
            "kind": module.kind,
            "plane": module.plane,
            "healthy": True,
            "detail": "Telegram ingress is external; this Spark Live runtime does not store or poll the bot token.",
            "healthcheck_command": None,
            "failure_hint": None,
            "success_hint": "External Telegram ingress owner is expected to run its own healthcheck.",
        }
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
    result = run_runtime_command(command, module.path, env=runtime_env, timeout=timeout_seconds)
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
        wrapper = public_local_path_ref(SPARK_HOME / "bin" / ("spark.cmd" if os.name == "nt" else "spark"))
        hints.append(f"Repair runtime first: {runtime_detail}. If you used install.sh, run Spark through the installed wrapper at `{wrapper}` so managed Node/Python are on PATH.")
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
            "No LLM provider is configured. Run `spark setup` to choose an Agent provider and Mission provider."
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
            elif provider == "codex" and detect_codex_cli()["present"]:
                auth_mode = "codex_oauth"
            elif provider == "openai":
                base_kind = openai_base_url_kind(str(state.get("base_url") or llm_state.get("base_url") or ""))
                if base_kind == "local":
                    auth_mode = "local"
                elif base_kind == "default" and detect_codex_cli()["present"]:
                    auth_mode = "codex_oauth"
            elif provider == "anthropic" and detect_claude_code()["present"]:
                auth_mode = "claude_oauth"
            elif provider == "ollama":
                auth_mode = "local"
        role_label = "LLM provider" if role == "all" else f"LLM role `{role}`"
        role_flag = "--llm-provider" if role == "all" else f"--{role}-llm-provider"
        if provider == "not_configured":
            hints.append(
                f"{role_label} is not configured. Run `spark setup {role_flag} codex` for OpenAI Codex sign-in, or choose anthropic, zai, kimi, openrouter, huggingface, minimax, lmstudio, ollama, or openai."
            )
        elif provider in {"zai", "kimi", "minimax", "openrouter", "huggingface"} and auth_mode == "not_configured":
            label = LLM_PROVIDER_LABELS.get(provider, provider)
            hints.append(
                f"{role_label} uses {label} but is missing an API key. Re-run `spark setup {role_flag} {provider} --{provider}-api-key <key>`."
            )
        elif provider == "anthropic" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses Anthropic Claude but neither Anthropic Claude Code nor ANTHROPIC_API_KEY is configured. Run `claude` to sign in so Spark can call `claude -p`, or rerun `spark setup {role_flag} anthropic --anthropic-api-key <key>`."
            )
        elif provider == "openai" and auth_mode == "not_configured" and openai_base_url_kind(str(state.get("base_url") or llm_state.get("base_url") or "")) == "remote_custom":
            hints.append(
                f"{role_label} uses a custom OpenAI-compatible endpoint but is missing an API key. Re-run `spark setup {role_flag} openai --openai-api-key <key> --openai-base-url <url>`."
            )
        elif provider == "openai" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses OpenAI API but OPENAI_API_KEY is not configured. Rerun `spark setup {role_flag} openai --openai-api-key <key>`, or use `spark setup {role_flag} codex` for OpenAI Codex sign-in."
            )
        elif provider == "codex" and auth_mode == "not_configured":
            hints.append(
                f"{role_label} uses OpenAI Codex but the OpenAI Codex CLI is not signed in or not on PATH. Run `codex login` first, then rerun `spark setup {role_flag} codex`."
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
        unmet = validate_capability_needs_for_install(bundle_modules, installed_modules, modules, bundle_name=args.target)
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


def print_setup_next_steps(
    bundle_name: str,
    ingress_owner: Module,
    llm_state: dict[str, Any],
    setup_state: dict[str, Any],
    *,
    start_now: bool,
    start_ok: bool,
    autostart_enabled: bool,
) -> None:
    provider = llm_state.get("provider") or "unknown"
    model = llm_state.get("model") or "not configured"
    roles = llm_state.get("roles") if isinstance(llm_state.get("roles"), dict) else {}
    session = str(setup_state.get("onboarding_session") or new_onboarding_session_code())
    telegram_label = "@YourSparkBot"
    print("")
    if start_now and start_ok:
        print("Spark is ready.")
    elif start_now:
        print("Spark is installed, but not running yet.")
    else:
        print("Spark is configured, but not started yet.")
    print("")
    print(f"Telegram: {telegram_label}")
    print(f"Autostart: {'enabled' if autostart_enabled else 'disabled'}")
    access_state = setup_state.get("access") if isinstance(setup_state, dict) else None
    if isinstance(access_state, dict):
        preflight = access_state.get("workspace_preflight") if isinstance(access_state.get("workspace_preflight"), dict) else {}
        ready_label = "ready" if preflight.get("writable") else "needs attention"
        print("")
        print(f"Access: Level 4 safe workspace is {ready_label} at {access_state.get('workspace_path')}.")
        print("Recommended for builders: choose Level 4 when prompted so Mission Control can work in this workspace.")
        print("Choose a lower level only for chat-only or public-research installs.")
        print("Spark uses workspace-write by default; whole-computer access is off.")
        print("Docker: optional stronger local isolation for riskier or reproducible work.")
        print("Modal: optional disposable cloud compute; Spark does not pass secrets or project files by default.")
        print("SSH: optional user-owned remote machine access, not the default sandbox.")
        print("Level 5 whole-computer mode stays off unless explicitly enabled with:")
        print("  spark access setup --level 5 --enable-high-agency")
    else:
        print("Recommended for builders: choose Level 4 when prompted so Mission Control can inspect and build in local workspaces.")
        print("Choose a lower level only for chat-only or public-research installs.")
    print("")
    print("Start chatting and building:")
    print("  1. Open your Spark bot in Telegram.")
    print(f"  2. If Telegram asks for a start code, send: /start {session}")
    print("  3. Send a normal message, or try: /run say exactly OK")
    print("")
    print("When you are ready, ask Spark how it can improve for your workflows.")
    print("Your agent will guide memory, missions, and self-improvement one step at a time.")
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
    voice_state = setup_state.get("voice") if isinstance(setup_state, dict) else None
    if isinstance(voice_state, dict) and voice_state.get("enabled"):
        print("")
        print("Voice:")
        if voice_state.get("elevenlabs_secret_configured"):
            print("  ElevenLabs key is stored in Spark secrets and injected into Builder at runtime.")
        else:
            print("  Voice chip is installed; choose hosted or local/private setup from Telegram.")
        print("  In Telegram, send: /voice self-test")
        print("  Then say: Guide me through ElevenLabs voice setup")
    print("")
    print("Checks:")
    print("  spark verify --onboarding")
    print("  spark fix telegram")
    print("  spark fix spawner")
    if not start_ok:
        print("")
        print("Mission Control or Spark did not fully start. Start it now:")
        print(f"  spark start {bundle_name}")
        print("  spark logs spawner-ui --lines 80")


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
    unmet = validate_capability_needs_for_install(bundle, installed_modules, modules, bundle_name=args.bundle)
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


def apply_setup_feature_aliases(args: argparse.Namespace) -> None:
    if not getattr(args, "with_voice", False):
        return
    if getattr(args, "bundle", "telegram-starter") == "telegram-starter":
        registry = load_registry_definition()
        if TELEGRAM_VOICE_BUNDLE not in registry.get("bundles", {}):
            raise SystemExit(f"`--with-voice` requires the `{TELEGRAM_VOICE_BUNDLE}` bundle in registry.json.")
        setattr(args, "bundle", TELEGRAM_VOICE_BUNDLE)
        return
    if VOICE_MODULE_NAME not in resolve_bundle_names(str(getattr(args, "bundle", ""))):
        raise SystemExit(f"`--with-voice` is only supported with `telegram-starter` or a bundle that includes `{VOICE_MODULE_NAME}`.")


def voice_setup_state(args: argparse.Namespace, bundle: list[Module], secret_values: dict[str, str]) -> dict[str, Any] | None:
    if not any(module.name == VOICE_MODULE_NAME for module in bundle):
        return None
    return {
        "enabled": True,
        "module": VOICE_MODULE_NAME,
        "elevenlabs_secret_configured": bool(secret_values.get("voice.elevenlabs.api_key")),
        "telegram_checks": ["/voice self-test", "/voice provider", "/voice speak Clean reset, Cem. Latest message wins."],
    }


def collect_setup_configuration(
    args: argparse.Namespace,
    bundle: list[Module],
    ingress_owner: Module,
    interactive: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Collect secrets and LLM choices, then build the persisted setup state."""
    from .sandbox.access import safe_workspace_setup_state

    existing_setup = load_json(CONFIG_PATH, {})
    if interactive:
        secret_values = collect_secret_values(args, bundle, interactive=False, allow_missing=True)
        secret_values = run_llm_provider_wizard(args, secret_values)
        secret_values = collect_secret_values(args, bundle, interactive=True, existing_values=secret_values)
    else:
        secret_values = collect_secret_values(args, bundle, interactive=False)
    secret_values = ensure_generated_setup_secrets(secret_values, bundle)
    llm_provider, llm_env = build_llm_env(args, secret_values)
    preserved_secret_keys = set(existing_setup.get("secret_keys", [])) if isinstance(existing_setup, dict) else set()
    preserved_profiles = existing_setup.get("telegram_profiles") if isinstance(existing_setup, dict) else None
    preserved_primary_profile = existing_setup.get(PRIMARY_TELEGRAM_PROFILE_KEY) if isinstance(existing_setup, dict) else None
    preserved_onboarding_session = existing_setup.get("onboarding_session") if isinstance(existing_setup, dict) else None
    if getattr(args, "external_telegram_ingress", False):
        stale_telegram_secret_ids = {
            key
            for key in preserved_secret_keys | set(secret_values.keys())
            if key in {"telegram.bot_token", "telegram.admin_ids"}
            or (key.startswith("telegram.profiles.") and key.endswith(".bot_token"))
        }
        for secret_id in stale_telegram_secret_ids:
            delete_secret(secret_id)
        preserved_secret_keys.difference_update(stale_telegram_secret_ids)
        preserved_profiles = None
        preserved_primary_profile = None
    setup_state = {
        "bundle": args.bundle,
        "modules": [module.name for module in bundle],
        "telegram_ingress_owner": ingress_owner.name,
        "telegram_ingress_mode": "external" if getattr(args, "external_telegram_ingress", False) else "local",
        "configured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "secret_keys": sorted(preserved_secret_keys | set(secret_values.keys())),
        "llm": llm_setup_state(llm_provider, llm_env),
        "builder_home": str(spark_builder_home()),
        "access": safe_workspace_setup_state(home=SPARK_HOME),
        "onboarding_session": (
            str(preserved_onboarding_session).strip()
            if isinstance(preserved_onboarding_session, str) and preserved_onboarding_session.strip()
            else new_onboarding_session_code()
        ),
    }
    sidecar_state = memory_sidecar_setup_state(args, existing_setup if isinstance(existing_setup, dict) else None)
    if sidecar_state is not None:
        setup_state["memory_sidecars"] = sidecar_state
    voice_state = voice_setup_state(args, bundle, secret_values)
    if voice_state is not None:
        setup_state["voice"] = voice_state
    if isinstance(preserved_profiles, dict) and preserved_profiles:
        setup_state["telegram_profiles"] = preserved_profiles
    if isinstance(preserved_primary_profile, str) and preserved_primary_profile.strip():
        setup_state[PRIMARY_TELEGRAM_PROFILE_KEY] = normalize_telegram_profile(preserved_primary_profile)
    else:
        setup_state[PRIMARY_TELEGRAM_PROFILE_KEY] = DEFAULT_PRIMARY_TELEGRAM_PROFILE
    primary_profile_secret = telegram_profile_secret_id(setup_state[PRIMARY_TELEGRAM_PROFILE_KEY], "bot_token")
    if "telegram.bot_token" in secret_values and primary_profile_secret not in secret_values:
        secret_values[primary_profile_secret] = secret_values["telegram.bot_token"]
        setup_state["secret_keys"] = sorted(set(setup_state["secret_keys"]) | {primary_profile_secret})
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


def install_memory_sidecar_dependencies(
    args: argparse.Namespace,
    modules: dict[str, Module],
    setup_state: dict[str, Any],
) -> None:
    """Install explicit optional memory sidecar extras after the base bundle exists."""
    sidecar_state = setup_state.get("memory_sidecars") if isinstance(setup_state, dict) else None
    enabled = set(sidecar_state.get("enabled") or []) if isinstance(sidecar_state, dict) else set()
    if "graphiti-kuzu" not in enabled:
        return
    memory = modules.get("domain-chip-memory")
    if memory is None:
        print("Skipping Graphiti/Kuzu sidecar extra: domain-chip-memory is not in this setup bundle.")
        return
    if getattr(args, "skip_install_commands", False):
        print("Skipping Graphiti/Kuzu sidecar extra install because --skip-install-commands was provided.")
        return
    install_target = f"{memory.path}[graphiti-kuzu]"
    print("Installing optional Graphiti/Kuzu memory sidecar extra for domain-chip-memory...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", install_target], check=True)


def write_setup_runtime_config(
    args: argparse.Namespace,
    modules: dict[str, Module],
    bundle: list[Module],
    secret_values: dict[str, str],
    setup_state: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Write Builder state, keychain secrets, and generated module env files."""
    builder_notes = initialize_builder_runtime_home(modules, secret_values, setup_state)
    keychain_report = persist_keychain_secrets(bundle, secret_values)
    generated_envs = build_module_envs(args, modules, secret_values)
    for module in bundle:
        env_values = strip_keychain_env_vars(generated_envs.get(module.name, {}), module)
        env_values = preserve_level5_guardrails(module.name, env_values)
        generated_path = generated_module_env_path(module)
        write_generated_env(generated_path, env_values)
        env_path = module_env_path(module)
        if env_path is not None and env_values:
            update_env_file(env_path, env_values)
    refresh_telegram_profile_envs(modules)
    return builder_notes, keychain_report


def refresh_telegram_profile_envs(modules: dict[str, Module]) -> None:
    gateway = modules.get("spark-telegram-bot")
    if gateway is None:
        return
    setup_state = load_json(CONFIG_PATH, {})
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    if not isinstance(profiles, dict):
        return
    base_env = read_generated_env(generated_module_env_path(gateway))
    for profile, profile_state in profiles.items():
        if not isinstance(profile_state, dict):
            continue
        normalized = normalize_telegram_profile(str(profile))
        if telegram_profile_is_default(normalized):
            continue
        existing_env = read_generated_env(generated_module_env_path(gateway, normalized))
        refreshed_env = dict(base_env)
        if existing_env.get("ADMIN_TELEGRAM_IDS"):
            refreshed_env["ADMIN_TELEGRAM_IDS"] = existing_env["ADMIN_TELEGRAM_IDS"]
        refreshed_env["TELEGRAM_GATEWAY_MODE"] = "polling"
        refreshed_env["TELEGRAM_RELAY_PORT"] = str(profile_state.get("relay_port") or existing_env.get("TELEGRAM_RELAY_PORT") or "")
        refreshed_env["SPARK_TELEGRAM_PROFILE"] = normalized
        refreshed_env.pop("BOT_TOKEN", None)
        write_generated_env(generated_module_env_path(gateway, normalized), refreshed_env)


def builder_runtime_env_refs_from_installed(installed: object) -> dict[str, str]:
    builder_path = installed_record_path(installed, "spark-intelligence-builder")
    if builder_path is None:
        return {}
    return {
        "SPARK_BUILDER_REPO": str(builder_path),
        "SPARK_BUILDER_HOME": str(spark_builder_home()),
        "SPARK_BUILDER_PYTHON": str(Path(sys.executable)),
        "SPARK_BUILDER_BRIDGE_MODE": "required",
    }


def installed_records_from_modules(modules_by_name: dict[str, Module]) -> dict[str, dict[str, str]]:
    return {name: {"path": str(module.path)} for name, module in modules_by_name.items()}


def _mapping_path_candidates(values: dict[str, str], name: str) -> list[Path]:
    raw = values.get(name, "")
    if not raw.strip():
        return []
    return [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def _mapping_named_path_candidates(values: dict[str, str], prefix: str, suffix: str) -> list[Path]:
    candidates: list[Path] = []
    for name, raw in values.items():
        if not name.startswith(prefix) or not name.endswith(suffix) or not raw.strip():
            continue
        candidates.append(Path(raw).expanduser())
    return candidates


def specialization_repo_env_var(path_key: str) -> str:
    normalized = str(path_key or "").strip().upper().replace("-", "_")
    return f"SPARK_SWARM_SPECIALIZATION_PATH_{normalized}_REPO"


def _specialization_path_candidates_from_values(values: dict[str, str]) -> list[Path]:
    return [
        *_mapping_path_candidates(values, "SPARK_SPECIALIZATION_PATH_ROOTS"),
        *_mapping_named_path_candidates(values, "SPARK_SWARM_SPECIALIZATION_PATH_", "_REPO"),
    ]


def telegram_specialization_runtime_env_refs_from_installed(
    installed: object,
    current_env: dict[str, str] | None = None,
) -> dict[str, str]:
    current = current_env or {}
    refs: dict[str, str] = {}
    env_values = dict(os.environ)
    swarm_root = first_existing_path(unique_path_candidates([
        *_mapping_path_candidates(current, "SPARK_SWARM_REPO"),
        *_mapping_path_candidates(current, "SPARK_SWARM_ROOT"),
        *_mapping_path_candidates(current, "SPARK_SWARM_RUNTIME_ROOT"),
        *env_path_candidates("SPARK_SWARM_REPO"),
        *env_path_candidates("SPARK_SWARM_ROOT"),
        *env_path_candidates("SPARK_SWARM_RUNTIME_ROOT"),
        *(candidate for candidate in [installed_path_candidate(installed, "spark-swarm")] if candidate is not None),
    ]))
    if swarm_root is not None:
        bridge_src = swarm_root / "apps" / "bridge" / "src"
        refs["SPARK_SWARM_REPO"] = str(swarm_root)
        refs["SPARK_SWARM_ROOT"] = str(swarm_root)
        refs["SPARK_SWARM_RUNTIME_ROOT"] = str(swarm_root)
        if (bridge_src / "spark_swarm_bridge" / "cli.py").exists():
            refs["SPARK_SWARM_BRIDGE_SRC"] = str(bridge_src)

    explicit_bridge_src = first_existing_path(unique_path_candidates([
        *_mapping_path_candidates(current, "SPARK_SWARM_BRIDGE_SRC"),
        *env_path_candidates("SPARK_SWARM_BRIDGE_SRC"),
    ]))
    if explicit_bridge_src is not None:
        refs["SPARK_SWARM_BRIDGE_SRC"] = str(explicit_bridge_src)

    startup_bench = first_existing_path(unique_path_candidates([
        *_mapping_path_candidates(current, "SPARK_STARTUP_BENCH_REPO"),
        *env_path_candidates("SPARK_STARTUP_BENCH_REPO"),
        *(candidate for candidate in [installed_path_candidate(installed, "startup-bench")] if candidate is not None),
    ]))
    if startup_bench is not None:
        refs["SPARK_STARTUP_BENCH_REPO"] = str(startup_bench)

    path_roots = unique_path_candidates([
        *_specialization_path_candidates_from_values(current),
        *_specialization_path_candidates_from_values(env_values),
        *specialization_path_candidates(installed),
    ])
    usable_paths = [path for path in path_roots if path.exists() and specialization_path_is_usable(path)]
    if usable_paths:
        refs["SPARK_SPECIALIZATION_PATH_ROOTS"] = os.pathsep.join(str(path) for path in usable_paths)
    for path in usable_paths:
        refs[specialization_repo_env_var(specialization_path_key(path))] = str(path)
    return refs


def telegram_generated_env_paths(setup_state: dict[str, Any] | None = None) -> list[Path]:
    paths = [MODULE_CONFIG_DIR / "spark-telegram-bot.env"]
    state = setup_state if isinstance(setup_state, dict) else load_json(CONFIG_PATH, {})
    profile_names: set[str] = set()
    profiles = state.get("telegram_profiles") if isinstance(state, dict) else None
    if isinstance(profiles, dict):
        for profile, profile_state in profiles.items():
            normalized = normalize_telegram_profile(str(profile))
            if isinstance(profile_state, dict) and not telegram_profile_is_default(normalized):
                profile_names.add(normalized)
    if MODULE_CONFIG_DIR.exists():
        for path in MODULE_CONFIG_DIR.glob("spark-telegram-bot.*.env"):
            prefix = "spark-telegram-bot."
            suffix = ".env"
            name = path.name
            if name.startswith(prefix) and name.endswith(suffix):
                normalized = normalize_telegram_profile(name[len(prefix):-len(suffix)])
                if not telegram_profile_is_default(normalized):
                    profile_names.add(normalized)
    for profile in sorted(profile_names):
        paths.append(MODULE_CONFIG_DIR / f"spark-telegram-bot.{profile}.env")
    return paths


def refresh_telegram_builder_runtime_refs(
    installed: object | None = None,
    setup_state: dict[str, Any] | None = None,
) -> list[Path]:
    installed_records = installed if installed is not None else load_json(REGISTRY_PATH, {})
    refs = builder_runtime_env_refs_from_installed(installed_records)
    if not refs:
        return []
    changed: list[Path] = []
    paths = telegram_generated_env_paths(setup_state)
    existing_by_path = {path: read_generated_env(path) for path in paths if path.exists()}
    existing_refs: dict[str, str] = {}
    for values in existing_by_path.values():
        existing_refs.update(values)
    setup_state_for_profiles = setup_state if isinstance(setup_state, dict) else load_json(CONFIG_PATH, {})
    primary_profile = primary_telegram_profile(setup_state_for_profiles)
    primary_relay_port = telegram_profile_relay_port(setup_state_for_profiles, primary_profile)
    base_gateway_env_path = MODULE_CONFIG_DIR / "spark-telegram-bot.env"
    for path in paths:
        if not path.exists():
            continue
        current = existing_by_path.get(path, {})
        if not current:
            continue
        next_values = dict(current)
        if path == base_gateway_env_path:
            next_values["SPARK_TELEGRAM_PROFILE"] = primary_profile
            next_values["TELEGRAM_RELAY_PORT"] = str(primary_relay_port)
        next_values.update(refs)
        next_values.update(telegram_specialization_runtime_env_refs_from_installed(
            installed_records,
            {**existing_refs, **current},
        ))
        if next_values != current:
            write_generated_env(path, next_values)
            changed.append(path)
    return changed


def runtime_path_values_equal(actual: str, expected: str) -> bool:
    if not actual or not expected:
        return actual == expected
    try:
        actual_path = os.path.normcase(os.path.normpath(os.fspath(Path(actual).expanduser())))
        expected_path = os.path.normcase(os.path.normpath(os.fspath(Path(expected).expanduser())))
    except (OSError, RuntimeError, ValueError):
        return actual == expected
    return actual_path == expected_path


def builder_runtime_ref_errors(installed: object, gateway_env: dict[str, str]) -> list[str]:
    refs = builder_runtime_env_refs_from_installed(installed)
    if not refs:
        return ["spark-intelligence-builder is not installed."]
    errors: list[str] = []
    for key in ("SPARK_BUILDER_REPO", "SPARK_BUILDER_BRIDGE_MODE"):
        expected = refs[key]
        actual = gateway_env.get(key, "")
        if key in {"SPARK_BUILDER_REPO", "SPARK_BUILDER_HOME", "SPARK_BUILDER_PYTHON"}:
            matches = runtime_path_values_equal(actual, expected)
            if not matches:
                actual_label = public_local_path_ref(actual) if actual else "missing"
                expected_label = public_local_path_ref(expected)
                errors.append(f"{key}={actual_label}; expected {expected_label}")
        elif actual != expected:
            errors.append(f"{key}={actual or 'missing'}; expected {expected}")
    return errors


def print_setup_summary(
    args: argparse.Namespace,
    ingress_owner: Module,
    builder_notes: list[str],
    keychain_report: dict[str, str],
    setup_state: dict[str, Any],
    *,
    start_now: bool = False,
    start_ok: bool = False,
) -> None:
    print("Spark setup complete.")
    print(f"Bundle: {args.bundle}")
    print(f"Telegram ingress owner: {ingress_owner.name}")
    if getattr(args, "external_telegram_ingress", False):
        print("Telegram ingress mode: external; no bot token stored in this Spark Live runtime.")
    else:
        print("Bot token routed only to spark-telegram-bot.")
    print(f"Generated module config dir: {MODULE_CONFIG_DIR}")
    for note in builder_notes:
        print(f"Builder runtime: {note}")
    if keychain_report:
        for secret_id, backend in sorted(keychain_report.items()):
            print(f"Secret {secret_id} -> {backend}")
    print_setup_next_steps(
        args.bundle,
        ingress_owner,
        setup_state["llm"],
        setup_state,
        start_now=start_now,
        start_ok=start_ok,
        autostart_enabled=bool(getattr(args, "autostart", True)),
    )


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    if not telegram_profile_is_default(getattr(args, "profile", None)):
        return configure_telegram_profile(args)
    apply_setup_feature_aliases(args)
    setup_state: dict[str, Any] | None = None
    pending = load_pending_setup_state() if getattr(args, "resume", False) else {}
    if pending:
        pending_bundle = str(pending.get("bundle") or "").strip()
        if pending_bundle and getattr(args, "bundle", "telegram-starter") == "telegram-starter":
            setattr(args, "bundle", pending_bundle)
        apply_setup_feature_aliases(args)
        print("Resuming pending Spark setup.")
        print(f"Last stop: {pending.get('detail') or pending.get('stage') or 'unknown'}")
    try:
        plan = resolve_setup_bundle_plan(args)
        interactive = setup_is_interactive(args)
        if interactive:
            print("")
            print("Spark is waking up.")
            print_setup_preflight(plan.bundle)
        secret_values, setup_state = collect_setup_configuration(
            args,
            plan.bundle,
            plan.ingress_owner,
            interactive,
        )
        setattr(args, "onboarding_session", setup_state.get("onboarding_session"))
        validate_new_telegram_bot_tokens(args, secret_values)
        save_json(CONFIG_PATH, setup_state)
        install_setup_bundle(args, plan.bundle, plan.installed_modules)
        install_memory_sidecar_dependencies(args, plan.modules, setup_state)
        builder_notes, keychain_report = write_setup_runtime_config(
            args,
            plan.modules,
            plan.bundle,
            secret_values,
            setup_state,
        )
        clear_pending_setup_state()
        start_now = bool(getattr(args, "start_now", True))
        start_ok = False
        if getattr(args, "autostart", True):
            print("")
            if start_now:
                print("Installing login autostart and starting Spark now.")
            else:
                print("Installing login autostart. Turn it off with: spark autostart off")
            start_ok = cmd_autostart_install(argparse.Namespace(target=args.bundle, now=start_now)) == 0
        elif start_now:
            print("")
            print("Starting Spark now.")
            start_ok = cmd_start(argparse.Namespace(target=args.bundle, profile=None)) == 0
        print_setup_summary(
            args,
            plan.ingress_owner,
            builder_notes,
            keychain_report,
            setup_state,
            start_now=start_now,
            start_ok=start_ok,
        )
        first_message_ok = True
        wait_seconds = first_message_wait_seconds(args, interactive)
        if start_now and start_ok and wait_seconds:
            print("")
            print("Waiting for Spark to hear you in Telegram...")
            result = wait_for_telegram_first_message(str(setup_state.get("onboarding_session") or ""), wait_seconds)
            print_first_message_wait_result(result)
            maybe_offer_first_message_repair(result, interactive)
            first_message_ok = bool(result.get("received") and result.get("replied"))
        return 0 if ((start_ok or not start_now) and first_message_ok) else 1
    except SystemExit as exc:
        detail = str(exc)
        save_pending_setup_state("setup", detail, setup_state)
        print_setup_failure_truth_screen(detail)
        raise


def cmd_onboard(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    pending = load_pending_setup_state()
    setup_state = load_json(CONFIG_PATH, {})
    installed = load_json(REGISTRY_PATH, {})
    bundle = str(getattr(args, "bundle", None) or pending.get("bundle") or setup_state.get("bundle") or "telegram-starter")
    setup_needed = bool(pending) or not CONFIG_PATH.exists() or not isinstance(installed, dict) or not installed

    if setup_needed:
        setup_argv = ["setup", bundle, "--resume"]
        setup_argv.append("--start-now" if getattr(args, "start_now", True) else "--no-start-now")
        setup_argv.append("--autostart" if getattr(args, "autostart", True) else "--no-autostart")
        if getattr(args, "non_interactive", False):
            setup_argv.append("--non-interactive")
        if not getattr(args, "wait_first_message", True):
            setup_argv.append("--no-wait-first-message")
        elif getattr(args, "wait_first_message_seconds", None) is not None:
            setup_argv.extend(["--wait-first-message-seconds", str(args.wait_first_message_seconds)])
        print("Spark onboard is resuming setup.")
        return cmd_setup(build_parser().parse_args(setup_argv))

    print("Spark onboard")
    print(f"Bundle: {bundle}")
    start_ok = True
    if getattr(args, "start_now", True):
        print("Starting Spark now.")
        start_ok = cmd_start(argparse.Namespace(target=bundle, profile=None, allow_boot_warnings=False, allow_dirty_runtime=False)) == 0

    session = str(setup_state.get("onboarding_session") or new_onboarding_session_code()) if isinstance(setup_state, dict) else new_onboarding_session_code()
    if isinstance(setup_state, dict) and setup_state.get("onboarding_session") != session:
        setup_state["onboarding_session"] = session
        save_json(CONFIG_PATH, setup_state)
    print("")
    print("Start chatting and building:")
    print("  1. Open your Spark bot in Telegram.")
    print(f"  2. If Telegram asks for a start code, send: /start {session}")
    print("  3. Send a normal message, or try: /run say exactly OK")
    print("")
    print("Checks:")
    print("  spark verify --onboarding")
    print("  spark fix telegram")

    first_message_ok = True
    wait_seconds = first_message_wait_seconds(args, setup_is_interactive(args))
    if start_ok and wait_seconds:
        print("")
        print("Waiting for Spark to hear you in Telegram...")
        result = wait_for_telegram_first_message(session, wait_seconds)
        print_first_message_wait_result(result)
        maybe_offer_first_message_repair(result, setup_is_interactive(args))
        first_message_ok = bool(result.get("received") and result.get("replied"))
    return 0 if start_ok and first_message_ok else 1


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
    for secret_id, value in secret_values.items():
        if secret_id in seen or not secret_id.startswith("telegram.profiles.") or not value:
            continue
        backend = store_secret(secret_id, value, preferred="keychain")
        report[secret_id] = backend
        seen.add(secret_id)
    return report


def command_with_managed_python(command: str) -> str:
    return subprocess.list2cmdline(install_command_argv(command))


def parse_memory_sidecars(value: str) -> list[str]:
    """Parse explicit optional memory sidecars for setup."""
    raw_parts = [part.strip().lower() for part in str(value or "").split(",")]
    parts = [part for part in raw_parts if part]
    if not parts:
        return []
    disabled = [part for part in parts if part in MEMORY_SIDECAR_DISABLE_CHOICES]
    if disabled:
        if len(parts) > 1:
            raise argparse.ArgumentTypeError("Use either 'none' or memory sidecar names, not both.")
        return []
    unknown = [part for part in parts if part not in MEMORY_SIDECAR_CHOICES]
    if unknown:
        choices = ", ".join(sorted(MEMORY_SIDECAR_CHOICES | MEMORY_SIDECAR_DISABLE_CHOICES))
        raise argparse.ArgumentTypeError(f"Unsupported memory sidecar {unknown[0]!r}. Choose one of: {choices}.")
    return sorted(set(parts))


def memory_sidecar_setup_state(
    args: argparse.Namespace,
    existing_setup: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build persisted optional memory sidecar setup state.

    The default setup path stays off. If setup is rerun without sidecar flags, preserve
    any prior explicit sidecar profile so `spark setup --resume` does not silently
    remove an advanced memory lane.
    """
    requested = getattr(args, "memory_sidecars", None)
    db_path_override = getattr(args, "graphiti_kuzu_db_path", None)
    if requested is None and db_path_override:
        requested = ["graphiti-kuzu"]
    if requested is None:
        existing = existing_setup.get("memory_sidecars") if isinstance(existing_setup, dict) else None
        return existing if isinstance(existing, dict) else None

    selected = list(requested or [])
    state: dict[str, Any] = {"enabled": selected}
    if "graphiti-kuzu" in selected:
        state["graphiti"] = {
            "enabled": True,
            "backend": "kuzu",
            "db_path": db_path_override or DEFAULT_GRAPHITI_KUZU_DB_PATH,
            "group_id": DEFAULT_GRAPHITI_GROUP_ID,
        }
    elif requested == []:
        state["graphiti"] = {"enabled": False, "backend": "kuzu"}
    return state


def resolve_builder_graphiti_db_path(builder_home: Path, configured_path: Any) -> Path:
    raw_path = str(configured_path or DEFAULT_GRAPHITI_KUZU_DB_PATH)
    resolved = raw_path.replace("{home}", str(builder_home)).replace("$SPARK_HOME", str(SPARK_HOME))
    path = Path(resolved).expanduser()
    if path.exists() and path.is_dir():
        path = path / "graphiti.kuzu"
    elif not path.suffix:
        path = path / "graphiti.kuzu"
    return path


def resolve_install_executable(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    if os.name == "nt" and not name.lower().endswith((".exe", ".cmd", ".bat", ".ps1")):
        for suffix in (".cmd", ".exe", ".bat"):
            path = shutil.which(name + suffix)
            if path:
                return path
    raise SystemExit(
        f"Missing required install tool `{name}`. Install it, reopen the terminal, then rerun the command. "
        "For Node modules, install Node.js 22+ or rerun Spark's installer with managed Node enabled."
    )


def install_command_argv(command: str) -> list[str]:
    parts = split_single_argv_command(command, "Install command")
    executable = parts[0].lower()
    if executable in {"python", "python3"}:
        return [str(Path(sys.executable)), *parts[1:]]
    if executable in {"pip", "pip3"}:
        return [str(Path(sys.executable)), "-m", "pip", *parts[1:]]
    if executable == "uv" and len(parts) >= 2 and parts[1] == "pip":
        return [str(Path(sys.executable)), "-m", "pip", *parts[2:]]
    if executable == "npm":
        return [resolve_install_executable("npm"), *parts[1:]]
    raise SystemExit(
        "Unsupported install command executable. Allowed install commands must start with "
        "python, python3, pip, pip3, uv pip, or npm."
    )


def run_install_command(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    require_write_allowed(cwd, safe_root=spark_write_safe_root(), subject="module install cwd")
    argv = install_command_argv(command)
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=write_boundary_env(shell_command_env(filtered=True)),
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return subprocess.CompletedProcess(argv, 124, stdout=stdout, stderr=stderr)
    except OSError as error:
        return subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"Could not start install command `{command}`: {error.__class__.__name__}. Check that the required tool is installed and on PATH.",
        )


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
    module_results = [public_diagnostic_payload(evaluate_module_health(module)) for module in modules.values()]
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
    public_tracked_pids = public_diagnostic_payload(tracked_pids)
    repair_hints = build_status_repair_hints(modules, module_results, setup_state, tracked_pids)
    ok = all(item["healthy"] is not False for item in module_results) and not repair_hints
    return {
        "ok": ok,
        "summary": "Spark CLI spike status",
        "telegram_ingress_owner": setup_state.get("telegram_ingress_owner"),
        "llm": setup_state.get("llm"),
        "telegram_profiles": telegram_profile_runtime_status(setup_state, tracked_pids),
        "modules": module_results,
        "tracked_pids": public_tracked_pids,
        "config_dir": public_local_path_ref(CONFIG_DIR),
        "repair_hints": repair_hints,
    }


def cmd_os_compile(args: argparse.Namespace) -> int:
    desktop = Path(args.desktop).expanduser()
    spark_home = Path(args.spark_home).expanduser()
    registry_path = Path(args.registry).expanduser()
    out_dir = Path(args.out).expanduser()
    compiled = compile_system_map(desktop=desktop, spark_home=spark_home, registry_path=registry_path)
    written = write_compiled_outputs(out_dir, compiled)
    summary = compile_summary(compiled, written)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print("Spark OS system map compiled")
    print(f"- modules: {summary['modules']}")
    print(f"- discovered repos: {summary['repos']}")
    print(f"- chip manifests: {summary['chip_manifests']}")
    print(f"- skill graphs: {summary['skill_graphs']}")
    print(f"- builder events: {summary.get('builder_event_rows') or 0}")
    print(f"- gaps: {summary['gaps']}")
    print(f"- output: {out_dir}")
    print("Redaction: no raw secrets, logs, conversations, memory evidence, or event summaries are exported.")
    return 0


def cmd_os_capabilities(args: argparse.Namespace) -> int:
    desktop = Path(args.desktop).expanduser()
    spark_home = Path(args.spark_home).expanduser()
    registry_path = Path(args.registry).expanduser()
    compiled = compile_system_map(desktop=desktop, spark_home=spark_home, registry_path=registry_path)
    catalog = compiled.get("capability_catalog") if isinstance(compiled, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    cards = catalog.get("capability_cards") if isinstance(catalog.get("capability_cards"), list) else []
    status_counts: dict[str, int] = {}
    surface_counts: dict[str, int] = {}
    proof_state_counts: dict[str, int] = {}
    trust_status_counts: dict[str, int] = {}
    proof_overall_status_counts: dict[str, int] = {}
    proof_verdict_status_counts: dict[str, int] = {}
    for card in cards:
        if not isinstance(card, dict):
            continue
        status = str(card.get("status") or "unknown")
        surface = str(card.get("surface_type") or "unknown")
        proof_state = str(card.get("proof_state") or "unknown")
        trust_status = str(card.get("trust_status") or "unknown")
        proof_summary = card.get("proof_summary") if isinstance(card.get("proof_summary"), dict) else {}
        proof_overall_status = str(proof_summary.get("overall_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        surface_counts[surface] = surface_counts.get(surface, 0) + 1
        proof_state_counts[proof_state] = proof_state_counts.get(proof_state, 0) + 1
        trust_status_counts[trust_status] = trust_status_counts.get(trust_status, 0) + 1
        proof_overall_status_counts[proof_overall_status] = proof_overall_status_counts.get(proof_overall_status, 0) + 1
        proof_verdicts = card.get("proof_verdicts") if isinstance(card.get("proof_verdicts"), dict) else {}
        for verdict in proof_verdicts.values():
            if not isinstance(verdict, dict):
                continue
            verdict_status = str(verdict.get("status") or "unknown")
            proof_verdict_status_counts[verdict_status] = proof_verdict_status_counts.get(verdict_status, 0) + 1

    payload = {
        "schema_version": "spark.os_capabilities.summary.v0",
        "generated_at": catalog.get("generated_at"),
        "card_count": len(cards),
        "status_counts": dict(sorted(status_counts.items())),
        "surface_counts": dict(sorted(surface_counts.items())),
        "proof_state_counts": dict(sorted(proof_state_counts.items())),
        "trust_status_counts": dict(sorted(trust_status_counts.items())),
        "proof_overall_status_counts": dict(sorted(proof_overall_status_counts.items())),
        "proof_verdict_status_counts": dict(sorted(proof_verdict_status_counts.items())),
        "cards": cards,
        "redaction": "Capability cards are compiled from metadata only; commands, packet bodies, logs, and raw evidence are omitted.",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Spark OS capabilities")
    print(f"- cards: {payload['card_count']}")
    for surface, count in payload["surface_counts"].items():
        print(f"- {surface}: {count}")
    for status, count in payload["status_counts"].items():
        print(f"- {status}: {count}")
    for proof_state, count in payload["proof_state_counts"].items():
        print(f"- proof {proof_state}: {count}")
    for trust_status, count in payload["trust_status_counts"].items():
        print(f"- trust {trust_status}: {count}")
    for proof_status, count in payload["proof_overall_status_counts"].items():
        print(f"- proof overall {proof_status}: {count}")
    for verdict_status, count in payload["proof_verdict_status_counts"].items():
        print(f"- proof verdict {verdict_status}: {count}")
    print("Redaction: commands, packet bodies, logs, and raw evidence are omitted.")
    return 0


def cmd_os_authority(args: argparse.Namespace) -> int:
    desktop = Path(args.desktop).expanduser()
    spark_home = Path(args.spark_home).expanduser()
    registry_path = Path(args.registry).expanduser()
    compiled = compile_system_map(desktop=desktop, spark_home=spark_home, registry_path=registry_path)
    authority = compiled.get("authority_view") if isinstance(compiled, dict) else {}
    authority = authority if isinstance(authority, dict) else {}
    guardrails = authority.get("guardrail_summary") if isinstance(authority.get("guardrail_summary"), dict) else {}
    cli_access = authority.get("cli_access") if isinstance(authority.get("cli_access"), dict) else {}
    telegram = (
        authority.get("telegram_access_policy")
        if isinstance(authority.get("telegram_access_policy"), dict)
        else {}
    )
    spawner = (
        authority.get("spawner_execution_policy")
        if isinstance(authority.get("spawner_execution_policy"), dict)
        else {}
    )
    browser = authority.get("browser_authority") if isinstance(authority.get("browser_authority"), dict) else {}
    public_output = (
        authority.get("public_output_authority")
        if isinstance(authority.get("public_output_authority"), dict)
        else {}
    )
    payload = {
        "schema_version": "spark.os_authority.summary.v0",
        "generated_at": authority.get("generated_at"),
        "default_access_level": authority.get("default_access_level_hint"),
        "default_sandbox_lane": cli_access.get("default_sandbox_lane"),
        "telegram_profiles": telegram.get("profiles") or [],
        "telegram_allow_matrix": telegram.get("allow_matrix") or {},
        "spawner_lanes": spawner.get("lane_ids") or [],
        "spawner_run_policies": spawner.get("run_policies") or [],
        "browser_risk_class_counts": browser.get("risk_class_counts") or {},
        "browser_approval_mode_counts": browser.get("approval_mode_counts") or {},
        "public_output_required_checks": public_output.get("required_publication_checks") or [],
        "guardrail_summary": guardrails,
        "authority": authority,
        "redaction": authority.get("redaction"),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Spark OS authority")
    print(f"- default access level: {payload['default_access_level']}")
    print(f"- default sandbox lane: {payload['default_sandbox_lane']}")
    print(f"- Telegram profiles: {len(payload['telegram_profiles'])}")
    print(f"- Spawner lanes: {len(payload['spawner_lanes'])}")
    print(f"- browser hooks: {browser.get('hook_count') or 0}")
    print(f"- toxic capability pairs: {guardrails.get('toxic_pair_count') or 0}")
    print(f"- publication checks required: {guardrails.get('publication_checks_required') or 0}")
    print("Redaction: policy constants and aggregate gate counts only; secrets and raw content are not read.")
    return 0


def _safe_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def cmd_os_trace(args: argparse.Namespace) -> int:
    desktop = Path(args.desktop).expanduser()
    spark_home = Path(args.spark_home).expanduser()
    registry_path = Path(args.registry).expanduser()
    compiled = compile_system_map(desktop=desktop, spark_home=spark_home, registry_path=registry_path)
    trace_index = _safe_mapping(compiled.get("trace_index") if isinstance(compiled, dict) else {})
    builder_events = _safe_mapping(trace_index.get("builder_events"))
    trace_health = _safe_mapping(trace_index.get("builder_trace_health"))
    trace_groups = _safe_mapping(trace_index.get("builder_trace_groups"))
    spawner = _safe_mapping(trace_index.get("spawner_prd_auto_trace_samples"))
    spawner_join = _safe_mapping(spawner.get("join_keys"))
    spawner_request_overlap = _safe_mapping(spawner.get("builder_request_overlap"))
    spawner_trace_overlap = _safe_mapping(spawner.get("builder_trace_ref_overlap"))
    telegram_gate = _safe_mapping(trace_index.get("telegram_final_answer_gate_samples"))
    telegram_join = _safe_mapping(telegram_gate.get("trace_join"))
    authority_verdicts = _safe_mapping(trace_index.get("authority_verdicts"))
    trace_current_health = _safe_mapping(trace_index.get("trace_current_health"))
    trace_repair_queue = _safe_list(trace_index.get("trace_repair_queue"))
    payload = {
        "schema_version": "spark.os_trace.summary.v0",
        "generated_at": trace_index.get("generated_at"),
        "builder_event_count": _safe_int(builder_events.get("row_count")),
        "trace_group_count": _safe_int(trace_health.get("trace_group_count") or trace_groups.get("group_count")),
        "missing_trace_ref_count": _safe_int(trace_health.get("missing_trace_ref_count")),
        "high_severity_open_count": _safe_int(trace_health.get("high_severity_open_count")),
        "orphan_parent_event_id_count": _safe_int(trace_health.get("orphan_parent_event_id_count")),
        "authority_verdict_count": _safe_int(authority_verdicts.get("verdict_count")),
        "authority_verdict_counts": _safe_mapping(authority_verdicts.get("verdict_counts")),
        "health_flags": _safe_list(trace_health.get("health_flags")),
        "recent_windows": _safe_list(trace_health.get("recent_windows")),
        "trace_current_health": trace_current_health,
        "top_missing_trace_ref_sources": _safe_list(
            _safe_mapping(trace_health.get("missing_trace_ref_sources")).get("rows")
        )[:10],
        "trace_repair_queue": trace_repair_queue[:10],
        "next_trace_repair": trace_repair_queue[0] if trace_repair_queue else None,
        "cross_system_trace": {
            "spawner_request_id_count": _safe_int(spawner_join.get("request_id_count")),
            "spawner_derived_trace_ref_count": _safe_int(spawner_join.get("derived_trace_ref_count")),
            "spawner_builder_request_overlap_count": _safe_int(
                spawner_request_overlap.get("matched_builder_request_id_count")
            ),
            "spawner_builder_trace_ref_overlap_count": _safe_int(
                spawner_trace_overlap.get("matched_builder_trace_ref_count")
            ),
            "telegram_final_answer_trace_join_status": telegram_join.get("status") or "unknown",
        },
        "trace_index": trace_index,
        "redaction": trace_index.get("redaction"),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    cross_system = payload["cross_system_trace"]
    print("Spark OS trace")
    print(f"- Builder events: {payload['builder_event_count']}")
    print(f"- trace groups: {payload['trace_group_count']}")
    print(f"- missing trace refs: {payload['missing_trace_ref_count']}")
    current_health = _safe_mapping(payload.get("trace_current_health"))
    if current_health:
        print(
            "- current trace health: "
            f"{current_health.get('status') or 'unknown'} "
            f"({current_health.get('window') or 'unknown'} "
            f"{_safe_int(current_health.get('missing_trace_ref_count'))}/"
            f"{_safe_int(current_health.get('row_count'))} missing)"
        )
    print(f"- open high-severity events: {payload['high_severity_open_count']}")
    print(f"- authority verdicts: {payload['authority_verdict_count']}")
    print(
        "- Spawner request overlaps: "
        f"{cross_system['spawner_builder_request_overlap_count']}/{cross_system['spawner_request_id_count']}"
    )
    print(f"- Telegram final-answer join: {cross_system['telegram_final_answer_trace_join_status']}")
    next_repair = _safe_mapping(payload.get("next_trace_repair"))
    if next_repair:
        print(
            "- next repair: "
            f"{next_repair.get('owner_repo')} / {next_repair.get('event_producer_family')} "
            f"needs {next_repair.get('missing_field')} "
            f"({next_repair.get('temporal_scope') or 'current_or_unknown'})"
        )
    print("Redaction: aggregate trace metadata only; raw event bodies and message text are omitted.")
    return 0


def cmd_os_memory(args: argparse.Namespace) -> int:
    desktop = Path(args.desktop).expanduser()
    spark_home = Path(args.spark_home).expanduser()
    registry_path = Path(args.registry).expanduser()
    compiled = compile_system_map(desktop=desktop, spark_home=spark_home, registry_path=registry_path)
    memory_index = _safe_mapping(compiled.get("memory_movement_index") if isinstance(compiled, dict) else {})
    safe_status = _safe_mapping(memory_index.get("safe_status_export"))
    status = _safe_mapping(safe_status.get("status"))
    kb_artifacts = _safe_mapping(memory_index.get("memory_kb_artifacts"))
    current_state = _safe_mapping(_safe_mapping(kb_artifacts.get("lane_counts")).get("current_state"))
    memory_review_queue = _safe_mapping(memory_index.get("memory_review_queue"))
    memory_review_items = _safe_list(memory_review_queue.get("items"))
    payload = {
        "schema_version": "spark.os_memory.summary.v0",
        "generated_at": memory_index.get("generated_at"),
        "status": status.get("status") or "unknown",
        "authority": status.get("authority") or memory_index.get("authority"),
        "row_count": _safe_int(status.get("row_count")),
        "movement_counts": _safe_mapping(status.get("movement_counts")),
        "authority_counts": _safe_mapping(status.get("authority_counts")),
        "source_family_counts": _safe_mapping(status.get("source_family_counts")),
        "record_counts": _safe_mapping(status.get("record_counts")),
        "kb_file_count": _safe_int(kb_artifacts.get("file_count")),
        "current_state_file_count": _safe_int(current_state.get("file_count")),
        "memory_review_queue": memory_review_queue,
        "next_memory_review": memory_review_items[0] if memory_review_items else None,
        "memory_movement_index": memory_index,
        "redaction": memory_index.get("redaction"),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("Spark OS memory movement")
    print(f"- status: {payload['status']}")
    print(f"- rows: {payload['row_count']}")
    print(f"- movement: {payload['movement_counts']}")
    print(f"- authority: {payload['authority_counts']}")
    print(f"- records: {payload['record_counts']}")
    print(f"- KB files: {payload['kb_file_count']}")
    next_review = _safe_mapping(payload.get("next_memory_review"))
    if next_review:
        operator_paths = _safe_mapping(next_review.get("operator_paths"))
        print(
            "- next review: "
            f"{next_review.get('owner_repo')} / {next_review.get('category')} "
            f"({next_review.get('reason_code')})"
        )
        if operator_paths:
            print(f"- provenance path: {operator_paths.get('provenance_drilldown')}")
            print(f"- stale/current gate: {operator_paths.get('stale_current_adjudication')}")
            print(f"- purge path: {operator_paths.get('purge_or_decay_path')}")
    print("Redaction: aggregate memory metadata only; raw memory text and row bodies are omitted.")
    return 0


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
        profile_parts = []
        for item in profiles:
            if not isinstance(item, dict):
                continue
            details = []
            if item.get("relay_port"):
                details.append(f":{item.get('relay_port')}")
            if item.get("primary"):
                details.append("primary")
            if item.get("autostart") is False:
                details.append("manual")
            suffix = f"({', '.join(details)})" if details else ""
            profile_parts.append(f"{item.get('profile')}={'running' if item.get('running') else 'stopped'}{suffix}")
        profile_summary = ", ".join(profile_parts)
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


def cmd_live(args: argparse.Namespace) -> int:
    command = getattr(args, "live_command", "status")
    if command in {"start", "run"}:
        args.target = live_runtime_target()
        args.profile = DEFAULT_TELEGRAM_PROFILE
        args.allow_boot_warnings = False
        start_code = cmd_start(args)
        if command == "run":
            print("")
            print("Spark Live is running. Press Ctrl+C to stop watching logs; services keep running.")
            print("To turn Spark off, run: spark live stop")
            print("")
            follow_live_logs(lines=getattr(args, "lines", 80))
        return start_code
    if command == "stop":
        args.target = live_runtime_target()
        args.profile = DEFAULT_TELEGRAM_PROFILE
        args.cascade = True
        return cmd_stop(args)
    if command == "restart":
        args.target = live_runtime_target()
        args.profile = DEFAULT_TELEGRAM_PROFILE
        args.cascade = True
        args.allow_boot_warnings = False
        return cmd_restart(args)
    if command == "logs":
        targets = live_log_targets()
        for index, (label, path) in enumerate(targets):
            if index:
                print("")
            print(f"== {label} ==")
            if path.exists():
                for line in tail_log_lines(path, getattr(args, "lines", 80)):
                    write_console_text(line if line.endswith("\n") else line + "\n")
            else:
                print(f"No logs yet at {path}")
        if getattr(args, "follow", False):
            follow_live_logs(lines=0)
        return 0
    if command == "verify":
        payload = collect_hosted_security_payload(deep=not bool(getattr(args, "quick", False)))
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print_hosted_security_payload(payload)
        return 0 if payload["ok"] else 1
    if command == "status":
        return cmd_live_status(args)
    raise SystemExit(f"Unknown live command: {command}")


def telegram_ingress_is_external(setup_state: dict[str, Any] | None = None) -> bool:
    setup = setup_state if isinstance(setup_state, dict) else load_json(CONFIG_PATH, {})
    return isinstance(setup, dict) and setup.get("telegram_ingress_mode") == "external"


def live_runtime_target() -> str:
    return "spawner-ui" if telegram_ingress_is_external() else "telegram-starter"


def live_log_targets() -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = [("spawner-ui", module_log_path("spawner-ui"))]
    setup_state = load_json(CONFIG_PATH, {})
    if telegram_ingress_is_external(setup_state):
        return targets
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    if isinstance(profiles, dict) and profiles:
        for profile in sorted(profiles):
            normalized = normalize_telegram_profile(str(profile))
            targets.append((f"spark-telegram-bot:{normalized}", module_log_path("spark-telegram-bot", normalized)))
    else:
        targets.append(("spark-telegram-bot", module_log_path("spark-telegram-bot")))
    return targets


def follow_live_logs(*, lines: int = 80) -> None:
    targets = live_log_targets()
    positions: dict[Path, int] = {}
    for label, path in targets:
        print(f"== {label} ==")
        if not path.exists():
            print(f"No logs yet at {path}")
            positions[path] = 0
            continue
        initial = initial_follow_log_lines(path, lines)
        for line in initial:
            write_console_text(f"[{label}] {line if line.endswith(chr(10)) else line + chr(10)}")
        positions[path] = path.stat().st_size
    try:
        while True:
            for label, path in targets:
                if not path.exists():
                    continue
                position = positions.get(path, 0)
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(position)
                    for line in handle:
                        write_console_text(f"[{label}] {line if line.endswith(chr(10)) else line + chr(10)}")
                    positions[path] = handle.tell()
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped watching Spark Live logs. Services are still running.")


def initial_follow_log_lines(path: Path, line_count: int) -> list[str]:
    if line_count == 0:
        return []
    return tail_log_lines(path, line_count)


def cmd_live_status(args: argparse.Namespace) -> int:
    payload = collect_status_payload()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    print("Spark Live")
    print("One surface for Telegram, Mission Control, memory, and provider routing.")
    print("")
    if payload.get("ok"):
        print("[OK] Spark Live is ready.")
    else:
        print("[FIX] Spark Live needs attention.")
    llm_state = payload.get("llm")
    if isinstance(llm_state, dict):
        roles = llm_state.get("roles")
        if isinstance(roles, dict):
            role_summary = ", ".join(
                f"{role}={roles.get(role, {}).get('provider', llm_state.get('provider', 'not_configured'))}"
                for role in LLM_ROLES
            )
            print(f"LLM roles: {role_summary}")
    profiles = payload.get("telegram_profiles")
    if isinstance(profiles, list) and profiles:
        running = [item for item in profiles if isinstance(item, dict) and item.get("running")]
        stopped = [item for item in profiles if isinstance(item, dict) and not item.get("running")]
        print(f"Telegram profiles: {len(running)} running, {len(stopped)} stopped")
    modules = payload.get("modules") if isinstance(payload.get("modules"), list) else []
    for name in ["spawner-ui", "spark-telegram-bot", "spark-intelligence-builder", "domain-chip-memory", "spark-researcher", "spark-character"]:
        module = next((item for item in modules if isinstance(item, dict) and item.get("name") == name), None)
        if not module:
            continue
        healthy = module.get("healthy")
        marker = "[OK]" if healthy else "[SKIP]" if healthy is None else "[FIX]"
        print(f"{marker} {name}: {module.get('detail')}")
    if payload.get("repair_hints"):
        print("")
        print("Fix next:")
        for hint in payload.get("repair_hints", []):
            print(f"  - {hint}")
        print("  - For deeper help: spark doctor llm \"Spark Live is not ready\" --save-report")
    print("")
    print("Useful:")
    print("  spark live start")
    print("  spark live restart")
    print("  spark live logs")
    return 0 if payload.get("ok") else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    if getattr(args, "doctor_command", None) == "llm":
        return cmd_doctor_llm(args)
    if getattr(args, "doctor_command", None) == "specialization-loop":
        payload = collect_specialization_loop_payload(proof=bool(getattr(args, "proof", False)))
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print_plain_specialization_loop_doctor(payload)
        return 0 if payload.get("ok") else 1
    payload = collect_status_payload()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_plain_doctor(payload)
    return 0 if payload.get("ok") else 1


def _doctor_module_summary(modules: list[Any], name: str, label: str) -> str:
    module = next((item for item in modules if isinstance(item, dict) and item.get("name") == name), None)
    if not module:
        return f"- {label}: not installed"
    healthy = module.get("healthy")
    state = "ready" if healthy else "not checked" if healthy is None else "needs attention"
    detail = str(module.get("detail") or "").strip()
    if detail:
        return f"- {label}: {state} - {detail}"
    return f"- {label}: {state}"


def print_plain_doctor(payload: dict[str, Any]) -> None:
    print("Spark doctor")
    print("Spark is ready." if payload.get("ok") else "Spark needs attention.")
    print("")
    modules = payload.get("modules") if isinstance(payload.get("modules"), list) else []
    llm_state = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
    provider = llm_state.get("provider") or "not configured"
    if provider == "not_configured":
        provider = "not configured"
    model = llm_state.get("model") or "default"
    print("Core")
    print(_doctor_module_summary(modules, "spark-telegram-bot", "Telegram"))
    print(f"- LLM: {provider} ({model})")
    print(_doctor_module_summary(modules, "spark-intelligence-builder", "Builder"))
    print(_doctor_module_summary(modules, "domain-chip-memory", "Memory"))
    print(_doctor_module_summary(modules, "spawner-ui", "Spawner"))
    print("")
    profiles = payload.get("telegram_profiles")
    if isinstance(profiles, list) and profiles:
        running = sum(1 for item in profiles if isinstance(item, dict) and item.get("running"))
        stopped = sum(1 for item in profiles if isinstance(item, dict) and not item.get("running"))
        print("Runtime")
        print(f"- Telegram profiles: {running} running, {stopped} stopped")
        print("")
    hints = payload.get("repair_hints") if isinstance(payload.get("repair_hints"), list) else []
    if hints:
        print("Fix next")
        for hint in hints[:5]:
            print(f"- {hint}")
        if len(hints) > 5:
            print(f"- {len(hints) - 5} more repair hint(s); run `spark status --json` for details.")
        print("")
    print("Useful")
    print("- spark live status")
    print("- spark providers status")
    print("- spark verify --onboarding")


def print_plain_specialization_loop_doctor(payload: dict[str, Any]) -> None:
    print("Spark specialization loop doctor")
    print("Specialization loops are discoverable." if payload.get("ok") else "Specialization loops need attention.")
    print("")
    print("Loop surfaces")
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    for check in checks:
        if not isinstance(check, dict):
            continue
        label = str(check.get("name") or "check").replace("_", " ")
        state = "ready" if check.get("ok") else "missing"
        detail = str(check.get("detail") or "").strip()
        print(f"- {label}: {state}" + (f" - {detail}" if detail else ""))
    missing = [check for check in checks if isinstance(check, dict) and not check.get("ok")]
    if missing:
        print("")
        print("Fix next")
        for check in missing:
            repair = str(check.get("repair") or "").strip()
            if repair:
                print(f"- {repair}")
    proofs = payload.get("status_proofs")
    if isinstance(proofs, list) and proofs:
        print("")
        print("Status proof")
        for proof in proofs:
            if not isinstance(proof, dict):
                continue
            state = "ready" if proof.get("ok") else "needs attention"
            detail = str(proof.get("detail") or "").strip()
            print(f"- {proof.get('path_key', 'path')}: {state}" + (f" - {detail}" if detail else ""))
    print("")
    print("Proof commands")
    for command in payload.get("next_commands", []):
        print(f"- {command}")
    safe_next_moves = payload.get("safe_next_moves")
    if isinstance(safe_next_moves, list) and safe_next_moves:
        print("")
        print("Safe next moves")
        for move in safe_next_moves:
            print(f"- {move}")
    print("")
    print("Boundary")
    boundary = str(
        payload.get("boundary")
        or "This doctor only inspects discoverability. It does not start runs, publish, delete, or repair automatically."
    )
    print(f"- {boundary}")


def collect_support_bundle_payload(*, include_logs: bool = False, log_lines: int = 120) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "created_at": timestamp_now(),
        "spark_home": public_local_path_ref(SPARK_HOME),
        "status": collect_status_payload(),
        "providers": provider_status_payload(),
        "verify": collect_verify_payload(deep=False),
        "security": collect_security_audit_payload(deep=False),
        "logs_included": bool(include_logs),
        "redaction": {
            "secrets_redacted": True,
            "home_paths_redacted": True,
            "share_policy": "local_review_first",
        },
    }
    if include_logs:
        logs: dict[str, list[str]] = {}
        status_payload = payload.get("status")
        modules = status_payload.get("modules") if isinstance(status_payload, dict) else []
        if isinstance(modules, list):
            for module in modules:
                if not isinstance(module, dict) or not module.get("name"):
                    continue
                name = str(module["name"])
                lines = tail_log_lines(module_log_path(name), log_lines)
                if lines:
                    logs[name] = [redact_shareable_text(line.rstrip()) for line in lines]
        payload["logs"] = logs
    redacted_payload = redact_shareable_payload(redact_for_llm(payload))
    redacted_payload["sharing_manifest"] = build_share_safety_manifest(
        redacted_payload,
        include_logs=include_logs,
        purpose="support_bundle",
    )
    return redacted_payload


def write_support_bundle(payload: dict[str, Any]) -> Path:
    output_dir = SPARK_HOME / "support"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"spark-support-{stamp}.zip"
    readme = (
        "Spark Support Bundle\n\n"
        "This archive is local-first and not uploaded automatically.\n"
        "Review it before sharing. Secrets, token-looking values, and local home paths are redacted best-effort.\n"
        "If sharing upstream, include only the smallest relevant excerpt and never include raw logs without review.\n"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", readme)
        archive.writestr("support.json", json.dumps(payload, indent=2, sort_keys=True))
    return path


def cmd_support(args: argparse.Namespace) -> int:
    if args.support_command != "bundle":
        raise SystemExit(f"Unknown support command: {args.support_command}")
    payload = collect_support_bundle_payload(include_logs=args.include_logs, log_lines=args.log_lines)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    path = write_support_bundle(payload)
    print("Spark support bundle")
    print("")
    print(f"[OK] Wrote local redacted support bundle: {path}")
    print("")
    print("Review before sharing:")
    print("  - No API keys, bot tokens, Authorization headers, cookies, or private logs.")
    print("  - Logs are excluded unless you used --include-logs.")
    print("  - A sharing_manifest is included in support.json; fix any remaining_risk_findings before sharing.")
    print("  - Nothing was uploaded.")
    print("")
    print("Useful next:")
    print(f"  spark doctor llm \"Describe the Spark issue\" --save-report")
    return 0


REVOKE_ALL_ROTATABLE_ENV_KEYS = {
    "EVENTS_API_KEY",
    "MCP_API_KEY",
    "SPARK_BRIDGE_API_KEY",
    "SPARK_UI_API_KEY",
    "TELEGRAM_RELAY_SECRET",
}
REVOKE_ALL_SPAWNER_REQUIRED_KEYS = {
    "EVENTS_API_KEY",
    "MCP_API_KEY",
    "SPARK_BRIDGE_API_KEY",
    "SPARK_UI_API_KEY",
}
REVOKE_ALL_NON_TERMINAL_PROVIDER_STATUSES = {"idle", "queued", "running"}
REVOKE_ALL_TERMINAL_MISSION_EVENTS = {"mission_completed", "mission_failed", "mission_cancelled"}
REVOKE_ALL_PAUSABLE_MISSION_EVENTS = {
    "mission_created",
    "mission_started",
    "mission_resumed",
    "task_started",
    "task_progress",
    "progress",
    "task_completed",
    "task_failed",
    "task_cancelled",
    "dispatch_started",
    "provider_feedback",
    "log",
}


def revoke_all_error_detail(error: BaseException) -> str:
    return redact_shareable_text(redact_sensitive_text(f"{error.__class__.__name__}: {error}"))


def revoke_all_token_value(key: str) -> str:
    prefix = key.lower().replace("_", "-")
    return f"spark-{prefix}-{py_secrets.token_urlsafe(32)}"


def capture_revoke_all_step(label: str, callback: Callable[[], int], *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "label": label, "planned": True, "exit_code": None, "output": ""}
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            exit_code = int(callback())
    except Exception as error:
        return {
            "ok": False,
            "label": label,
            "planned": False,
            "exit_code": None,
            "output": redact_shareable_text(output.getvalue().strip()),
            "error": revoke_all_error_detail(error),
        }
    return {
        "ok": True,
        "label": label,
        "planned": False,
        "exit_code": exit_code,
        "output": redact_shareable_text(output.getvalue().strip()),
    }


def generated_env_files_for_revoke_all() -> list[Path]:
    if not MODULE_CONFIG_DIR.exists():
        return []
    try:
        return sorted(path for path in MODULE_CONFIG_DIR.glob("*.env") if path.is_file())
    except OSError:
        return []


def module_name_from_generated_env_path(path: Path) -> str | None:
    stem = path.stem
    if "." in stem:
        return None
    return stem


def resolve_installed_modules_best_effort() -> dict[str, Module]:
    try:
        return resolve_installed_modules()
    except Exception:
        return {}


def sync_generated_env_to_module_output(
    generated_path: Path,
    values: dict[str, str],
    installed_modules: dict[str, Module],
) -> str | None:
    module_name = module_name_from_generated_env_path(generated_path)
    if not module_name:
        return None
    module = installed_modules.get(module_name)
    if module is None:
        return None
    env_path = module_env_path(module)
    if env_path is None:
        return None
    update_env_file(env_path, values)
    return str(env_path)


def rotate_revoke_all_env_keys(*, dry_run: bool = False) -> dict[str, Any]:
    rotated_files: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    generated_values: dict[str, str] = {}
    installed_modules = resolve_installed_modules_best_effort()

    for path in generated_env_files_for_revoke_all():
        values = read_generated_env(path)
        keys = {key for key in REVOKE_ALL_ROTATABLE_ENV_KEYS if key in values}
        if path.name == "spawner-ui.env":
            keys.update(REVOKE_ALL_SPAWNER_REQUIRED_KEYS)
        if not keys:
            continue
        try:
            next_values = dict(values)
            for key in sorted(keys):
                generated_values.setdefault(key, revoke_all_token_value(key))
                next_values[key] = generated_values[key]
            synced_env_path = None
            if not dry_run:
                write_generated_env(path, next_values)
                synced_env_path = sync_generated_env_to_module_output(path, next_values, installed_modules)
            rotated_files.append(
                {
                    "path": str(path),
                    "keys": sorted(keys),
                    "synced_module_env_path": synced_env_path,
                    "planned": dry_run,
                }
            )
        except Exception as error:
            failures.append({"path": str(path), "error": revoke_all_error_detail(error)})

    return {
        "ok": not failures,
        "rotated_files": rotated_files,
        "rotated_key_names": sorted(generated_values),
        "failures": failures,
        "planned": dry_run,
    }


def disable_revoke_all_custom_mcp(*, dry_run: bool = False) -> dict[str, Any]:
    spawner_env_path = MODULE_CONFIG_DIR / "spawner-ui.env"
    if not spawner_env_path.exists():
        return {
            "ok": True,
            "disabled": False,
            "planned": dry_run,
            "detail": "No generated spawner-ui env file was present.",
            "files": [],
        }
    try:
        values = read_generated_env(spawner_env_path)
        values["MCP_ALLOW_CUSTOM_CONFIG"] = "0"
        synced_env_path = None
        if not dry_run:
            write_generated_env(spawner_env_path, values)
            synced_env_path = sync_generated_env_to_module_output(
                spawner_env_path,
                values,
                resolve_installed_modules_best_effort(),
            )
        return {
            "ok": True,
            "disabled": True,
            "planned": dry_run,
            "files": [
                {
                    "path": str(spawner_env_path),
                    "synced_module_env_path": synced_env_path,
                    "key": "MCP_ALLOW_CUSTOM_CONFIG",
                    "value": "0",
                }
            ],
        }
    except Exception as error:
        return {
            "ok": False,
            "disabled": False,
            "planned": dry_run,
            "files": [{"path": str(spawner_env_path)}],
            "error": revoke_all_error_detail(error),
        }


def telegram_tokens_for_revoke_all(secret_ids: Iterable[str]) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    seen: set[str] = set()
    for secret_id in sorted(secret_ids):
        if not is_telegram_bot_token_secret(secret_id):
            continue
        value = fetch_secret(secret_id)
        if not value:
            continue
        token = extract_telegram_bot_token(value)
        if token in seen:
            continue
        seen.add(token)
        tokens.append({"secret_id": secret_id, "token": token})
    return tokens


def clear_telegram_webhook_state(tokens: list[dict[str, str]], *, dry_run: bool = False) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for item in tokens:
        secret_id = item["secret_id"]
        if dry_run:
            results.append({"secret_id": secret_id, "ok": True, "planned": True})
            continue
        token = urllib.parse.quote(item["token"], safe=":")
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
        request = urllib.request.Request(url, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=TELEGRAM_BOT_TOKEN_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            ok = bool(payload.get("ok"))
            entry: dict[str, Any] = {"secret_id": secret_id, "ok": ok, "planned": False}
            if not ok:
                entry["description"] = redact_sensitive_text(str(payload.get("description") or "Telegram rejected deleteWebhook"))
                failures.append({"secret_id": secret_id, "error": str(entry["description"])})
            results.append(entry)
        except Exception as error:
            detail = revoke_all_error_detail(error)
            failures.append({"secret_id": secret_id, "error": detail})
            results.append({"secret_id": secret_id, "ok": False, "planned": False, "error": detail})
    return {
        "ok": not failures,
        "requested": len(tokens),
        "results": results,
        "failures": failures,
        "planned": dry_run,
    }


def delete_revoke_all_secrets(secret_ids: Iterable[str], *, dry_run: bool = False) -> dict[str, Any]:
    deleted: list[str] = []
    failures: list[dict[str, str]] = []
    for secret_id in sorted(secret_ids):
        if dry_run:
            deleted.append(secret_id)
            continue
        try:
            delete_secret(secret_id)
            deleted.append(secret_id)
        except Exception as error:
            failures.append({"secret_id": secret_id, "error": revoke_all_error_detail(error)})
    external_markers = ("github", "scanner", "oauth", "access_token", "refresh_token")
    external_ids = [secret_id for secret_id in deleted if any(marker in secret_id.lower() for marker in external_markers)]
    return {
        "ok": not failures,
        "deleted_secret_ids": deleted,
        "deleted_count": len(deleted),
        "external_token_secret_ids": external_ids,
        "failures": failures,
        "planned": dry_run,
        "remote_revoke_note": (
            "Local Spark copies were removed. Revoke provider-side OAuth/GitHub/Scanner tokens in the provider console when applicable."
            if external_ids
            else ""
        ),
    }


def spawner_state_dir_for_revoke_all() -> Path:
    spawner_env = read_generated_env(MODULE_CONFIG_DIR / "spawner-ui.env")
    raw = spawner_env.get("SPAWNER_STATE_DIR") or str(STATE_DIR / "spawner-ui")
    return Path(raw).expanduser()


def load_json_best_effort(path: Path, default: Any) -> Any:
    try:
        return load_json(path, default)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def latest_mission_events(recent: list[Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in recent:
        if not isinstance(entry, dict):
            continue
        mission_id = entry.get("missionId")
        event_type = entry.get("eventType")
        if not isinstance(mission_id, str) or not mission_id.strip():
            continue
        if not isinstance(event_type, str) or not event_type.strip():
            continue
        latest.setdefault(mission_id.strip(), entry)
    return latest


def pause_entry_for_revoke_all(entry: dict[str, Any], timestamp: str) -> dict[str, Any]:
    next_entry = dict(entry)
    next_entry.update(
        {
            "eventType": "mission_paused",
            "summary": "Mission paused by spark security revoke-all.",
            "timestamp": timestamp,
            "source": "spark-cli-security-revoke-all",
        }
    )
    next_entry["taskId"] = None
    next_entry["taskName"] = None
    next_entry["progress"] = None
    return next_entry


def pause_revoke_all_missions(*, dry_run: bool = False, timestamp: str | None = None) -> dict[str, Any]:
    created_at = timestamp or timestamp_now()
    state_dir = spawner_state_dir_for_revoke_all()
    active_path = state_dir / "active-mission.json"
    mission_control_path = state_dir / "mission-control.json"
    provider_results_path = state_dir / "mission-provider-results.json"
    pause_marker_path = state_dir / "security-revoke-all.json"
    paused_mission_ids: set[str] = set()
    provider_results_cancelled = 0
    failures: list[dict[str, str]] = []

    mission_control = load_json_best_effort(mission_control_path, {})
    recent = mission_control.get("recent") if isinstance(mission_control, dict) else None
    if isinstance(recent, list):
        latest = latest_mission_events(recent)
        pause_entries: list[dict[str, Any]] = []
        for mission_id, entry in latest.items():
            event_type = str(entry.get("eventType") or "")
            if event_type in REVOKE_ALL_TERMINAL_MISSION_EVENTS or event_type == "mission_paused":
                continue
            if event_type in REVOKE_ALL_PAUSABLE_MISSION_EVENTS:
                paused_mission_ids.add(mission_id)
                pause_entries.append(pause_entry_for_revoke_all(entry, created_at))
        if pause_entries and not dry_run:
            try:
                mission_control["recent"] = [*pause_entries, *recent]
                mission_control["totalRelayed"] = int(mission_control.get("totalRelayed") or 0) + len(pause_entries)
                per_mission = mission_control.get("perMission")
                if not isinstance(per_mission, dict):
                    per_mission = {}
                for entry in pause_entries:
                    mission_id = str(entry.get("missionId") or "")
                    per_mission[mission_id] = int(per_mission.get(mission_id) or 0) + 1
                mission_control["perMission"] = per_mission
                save_json(mission_control_path, mission_control)
            except Exception as error:
                failures.append({"path": str(mission_control_path), "error": revoke_all_error_detail(error)})

    active = load_json_best_effort(active_path, {})
    if isinstance(active, dict) and active:
        mission_id = str(active.get("missionId") or active.get("id") or "").strip()
        status = str(active.get("status") or "").strip().lower()
        if mission_id and status not in {"completed", "failed", "cancelled", "paused"}:
            paused_mission_ids.add(mission_id)
            if not dry_run:
                try:
                    active["status"] = "paused"
                    active["lastUpdated"] = created_at
                    active["note"] = "Paused by spark security revoke-all"
                    active["securityRevokeAll"] = {"pausedAt": created_at, "source": "spark-cli"}
                    save_json(active_path, active)
                except Exception as error:
                    failures.append({"path": str(active_path), "error": revoke_all_error_detail(error)})

    provider_results = load_json_best_effort(provider_results_path, {})
    missions = provider_results.get("missions") if isinstance(provider_results, dict) else None
    if isinstance(missions, dict):
        changed = False
        for mission_id, results in missions.items():
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                status = str(result.get("status") or "").lower()
                if status in REVOKE_ALL_NON_TERMINAL_PROVIDER_STATUSES:
                    paused_mission_ids.add(str(mission_id))
                    provider_results_cancelled += 1
                    changed = True
                    if not dry_run:
                        result["status"] = "cancelled"
                        result["error"] = "Security revoke-all stopped runtime while pausing mission."
                        result.setdefault("completedAt", created_at)
        if changed and not dry_run:
            try:
                save_json(provider_results_path, provider_results)
            except Exception as error:
                failures.append({"path": str(provider_results_path), "error": revoke_all_error_detail(error)})

    marker = {
        "version": 1,
        "created_at": created_at,
        "pause_new_missions": True,
        "custom_mcp_disabled": True,
        "paused_mission_ids": sorted(paused_mission_ids),
        "reason": "spark security revoke-all",
    }
    if not dry_run:
        try:
            save_json(pause_marker_path, marker)
        except Exception as error:
            failures.append({"path": str(pause_marker_path), "error": revoke_all_error_detail(error)})

    return {
        "ok": not failures,
        "state_dir": str(state_dir),
        "active_mission_path": str(active_path),
        "mission_control_path": str(mission_control_path),
        "provider_results_path": str(provider_results_path),
        "pause_marker_path": str(pause_marker_path),
        "paused_mission_ids": sorted(paused_mission_ids),
        "provider_results_cancelled": provider_results_cancelled,
        "planned": dry_run,
        "failures": failures,
    }


def execute_security_revoke_all(*, dry_run: bool = False, include_logs: bool = False) -> dict[str, Any]:
    ensure_state_dirs()
    created_at = timestamp_now()
    payload: dict[str, Any] = {
        "ok": True,
        "summary": "Spark revoke-all security response",
        "created_at": created_at,
        "dry_run": dry_run,
        "actions": {},
        "support_bundle_path": None,
        "manual_remote_revocations": [
            "Telegram bot tokens were removed locally; rotate or revoke the bot with BotFather if a token leaked.",
            "OAuth/GitHub/Scanner tokens were removed locally when present; revoke them in their provider consoles when applicable.",
            "Cloud/provider API keys outside Spark's local secret store still need provider-side rotation.",
        ],
    }

    with pid_file_lock():
        tracked_processes_before = sorted(load_pids().keys())
    payload["actions"]["autostart"] = capture_revoke_all_step(
        "Disable Spark login autostart",
        lambda: cmd_autostart_uninstall(argparse.Namespace()),
        dry_run=dry_run,
    )
    payload["actions"]["processes"] = {
        **capture_revoke_all_step(
            "Stop tracked Spark processes",
            lambda: cmd_stop(argparse.Namespace(target=None, profile=None, cascade=True)),
            dry_run=dry_run,
        ),
        "tracked_processes_before": tracked_processes_before,
    }

    secret_ids = sorted(list_stored_secrets())
    telegram_tokens = telegram_tokens_for_revoke_all(secret_ids)
    payload["actions"]["telegram"] = clear_telegram_webhook_state(telegram_tokens, dry_run=dry_run)
    payload["actions"]["secrets"] = delete_revoke_all_secrets(secret_ids, dry_run=dry_run)
    payload["actions"]["local_keys"] = rotate_revoke_all_env_keys(dry_run=dry_run)
    payload["actions"]["custom_mcp"] = disable_revoke_all_custom_mcp(dry_run=dry_run)
    payload["actions"]["missions"] = pause_revoke_all_missions(dry_run=dry_run, timestamp=created_at)

    if not dry_run:
        try:
            support_payload = collect_support_bundle_payload(include_logs=include_logs, log_lines=120)
            support_payload["revoke_all"] = redact_shareable_payload(
                redact_for_llm({key: value for key, value in payload.items() if key != "support_bundle_path"})
            )
            support_path = write_support_bundle(support_payload)
            payload["support_bundle_path"] = str(support_path)
            payload["actions"]["support_bundle"] = {"ok": True, "path": str(support_path), "include_logs": include_logs}
        except Exception as error:
            payload["actions"]["support_bundle"] = {"ok": False, "error": revoke_all_error_detail(error)}
    else:
        payload["actions"]["support_bundle"] = {"ok": True, "planned": True, "path": None}

    critical_actions = ("secrets", "local_keys", "custom_mcp", "missions", "support_bundle")
    payload["ok"] = all(bool(payload["actions"].get(name, {}).get("ok")) for name in critical_actions)
    return payload


def print_security_revoke_all_payload(payload: dict[str, Any]) -> None:
    dry_run = bool(payload.get("dry_run"))
    actions = payload.get("actions") if isinstance(payload.get("actions"), dict) else {}
    print("Spark security revoke-all")
    print("")
    if dry_run:
        print("Dry run: no local state was changed.")
        print("")
    for key, label in [
        ("autostart", "login autostart"),
        ("processes", "tracked processes"),
        ("telegram", "Telegram webhook/session state"),
        ("secrets", "local Spark secrets"),
        ("local_keys", "local bridge/API keys"),
        ("custom_mcp", "custom MCP config"),
        ("missions", "active missions"),
        ("support_bundle", "support bundle"),
    ]:
        action = actions.get(key) if isinstance(actions, dict) else None
        if not isinstance(action, dict):
            continue
        marker = "[OK]" if action.get("ok") else "[CHECK]"
        if key == "secrets":
            detail = f"{action.get('deleted_count', 0)} secret id(s) {'would be removed' if dry_run else 'removed'}"
        elif key == "local_keys":
            detail = f"{len(action.get('rotated_files') or [])} generated env file(s) {'would be rotated' if dry_run else 'rotated'}"
        elif key == "missions":
            detail = f"{len(action.get('paused_mission_ids') or [])} mission(s) {'would be paused' if dry_run else 'paused'}"
        elif key == "support_bundle":
            detail = str(action.get("path") or ("planned" if dry_run else action.get("error") or "not written"))
        else:
            detail = "planned" if action.get("planned") else str(action.get("error") or "done")
        print(f"{marker} {label}: {detail}")
    if payload.get("support_bundle_path"):
        print("")
        print(f"Redacted support bundle: {payload['support_bundle_path']}")
    print("")
    print("Remote cleanup still to do where applicable:")
    for item in payload.get("manual_remote_revocations") or []:
        print(f"  - {item}")


SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"\b\d{7,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{16,}|sk-proj-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|gho_[A-Za-z0-9_]{16,}|ghp_[A-Za-z0-9_]{16,}|glpat-[A-Za-z0-9_\-]{16,}|xoxb-[A-Za-z0-9_\-]{16,}|xoxp-[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)(\s*[:=]\s*)([^\s,;\"']+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{16,})"),
]
SECRET_SURFACE_ENV_PATTERN = re.compile(
    r"(?im)^\s*([A-Z][A-Z0-9_]*(?:API_KEY|BOT_TOKEN|TOKEN|SECRET|PASSWORD|AUTHORIZATION))\s*=\s*([^\r\n#]+)"
)
SECRET_SURFACE_ALLOWED_CONFIG_SECRET_NAMES = {"TELEGRAM_RELAY_SECRET"}
SECRET_SURFACE_TOKEN_PATTERNS = [
    re.compile(r"\b(?:bot)?\d{7,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{16,}|sk-proj-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|gho_[A-Za-z0-9_]{16,}|ghp_[A-Za-z0-9_]{16,}|glpat-[A-Za-z0-9_\-]{16,}|xoxb-[A-Za-z0-9_\-]{16,}|xoxp-[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{16,})\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
]
SECRET_SURFACE_MAX_FILE_BYTES = 2 * 1024 * 1024


def secret_surface_value_is_redacted(value: str) -> bool:
    normalized = value.strip().strip("\"'")
    if not normalized:
        return True
    return bool(re.fullmatch(r"\[?redacted\]?|<[^>]*redacted[^>]*>", normalized, flags=re.IGNORECASE))


def secret_surface_file_findings(path: Path) -> dict[str, int]:
    try:
        if not path.is_file() or path.stat().st_size > SECRET_SURFACE_MAX_FILE_BYTES:
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    env_hits = 0
    for match in SECRET_SURFACE_ENV_PATTERN.finditer(text):
        secret_name = match.group(1)
        if path.suffix == ".env" and secret_name in SECRET_SURFACE_ALLOWED_CONFIG_SECRET_NAMES:
            continue
        if not secret_surface_value_is_redacted(match.group(2)):
            env_hits += 1

    token_hits = 0
    scrubbed_env_values = SECRET_SURFACE_ENV_PATTERN.sub(
        lambda match: f"{match.group(1)}="
        + ("<redacted>" if secret_surface_value_is_redacted(match.group(2)) else "<secret>"),
        text,
    )
    for pattern in SECRET_SURFACE_TOKEN_PATTERNS:
        for match in pattern.finditer(scrubbed_env_values):
            if "redacted" not in match.group(0).lower():
                token_hits += 1

    findings: dict[str, int] = {}
    if env_hits:
        findings["env_secret_assignments"] = env_hits
    if token_hits:
        findings["token_like_values"] = token_hits
    return findings


def collect_secret_surface_payload() -> dict[str, Any]:
    roots = [MODULE_CONFIG_DIR, LOG_DIR]
    findings: list[dict[str, Any]] = []
    scanned_files = 0
    for root in roots:
        if not root.exists():
            continue
        try:
            files = [path for path in root.rglob("*") if path.is_file()]
        except OSError:
            continue
        for path in files:
            scanned_files += 1
            counts = secret_surface_file_findings(path)
            if counts:
                findings.append(
                    {
                        "path": redact_shareable_text(str(path)),
                        "counts": counts,
                    }
                )

    return {
        "ok": not findings,
        "scanned_files": scanned_files,
        "findings": findings,
        "detail": (
            f"Generated configs/logs scanned clean ({scanned_files} files)."
            if not findings
            else f"Found plaintext-looking secrets in {len(findings)} generated config/log file(s)."
        ),
        "repair": "spark fix secrets",
    }


def redact_secret_surface_logs() -> dict[str, Any]:
    changed: list[str] = []
    scanned = 0
    if not LOG_DIR.exists():
        return {"changed": changed, "scanned_files": scanned}
    try:
        files = [path for path in LOG_DIR.rglob("*") if path.is_file()]
    except OSError:
        return {"changed": changed, "scanned_files": scanned}
    for path in files:
        scanned += 1
        try:
            if path.stat().st_size > SECRET_SURFACE_MAX_FILE_BYTES:
                continue
            original = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        redacted = redact_sensitive_text(original)
        if redacted != original:
            try:
                path.write_text(redacted, encoding="utf-8")
            except OSError:
                continue
            changed.append(redact_shareable_text(str(path)))
    return {"changed": changed, "scanned_files": scanned}


def security_check(
    name: str,
    ok: bool,
    detail: str,
    repair: str,
    *,
    severity: str = "info",
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "severity": severity if not ok else "info",
        "detail": detail,
        "repair": repair,
    }


def spark_home_boundary_errors(spark_home: Path = SPARK_HOME) -> list[str]:
    errors: list[str] = []
    try:
        resolved = spark_home.expanduser().resolve()
    except OSError:
        resolved = spark_home.expanduser().absolute()

    unsafe: set[Path] = set()
    if resolved.anchor:
        unsafe.add(Path(resolved.anchor))
    unsafe.add(Path.home().expanduser())
    try:
        unsafe = {path.resolve() for path in unsafe}
    except OSError:
        unsafe = {path.absolute() for path in unsafe}

    if resolved in unsafe:
        errors.append(f"SPARK_HOME points at a broad directory: {redact_shareable_text(str(resolved))}.")
    if str(resolved).strip() in {"", ".", os.sep}:
        errors.append("SPARK_HOME is empty or points at the filesystem root.")
    return errors


def spark_home_write_errors(paths: list[Path] | None = None) -> list[str]:
    errors: list[str] = []
    for path in paths or [SPARK_HOME, STATE_DIR, CONFIG_DIR, LOG_DIR]:
        if path.exists() and not os.access(path, os.R_OK | os.W_OK):
            errors.append(f"{redact_shareable_text(str(path))} is not readable/writable by the current user.")
    return errors


def local_secret_file_permission_errors(paths: list[Path] | None = None) -> list[str]:
    if os.name == "nt":
        return []
    errors: list[str] = []
    for path in paths or [SECRETS_FILE_PATH, SECRETS_INDEX_PATH]:
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"Could not inspect {redact_shareable_text(str(path))}: {exc}.")
            continue
        if mode & 0o077:
            errors.append(f"{redact_shareable_text(str(path))} is {oct(mode)}; Spark secrets should be private.")
    return errors


def local_control_surface_errors() -> list[str]:
    errors: list[str] = []
    spawner_env = read_generated_env(MODULE_CONFIG_DIR / "spawner-ui.env")
    spawner_host = (spawner_env.get("SPARK_SPAWNER_HOST") or spawner_env.get("HOST") or "").strip()
    allowed_hosts = [host.strip() for host in (spawner_env.get("SPARK_ALLOWED_HOSTS") or "").split(",") if host.strip()]
    public_bind = spawner_host in {"0.0.0.0", "::"} or bool(allowed_hosts)
    if public_bind:
        errors.extend(hosted_allowed_host_errors(allowed_hosts))
        if not allowed_hosts:
            errors.append("Spawner appears publicly bound but SPARK_ALLOWED_HOSTS is not configured.")
        ui_key = spawner_env.get("SPARK_UI_API_KEY") or os.environ.get("SPARK_UI_API_KEY") or ""
        bridge_key = spawner_env.get("SPARK_BRIDGE_API_KEY") or os.environ.get("SPARK_BRIDGE_API_KEY") or ""
        errors.extend(hosted_api_key_strength_errors(ui_key, bridge_key))
    return errors


def telegram_polling_conflict_errors() -> list[str]:
    errors: list[str] = []
    setup_state = load_json(CONFIG_PATH, {})
    if telegram_ingress_is_external(setup_state if isinstance(setup_state, dict) else {}):
        return []
    profiles = configured_telegram_profiles() or [DEFAULT_TELEGRAM_PROFILE]
    token_profiles: dict[str, list[str]] = {}

    for profile in profiles:
        token = fetch_secret(telegram_profile_secret_id(profile, "bot_token"))
        if token:
            token_profiles.setdefault(token, []).append(profile)
        log_text = "".join(tail_log_lines(module_log_path("spark-telegram-bot", profile), 200))
        if "409: Conflict" in log_text and "getUpdates" in log_text:
            errors.append(
                f"Telegram profile `{profile}` log shows a getUpdates conflict; another process is polling the same bot token."
            )

    legacy_token = fetch_secret("telegram.bot_token")
    primary_profile = primary_telegram_profile(setup_state if isinstance(setup_state, dict) else {})
    primary_token = fetch_secret(telegram_profile_secret_id(primary_profile, "bot_token"))
    if legacy_token and legacy_token != primary_token:
        token_profiles.setdefault(legacy_token, []).append("legacy-default")

    for profile_names in token_profiles.values():
        unique_profiles = sorted(set(profile_names))
        if len(unique_profiles) > 1:
            errors.append(f"Telegram profiles share one bot token: {', '.join(unique_profiles)}.")
    return errors


def pid_registry_errors() -> list[str]:
    errors: list[str] = []
    for key, record in load_pids().items():
        if not isinstance(record, dict):
            errors.append(f"Process registry entry `{key}` is malformed.")
            continue
        try:
            pid = int(record.get("pid", 0))
        except (TypeError, ValueError):
            errors.append(f"Process registry entry `{key}` has an invalid pid.")
            continue
        if pid and not pid_is_running(pid):
            errors.append(f"Process registry entry `{key}` points at a stale pid ({pid}).")
    return errors


def running_as_hosted_context() -> bool:
    return bool(
        os.environ.get("SPARK_LIVE_CONTAINER")
        or os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("SPARK_ALLOWED_HOSTS")
    )


def security_provider_detail(provider_payload: dict[str, Any]) -> str:
    roles = provider_payload.get("roles")
    if not isinstance(roles, dict) or not roles:
        summary = str(provider_payload.get("summary") or "Spark LLM provider roles")
        repair_hints = provider_payload.get("repair_hints")
        if isinstance(repair_hints, list) and repair_hints:
            return f"{summary}: {'; '.join(str(item) for item in repair_hints[:3])}"
        return summary

    parts: list[str] = []
    for role in LLM_ROLES:
        role_payload = roles.get(role)
        if not isinstance(role_payload, dict):
            parts.append(f"{role}=not configured")
            continue
        provider = str(role_payload.get("provider") or "not configured")
        model = str(role_payload.get("model") or "default")
        auth_mode = str(role_payload.get("auth_mode") or "unknown")
        ready = bool(role_payload.get("ready"))
        suffix = "" if ready else " (not ready)"
        parts.append(f"{role}={provider}/{model} via {auth_mode}{suffix}")
    return "; ".join(parts)


def git_short_status(path: Path) -> str:
    result = subprocess.run(
        git_command("-C", str(path), "status", "--porcelain"),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def git_current_head(path: Path) -> str | None:
    result = subprocess.run(
        git_command("-C", str(path), "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip().lower()
    return value if validate_commit_pin(value) else None


def installed_record_registry_commit(record: dict[str, Any]) -> str | None:
    value = str(record.get("registry_commit") or record.get("commit") or "").strip().lower()
    if not value:
        return None
    try:
        return validate_commit_pin(value)
    except SystemExit:
        return None


def module_supply_chain_errors() -> list[str]:
    installed = load_json(REGISTRY_PATH, {})
    registry_modules = load_registry_definition().get("modules", {})
    if not isinstance(installed, dict) or not installed:
        return ["No installed module registry was found; run `spark setup` before launch."]
    if not isinstance(registry_modules, dict):
        registry_modules = {}

    errors: list[str] = []
    modules_root = SPARK_HOME / "modules"
    for name, record in sorted(installed.items()):
        if not isinstance(record, dict):
            errors.append(f"Installed module `{name}` has a malformed registry record.")
            continue
        path = Path(str(record.get("path") or "")).expanduser()
        if not path.exists():
            errors.append(f"Installed module `{name}` path is missing: {redact_shareable_text(str(path))}.")
            continue
        try:
            if not path.resolve().is_relative_to(modules_root.resolve()):
                errors.append(f"Installed module `{name}` lives outside Spark's managed module directory.")
        except AttributeError:  # pragma: no cover - Python <3.9 fallback
            if str(modules_root.resolve()) not in str(path.resolve()):
                errors.append(f"Installed module `{name}` lives outside Spark's managed module directory.")
        except OSError:
            errors.append(f"Could not resolve installed module path for `{name}`.")

        metadata = registry_modules.get(str(name))
        if not isinstance(metadata, dict):
            errors.append(f"Installed module `{name}` is not present in the blessed registry.")
            continue
        if not bool(metadata.get("blessed", False)):
            errors.append(f"Installed module `{name}` is not marked blessed in the registry.")

        pinned = str(metadata.get("commit") or "").strip().lower()
        if not pinned:
            errors.append(f"Blessed module `{name}` does not have a full registry commit pin.")
        elif (path / ".git").exists():
            current = git_current_head(path)
            if current is None:
                errors.append(f"Could not read git HEAD for installed module `{name}`.")
            elif current != pinned:
                errors.append(f"Installed module `{name}` is at {current[:12]}, not pinned {pinned[:12]}.")
            if git_short_status(path):
                errors.append(f"Installed module `{name}` has local git changes.")
        else:
            recorded = installed_record_registry_commit(record)
            if recorded is None:
                errors.append(
                    f"Installed module `{name}` is not a git checkout and has no recorded registry commit provenance."
                )
            elif recorded != pinned:
                errors.append(f"Installed module `{name}` records {recorded[:12]}, not pinned {pinned[:12]}.")
    return errors


def runtime_supply_chain_warnings(modules: Iterable[Module]) -> list[str]:
    """Return warnings for startable installed modules that drift from registry pins."""
    registry_modules = load_registry_definition().get("modules", {})
    if not isinstance(registry_modules, dict):
        registry_modules = {}
    modules_root = SPARK_HOME / "modules"
    try:
        resolved_modules_root = modules_root.resolve()
    except OSError:
        resolved_modules_root = modules_root

    warnings: list[str] = []
    for module in modules:
        if not module.run_command:
            continue
        try:
            resolved_path = module.path.resolve()
            in_managed_home = resolved_path.is_relative_to(resolved_modules_root)
        except AttributeError:  # pragma: no cover - Python <3.9 fallback
            in_managed_home = str(resolved_modules_root) in str(module.path.resolve())
        except OSError:
            warnings.append(f"{module.name}: could not resolve installed runtime path.")
            continue
        if not in_managed_home:
            continue

        metadata = registry_modules.get(module.name)
        if not isinstance(metadata, dict):
            warnings.append(f"{module.name}: not present in the blessed registry.")
            continue
        pinned = str(metadata.get("commit") or "").strip().lower()
        if not pinned:
            warnings.append(f"{module.name}: blessed registry entry has no full commit pin.")
        elif (module.path / ".git").exists():
            current = git_current_head(module.path)
            if current is None:
                warnings.append(f"{module.name}: could not read git HEAD.")
            elif current != pinned:
                warnings.append(f"{module.name}: at {current[:12]}, expected pinned {pinned[:12]}.")
            if git_short_status(module.path):
                warnings.append(f"{module.name}: installed runtime has local git changes.")
        else:
            warnings.append(f"{module.name}: installed runtime is not a git checkout.")
    return warnings


def truthy_env(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def runtime_guard_bypassed(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "allow_dirty_runtime", False)) or truthy_env("SPARK_ALLOW_DIRTY_RUNTIME")


def runtime_guard_is_strict() -> bool:
    return truthy_env("SPARK_STRICT_RUNTIME_PINS")


def emit_runtime_supply_chain_guard(modules: Iterable[Module], args: argparse.Namespace) -> bool:
    """Warn, or fail in strict mode, when Spark would run a dirty managed checkout."""
    if runtime_guard_bypassed(args):
        return True
    warnings = runtime_supply_chain_warnings(modules)
    if not warnings:
        return True

    strict = runtime_guard_is_strict()
    marker = "blocked" if strict else "warning"
    print(f"Spark runtime hygiene {marker}: installed runtime code has drifted from the pinned registry.")
    for warning in warnings:
        print(f"  - {warning}")
    print("")
    print("Recommended workflow:")
    print("  - Keep ~/.spark/modules/... as installed runtime only.")
    print("  - Build in a dev checkout/worktree, for example C:\\Users\\USER\\Desktop\\spawner-ui.")
    print("  - Test dev servers on another port, for example 5174, then commit/push and run spark update.")
    if strict:
        print("")
        print("To run anyway for local development, add --allow-dirty-runtime or set SPARK_ALLOW_DIRTY_RUNTIME=1.")
        return False
    print("")
    print("Continuing for now. To silence this for intentional local runtime testing, add --allow-dirty-runtime.")
    return True


def dependency_lockfile_errors() -> list[str]:
    installed = load_json(REGISTRY_PATH, {})
    errors: list[str] = []
    if not isinstance(installed, dict):
        return errors
    for name, record in sorted(installed.items()):
        if not isinstance(record, dict):
            continue
        path = Path(str(record.get("path") or "")).expanduser()
        if not path.exists():
            continue
        if (path / "package.json").exists() and not any(
            (path / lockfile).exists()
            for lockfile in ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock")
        ):
            errors.append(f"Node module `{name}` has package.json but no dependency lockfile.")
        if (path / "pyproject.toml").exists() and not any(
            (path / lockfile).exists()
            for lockfile in ("uv.lock", "poetry.lock", "pdm.lock", "requirements.lock", "requirements.txt")
        ):
            errors.append(f"Python module `{name}` has pyproject.toml but no dependency lock/requirements file.")
    return errors


def requirement_line_is_pinned(line: str) -> bool:
    raw = line.split("#", 1)[0].strip()
    if not raw:
        return True
    if raw.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
        return True
    if raw.startswith(("--index-url", "--extra-index-url", "--find-links", "--trusted-host")):
        return True
    if raw.startswith("-e "):
        return raw.startswith(("-e .", "-e ./", "-e ../")) or re.search(r"@[0-9a-fA-F]{7,40}\b", raw) is not None
    if raw.startswith(("git+", "http://", "https://")):
        return re.search(r"@[0-9a-fA-F]{7,40}\b", raw) is not None
    if " @ " in raw:
        return True
    return "==" in raw


def dependency_pin_errors() -> list[str]:
    installed = load_json(REGISTRY_PATH, {})
    errors: list[str] = []
    if not isinstance(installed, dict):
        return errors
    for name, record in sorted(installed.items()):
        if not isinstance(record, dict):
            continue
        path = Path(str(record.get("path") or "")).expanduser()
        requirements_path = path / "requirements.txt"
        if not requirements_path.exists():
            continue
        try:
            lines = requirements_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            errors.append(f"Python module `{name}` requirements.txt could not be read.")
            continue
        unpinned = [
            line.split("#", 1)[0].strip()
            for line in lines
            if line.split("#", 1)[0].strip() and not requirement_line_is_pinned(line)
        ]
        if unpinned:
            errors.append(
                f"Python module `{name}` has unpinned requirements: {', '.join(unpinned[:5])}."
            )
    return errors


NODE_LOCKFILES = ("package-lock.json", "npm-shrinkwrap.json")


def package_json_dependency_maps(payload: Any) -> dict[str, dict[str, str]]:
    if not isinstance(payload, dict):
        return {}
    maps: dict[str, dict[str, str]] = {}
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        raw = payload.get(key)
        if isinstance(raw, dict):
            maps[key] = {str(name): str(spec) for name, spec in raw.items()}
    return maps


def package_dependency_spec_is_commit_pinned(spec: str) -> bool:
    raw = str(spec or "").strip()
    if not raw:
        return True
    if raw.startswith(("file:", "link:", "workspace:")):
        return True
    if raw.startswith(("git+", "github:", "gitlab:", "bitbucket:")) or ".git#" in raw:
        return re.search(r"#[0-9a-fA-F]{7,40}\b", raw) is not None
    return True


def dependency_lock_integrity_errors() -> list[str]:
    installed = load_json(REGISTRY_PATH, {})
    errors: list[str] = []
    if not isinstance(installed, dict):
        return errors
    for name, record in sorted(installed.items()):
        if not isinstance(record, dict):
            continue
        path = Path(str(record.get("path") or "")).expanduser()
        package_json_path = path / "package.json"
        if not package_json_path.exists():
            continue
        try:
            package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Node module `{name}` package.json could not be read: {exc}.")
            continue
        dep_maps = package_json_dependency_maps(package_json)
        for dep_name, spec in sorted({dep: spec for deps in dep_maps.values() for dep, spec in deps.items()}.items()):
            if not package_dependency_spec_is_commit_pinned(spec):
                errors.append(f"Node module `{name}` dependency `{dep_name}` uses an unpinned git/source spec.")

        lock_path = next((path / lockfile for lockfile in NODE_LOCKFILES if (path / lockfile).exists()), None)
        if lock_path is None:
            continue
        try:
            lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"Node module `{name}` dependency lockfile could not be read: {exc}.")
            continue
        lock_version = lock_payload.get("lockfileVersion") if isinstance(lock_payload, dict) else None
        if not isinstance(lock_version, int) or lock_version < 1:
            errors.append(f"Node module `{name}` dependency lockfile has no valid lockfileVersion.")
            continue
        packages = lock_payload.get("packages") if isinstance(lock_payload, dict) else None
        root_package = packages.get("") if isinstance(packages, dict) else None
        legacy_deps = lock_payload.get("dependencies") if isinstance(lock_payload, dict) else None
        for section, deps in dep_maps.items():
            locked_root = root_package.get(section) if isinstance(root_package, dict) else None
            for dep_name, spec in sorted(deps.items()):
                root_spec = locked_root.get(dep_name) if isinstance(locked_root, dict) else None
                if root_package is not None and root_spec != spec:
                    errors.append(f"Node module `{name}` lockfile root entry is stale for `{dep_name}`.")
                    continue
                package_entry = packages.get(f"node_modules/{dep_name}") if isinstance(packages, dict) else None
                legacy_entry = legacy_deps.get(dep_name) if isinstance(legacy_deps, dict) else None
                if package_entry is None and legacy_entry is None:
                    errors.append(f"Node module `{name}` lockfile is missing resolved entry for `{dep_name}`.")
    return errors


def requirement_file_enables_hash_mode(lines: list[str]) -> bool:
    return any("--require-hashes" in line.split("#", 1)[0] for line in lines)


def requirement_line_needs_hash(line: str) -> bool:
    raw = line.split("#", 1)[0].strip()
    if not raw:
        return False
    if raw.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
        return False
    if raw.startswith(("--index-url", "--extra-index-url", "--find-links", "--trusted-host", "--require-hashes")):
        return False
    return "--hash=" not in raw


def dependency_hash_mode_errors() -> list[str]:
    installed = load_json(REGISTRY_PATH, {})
    errors: list[str] = []
    if not isinstance(installed, dict):
        return errors
    for name, record in sorted(installed.items()):
        if not isinstance(record, dict):
            continue
        requirements_path = Path(str(record.get("path") or "")).expanduser() / "requirements.txt"
        if not requirements_path.exists():
            continue
        try:
            lines = requirements_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        if not requirement_file_enables_hash_mode(lines):
            continue
        unhashed = [line.split("#", 1)[0].strip() for line in lines if requirement_line_needs_hash(line)]
        if unhashed:
            errors.append(f"Python module `{name}` uses --require-hashes but has unhashed requirements: {', '.join(unhashed[:5])}.")
    return errors


def endpoint_security_errors() -> list[str]:
    errors: list[str] = []
    provider_payload = provider_status_payload()
    urls: list[tuple[str, str]] = []
    roles = provider_payload.get("roles")
    if isinstance(roles, dict):
        for role, role_payload in roles.items():
            if isinstance(role_payload, dict) and role_payload.get("base_url"):
                urls.append((f"llm role {role}", str(role_payload["base_url"])))

    for env_name in ("spawner-ui.env", "spark-telegram-bot.env", "spark-intelligence-builder.env"):
        env_values = read_generated_env(MODULE_CONFIG_DIR / env_name)
        for key, value in env_values.items():
            if ("URL" in key or key.endswith("_HOST")) and value:
                for raw_url in str(value).split(","):
                    urls.append((f"{env_name}:{key}", raw_url.strip()))

    for label, raw_url in urls:
        errors.extend(
            validate_url_safety(
                raw_url,
                label=label,
                policy=UrlPolicy(allow_local=True, allow_private_networks=False, require_https_for_remote=True),
            )
        )
    return errors


def module_allowed_secret_env_vars(module: Module) -> set[str]:
    return {binding["env_var"].upper() for binding in module_secret_env_bindings(module)}


def generated_env_contract_errors(modules: dict[str, Module] | None = None) -> list[str]:
    loaded = modules if modules is not None else resolve_installed_modules()
    blocked = provider_secret_env_blocklist()
    errors: list[str] = []
    for module in loaded.values():
        allowed = module_allowed_secret_env_vars(module)
        env_path = generated_module_env_path(module)
        generated = read_generated_env(env_path)
        leaked = sorted(key for key in generated if key.upper() in blocked and key.upper() not in allowed)
        if leaked:
            errors.append(
                f"{module.name} generated env contains reserved provider secret env var(s): {', '.join(leaked)}."
            )
    return errors


def runtime_env_contract_errors(modules: dict[str, Module] | None = None) -> list[str]:
    try:
        loaded = modules if modules is not None else resolve_installed_modules()
    except (OSError, SystemExit, KeyError, tomllib.TOMLDecodeError) as exc:
        return [f"Could not inspect installed module env contracts: {exc}."]
    blocked = provider_secret_env_blocklist()
    errors = generated_env_contract_errors(loaded)
    for module in loaded.values():
        allowed = module_allowed_secret_env_vars(module)
        try:
            env = module_runtime_env(module)
        except (OSError, SystemExit, KeyError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"Could not build runtime env for {module.name}: {exc}.")
            continue
        leaked = sorted(key for key in env if key.upper() in blocked and key.upper() not in allowed)
        if leaked:
            errors.append(
                f"{module.name} runtime env exposes undeclared provider secret env var(s): {', '.join(leaked)}."
            )
    return errors


def agency_guardrail_errors() -> list[str]:
    errors: list[str] = []
    if str(os.environ.get("SPARK_ALLOW_HOSTED_FULL_ACCESS") or "").strip().lower() in {"1", "true", "yes", "on"}:
        errors.append("SPARK_ALLOW_HOSTED_FULL_ACCESS is enabled; hosted full-access mode should stay off unless privately approval-gated.")
    return errors


def audit_visibility_errors() -> list[str]:
    errors: list[str] = []
    if not LOG_DIR.exists():
        return ["Spark log directory does not exist yet."]
    pids = load_pids()
    for key, record in sorted(pids.items()):
        if not isinstance(record, dict):
            continue
        raw_log_path = str(record.get("log_path") or "").strip()
        if raw_log_path and not Path(raw_log_path).exists():
            errors.append(f"Tracked process `{key}` points at missing log file.")
    return errors


def pending_setup_errors() -> list[str]:
    if not SETUP_PENDING_PATH.exists():
        return []
    pending = load_pending_setup_state()
    if not pending:
        return ["Pending setup marker exists but could not be read."]
    stage = str(pending.get("stage") or "unknown")
    detail = str(pending.get("detail") or "no stop reason recorded")
    return [f"Pending setup stopped at {stage}: {detail}"]


def autostart_runtime_errors() -> list[str]:
    profiles = autostart_telegram_profiles()
    if not profiles:
        return []
    installed = load_json(REGISTRY_PATH, {})
    setup_state = load_json(CONFIG_PATH, {})
    installed_names = set(installed.keys()) if isinstance(installed, dict) else set()
    expected = expected_runtime_process_names(installed_names, setup_state if isinstance(setup_state, dict) else {})
    if not expected:
        return [f"Telegram autostart profiles are enabled ({', '.join(profiles)}), but no runtime process is expected."]
    ok, detail = process_runtime_detail(load_pids(), expected)
    if ok:
        return []
    return [f"Autostart profiles enabled ({', '.join(profiles)}), but runtime is not live: {detail}"]


def collect_security_audit_payload(*, deep: bool = False, hosted: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    secret_surface = collect_secret_surface_payload()
    checks.append(security_check(
        "secret_surface",
        bool(secret_surface.get("ok")),
        str(secret_surface.get("detail", "")),
        "spark fix secrets --redact-logs",
        severity="high",
    ))

    home_errors = spark_home_boundary_errors()
    checks.append(security_check(
        "spark_home_boundary",
        not home_errors,
        "SPARK_HOME is scoped to Spark-owned state." if not home_errors else "; ".join(home_errors),
        "Set SPARK_HOME to a dedicated Spark directory such as <spark-home> for local use or /data/spark for hosted use.",
        severity="high",
    ))

    write_errors = spark_home_write_errors()
    checks.append(security_check(
        "spark_home_writable",
        not write_errors,
        "Spark-owned state directories are readable/writable." if not write_errors else "; ".join(write_errors),
        "Repair ownership/permissions for the Spark home, then rerun spark security audit.",
        severity="medium",
    ))

    permission_errors = local_secret_file_permission_errors()
    checks.append(security_check(
        "secret_file_permissions",
        not permission_errors,
        (
            "Local secret file permissions are private or handled by the OS keychain."
            if not permission_errors
            else "; ".join(permission_errors)
        ),
        "Run `spark setup` or `chmod 600 <spark-home>/config/secrets.local.json <spark-home>/config/secrets_index.json`.",
        severity="high",
    ))

    cloud_errors = hosted_cloud_credential_env_errors()
    checks.append(security_check(
        "ambient_cloud_credentials",
        not cloud_errors,
        "No cloud/admin deployment tokens are visible in this Spark process." if not cloud_errors else "; ".join(cloud_errors),
        "Remove cloud deployment credentials from the Spark runtime environment unless explicitly needed.",
        severity="high",
    ))

    control_errors = local_control_surface_errors()
    checks.append(security_check(
        "control_surface",
        not control_errors,
        "Spawner control surface is local-only or protected." if not control_errors else "; ".join(control_errors),
        "Bind Spawner to localhost, or configure exact SPARK_ALLOWED_HOSTS plus strong SPARK_UI_API_KEY/SPARK_BRIDGE_API_KEY.",
        severity="high",
    ))

    telegram_errors = telegram_polling_conflict_errors()
    checks.append(security_check(
        "telegram_polling",
        not telegram_errors,
        "No Telegram long-polling conflicts or reused profile tokens detected." if not telegram_errors else "; ".join(telegram_errors),
        "Use one bot token per running profile; stop duplicate pollers or rotate the affected BotFather token.",
        severity="high",
    ))

    pid_errors = pid_registry_errors()
    checks.append(security_check(
        "process_registry",
        not pid_errors,
        "Spark process registry has no malformed or stale entries." if not pid_errors else "; ".join(pid_errors[:5]),
        "Run `spark live restart`, or `spark stop telegram-starter` then `spark live start` to refresh supervised pids.",
        severity="medium",
    ))

    pending_errors = pending_setup_errors()
    checks.append(security_check(
        "pending_setup_state",
        not pending_errors,
        "No interrupted setup state is pending." if not pending_errors else "; ".join(pending_errors[:3]),
        "Run `spark onboard` or `spark setup telegram-starter --resume`.",
        severity="medium",
    ))

    autostart_errors = autostart_runtime_errors()
    checks.append(security_check(
        "autostart_runtime",
        not autostart_errors,
        "Autostart profiles are either disabled or backed by live supervised runtime processes."
        if not autostart_errors
        else "; ".join(autostart_errors[:3]),
        "Run `spark autostart on --now`, then `spark live status`.",
        severity="medium",
    ))

    supply_chain_errors = module_supply_chain_errors()
    checks.append(security_check(
        "module_supply_chain",
        not supply_chain_errors,
        "Installed modules match blessed registry pins and provenance boundaries." if not supply_chain_errors else "; ".join(supply_chain_errors[:6]),
        "Run `spark update --skip-dirty`, review local module edits, or reinstall the affected module from the blessed registry pin.",
        severity="high",
    ))

    provenance_payload = collect_module_provenance_payload()
    provenance_errors = [
        f"{check.get('name', 'unknown')}: {', '.join(check.get('warnings', [])) or check.get('detail', 'provenance check failed')}"
        for check in provenance_payload.get("checks", [])
        if not check.get("ok")
    ]
    checks.append(security_check(
        "module_provenance",
        bool(provenance_payload.get("ok")),
        "Blessed registry modules have commit pins and attestation metadata." if not provenance_errors else "; ".join(provenance_errors[:6]),
        "Run `spark verify --provenance`, then update registry pins/attestations before publishing the installer.",
        severity="high",
    ))

    lockfile_errors = dependency_lockfile_errors()
    checks.append(security_check(
        "dependency_lockfiles",
        not lockfile_errors,
        "Installed modules have dependency lockfiles or requirements where expected." if not lockfile_errors else "; ".join(lockfile_errors[:6]),
        "Add lockfiles/requirements for affected modules before publishing or pinning a release.",
        severity="medium",
    ))

    pin_errors = dependency_pin_errors()
    checks.append(security_check(
        "dependency_pins",
        not pin_errors,
        "Python requirements are pinned where requirements.txt is used." if not pin_errors else "; ".join(pin_errors[:6]),
        "Pin affected requirements to exact versions or immutable source refs before publishing.",
        severity="medium",
    ))

    lock_integrity_errors = dependency_lock_integrity_errors()
    checks.append(security_check(
        "dependency_lock_integrity",
        not lock_integrity_errors,
        "Node dependency lockfiles match package manifests and git/source specs are commit-pinned."
        if not lock_integrity_errors
        else "; ".join(lock_integrity_errors[:6]),
        "Regenerate lockfiles with the intended package manager and pin git/source dependencies to immutable commits.",
        severity="medium",
    ))

    hash_mode_errors = dependency_hash_mode_errors()
    checks.append(security_check(
        "dependency_hash_mode",
        not hash_mode_errors,
        "Python --require-hashes files hash every install requirement." if not hash_mode_errors else "; ".join(hash_mode_errors[:6]),
        "Add --hash entries for every requirement or remove --require-hashes until the file is fully hashed.",
        severity="medium",
    ))

    endpoint_errors = endpoint_security_errors()
    checks.append(security_check(
        "endpoint_safety",
        not endpoint_errors,
        "Provider and bridge endpoints avoid obvious SSRF/misrouting hazards." if not endpoint_errors else "; ".join(endpoint_errors[:6]),
        "Use HTTPS for remote providers, localhost for local-only services, and never point providers at metadata or wildcard addresses.",
        severity="high",
    ))

    runtime_env_errors = runtime_env_contract_errors()
    checks.append(security_check(
        "runtime_env_contract",
        not runtime_env_errors,
        "Runtime envs only expose provider secrets through declared module bindings." if not runtime_env_errors else "; ".join(runtime_env_errors[:6]),
        "Move provider/API keys into Spark secrets, declare needed secrets in spark.toml, then rerun `spark setup --resume`.",
        severity="high",
    ))

    agency_errors = agency_guardrail_errors()
    checks.append(security_check(
        "agency_guardrails",
        not agency_errors,
        "Hosted full-access override is not enabled in this process." if not agency_errors else "; ".join(agency_errors),
        "Unset SPARK_ALLOW_HOSTED_FULL_ACCESS unless this is a private, approval-gated operator environment.",
        severity="high",
    ))

    visibility_errors = audit_visibility_errors()
    checks.append(security_check(
        "audit_visibility",
        not visibility_errors,
        "Spark logs are present for tracked runtime processes." if not visibility_errors else "; ".join(visibility_errors[:6]),
        "Run `spark live restart` so supervised processes recreate logs, then rerun the audit.",
        severity="medium",
    ))

    provider_payload = provider_status_payload()
    checks.append(security_check(
        "llm_roles",
        bool(provider_payload.get("ok")),
        security_provider_detail(provider_payload),
        "spark providers status",
        severity="medium",
    ))

    generated_env = read_generated_env(MODULE_CONFIG_DIR / "spark-telegram-bot.env")
    gateway_mode = generated_env.get("TELEGRAM_GATEWAY_MODE", "polling")
    checks.append(security_check(
        "telegram_ingress_mode",
        gateway_mode == "polling",
        (
            "Telegram is using long polling."
            if gateway_mode == "polling"
            else f"Telegram gateway mode is {gateway_mode}; launch profile should stay on long polling for this release."
        ),
        "spark setup --resume",
        severity="high",
    ))

    status_payload = collect_status_payload()
    repair_hints = status_payload.get("repair_hints") if isinstance(status_payload, dict) else []
    checks.append(security_check(
        "runtime_health",
        bool(status_payload.get("ok")) if isinstance(status_payload, dict) else False,
        "Spark runtime health is clean." if not repair_hints else "; ".join(str(item) for item in repair_hints[:3]),
        "spark live status",
        severity="medium",
    ))

    should_include_hosted = hosted or running_as_hosted_context()
    if should_include_hosted:
        hosted_payload = collect_hosted_security_payload(deep=deep)
        for check in hosted_payload.get("checks", []):
            if not isinstance(check, dict):
                continue
            checks.append(security_check(
                f"hosted_{check.get('name', 'unknown')}",
                bool(check.get("ok")),
                str(check.get("detail") or ""),
                str(check.get("repair") or "spark live verify"),
                severity="high" if check.get("required", True) else "medium",
            ))

    if deep and not should_include_hosted:
        checks.append(
            {
                "name": "deep_verify",
                "ok": bool(collect_verify_payload(deep=True).get("ok")),
                "severity": "medium",
                "detail": "Deep verification completed; run `spark verify --deep` for full details.",
                "repair": "spark verify --deep",
            }
        )

    findings = [check for check in checks if not check.get("ok")]
    return {
        "ok": not findings,
        "checks": checks,
        "findings": findings,
        "summary": "Spark security audit",
        "share_policy": "Use `spark support bundle --include-logs` only after reviewing the local archive.",
    }


def cmd_security(args: argparse.Namespace) -> int:
    if args.security_command == "revoke-all":
        payload = execute_security_revoke_all(
            dry_run=bool(getattr(args, "dry_run", False)),
            include_logs=bool(getattr(args, "include_logs", False)),
        )
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload.get("ok") else 1
        print_security_revoke_all_payload(payload)
        return 0 if payload.get("ok") else 1
    if args.security_command != "audit":
        raise SystemExit(f"Unknown security command: {args.security_command}")
    payload = collect_security_audit_payload(deep=args.deep, hosted=getattr(args, "hosted", False))
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    print("Spark security audit")
    print("")
    for check in payload["checks"]:
        if check.get("ok"):
            marker = "[OK]"
        else:
            severity = str(check.get("severity") or "medium").upper()
            marker = f"[FIX:{severity}]"
        print(f"{marker} {check['name']}: {check['detail']}")
        if not check.get("ok") and check.get("repair"):
            print(f"      {check['repair']}")
    print("")
    print("Safe sharing:")
    print("  Nothing is uploaded by this command.")
    print("  Review every bundle before sharing.")
    print("  spark support bundle")
    print("  spark support bundle --include-logs")
    return 0 if payload.get("ok") else 1


def cmd_approval(args: argparse.Namespace) -> int:
    if args.approval_command != "classify":
        raise SystemExit(f"Unknown approval command: {args.approval_command}")
    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Usage: spark approval classify -- <command>")
    decision = approval_required_for_command(
        command,
        CommandContext(
            surface=str(getattr(args, "surface", "cli") or "cli"),
            hosted=bool(getattr(args, "hosted", False)),
            non_interactive=bool(getattr(args, "non_interactive", False)),
        ),
    )
    payload = {
        "ok": True,
        "mode": "report_only",
        "decision": decision.to_dict(),
        "note": "Report-only classifier. Spark is not enforcing this decision yet.",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("Spark approval classifier")
    print(f"Class: {decision.action_class}")
    print(f"Risk: {decision.risk}")
    print(f"Requires approval: {'yes' if decision.requires_approval else 'no'}")
    print(f"Reason: {decision.reason}")
    if decision.target_display:
        print(f"Target: {decision.target_display}")
    if decision.confirmation_phrase:
        print(f"Confirmation phrase: {decision.confirmation_phrase}")
    print("Mode: report-only")
    return 0


def print_access_payload(payload: dict[str, Any]) -> None:
    recommended = payload.get("recommended") if isinstance(payload.get("recommended"), dict) else {}
    print("Spark access setup")
    print(f"Access level: {payload.get('access_level')}")
    print(f"OS: {payload.get('os_family')}")
    print(f"Workspace: {payload.get('workspace_path')}")
    print(f"Recommended lane: {recommended.get('label') or recommended.get('id')}")
    if recommended.get("user_message"):
        print(str(recommended["user_message"]))
    if recommended.get("os_hint"):
        print(str(recommended["os_hint"]))
    workspace_preflight = payload.get("workspace_preflight") if isinstance(payload.get("workspace_preflight"), dict) else {}
    if workspace_preflight:
        print(f"Workspace preflight: {'writable' if workspace_preflight.get('writable') else 'not writable'}")
    guide = payload.get("guide") if isinstance(payload.get("guide"), dict) else {}
    if guide:
        print("")
        print(str(guide.get("summary") or "Guided access path"))
        print(str(guide.get("plain_default") or "Use the Spark workspace first."))
        if guide.get("security_note"):
            print(str(guide["security_note"]))
        print("Stronger sandbox order: Docker -> Modal -> SSH")
    level5 = payload.get("level5") if isinstance(payload.get("level5"), dict) else {}
    if int(payload.get("access_level") or 0) >= 5:
        if level5.get("enabled"):
            print("Level 5 guardrails: active")
        elif level5.get("restart_required"):
            print("Level 5 guardrails: configured, restart Spark to activate")
        else:
            print("Level 5 guardrails: blocked until explicitly enabled")
    print("")
    print("Available lanes:")
    for lane in payload.get("lanes", []):
        if not isinstance(lane, dict):
            continue
        marker = "*" if lane.get("recommended") else "-"
        status = "ready" if lane.get("available") else str(lane.get("setup_mode") or "guided")
        print(f"  {marker} {lane.get('label') or lane.get('id')}: {status}")
    print("")
    print(f"Next: {payload.get('next')}")


def cmd_access(args: argparse.Namespace) -> int:
    from .sandbox.access import access_lane_payload, level5_disable_payload

    if getattr(args, "access_command", "") == "disable-level5":
        payload = level5_disable_payload()
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
            return 0 if payload.get("ok") else 1
        print("Spark Level 5 guardrails disabled.")
        print("Restart Spark so Telegram and Spawner reload the safer access state.")
        print(f"Next: {payload.get('next')}")
        return 0 if payload.get("ok") else 1

    requested_lane = str(getattr(args, "with_lane", "") or "")
    goal = str(getattr(args, "goal", "") or "")
    if requested_lane and requested_lane not in goal.lower():
        goal = f"{goal} {requested_lane}".strip()
    payload = access_lane_payload(
        level=int(getattr(args, "level", 4) or 4),
        goal=goal,
        setup=getattr(args, "access_command", "") == "setup",
        enable_high_agency=bool(getattr(args, "enable_high_agency", False)),
    )
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1
    print_access_payload(payload)
    return 0 if payload.get("ok") else 1


def cmd_sandbox(args: argparse.Namespace) -> int:
    from .sandbox.capabilities import CapabilityManifest
    from .sandbox.docker import collect_docker_doctor_payload, collect_docker_smoke_payload
    from .sandbox.modal import collect_modal_doctor_payload, collect_modal_smoke_payload
    from .sandbox.ssh import (
        add_ssh_target,
        collect_ssh_doctor_payload,
        collect_ssh_smoke_payload,
        list_ssh_targets,
        remove_ssh_target,
        ssh_management_capabilities,
        trust_ssh_target_host_key,
    )

    backend = getattr(args, "sandbox_backend", "") or "unknown"
    command = getattr(args, f"{backend}_command", "") or "unknown"
    if backend == "ssh" and command in {"add", "list", "remove", "doctor", "trust", "smoke"}:
        try:
            if command == "add":
                target, warnings = add_ssh_target(
                    name=args.name,
                    host=args.host,
                    user=args.user,
                    identity_file=args.identity_file,
                    port=args.port,
                )
                payload = {
                    "ok": True,
                    "backend": "ssh",
                    "command": "add",
                    "target": target.to_public_dict(),
                    "warnings": warnings,
                    "capabilities": ssh_management_capabilities().to_dict(),
                    "next": f"Run `spark sandbox ssh trust {target.name}`, then `spark sandbox ssh doctor {target.name}`.",
                }
                exit_code = 0
            elif command == "list":
                payload = {
                    "ok": True,
                    "backend": "ssh",
                    "command": "list",
                    "targets": [target.to_public_dict() for target in list_ssh_targets()],
                    "capabilities": ssh_management_capabilities().to_dict(),
                }
                exit_code = 0
            elif command == "remove":
                removed = remove_ssh_target(args.name)
                payload = {
                    "ok": removed,
                    "backend": "ssh",
                    "command": "remove",
                    "target": args.name,
                    "removed": removed,
                    "capabilities": ssh_management_capabilities().to_dict(),
                }
                exit_code = 0 if removed else 1
            elif command == "doctor":
                payload = collect_ssh_doctor_payload(args.name, remote_probe=bool(getattr(args, "remote_probe", False)))
                exit_code = 0 if payload.get("ok") else 1
            elif command == "smoke":
                payload = collect_ssh_smoke_payload(args.name, keep_debug_files=bool(getattr(args, "keep_debug_files", False)))
                exit_code = 0 if payload.get("ok") else 1
            elif command == "trust":
                target, scan = trust_ssh_target_host_key(
                    args.name,
                    expected_fingerprint=getattr(args, "fingerprint", "") or "",
                )
                payload = {
                    "ok": True,
                    "backend": "ssh",
                    "command": "trust",
                    "target": target.to_public_dict(),
                    "host_key": scan.to_dict(),
                    "capabilities": ssh_management_capabilities().to_dict(),
                    "next": f"Run `spark sandbox ssh doctor {target.name}` to verify trusted host-key status.",
                }
                exit_code = 0
            else:
                raise ValueError(f"Unsupported SSH sandbox command: {command}")
        except ValueError as error:
            payload = {
                "ok": False,
                "backend": "ssh",
                "command": command,
                "error": str(error),
                "capabilities": ssh_management_capabilities().to_dict(),
            }
            exit_code = 1
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            if command in {"doctor", "smoke"} and "checks" in payload:
                status = "OK" if payload.get("ok") else "needs attention"
                print(f"Spark SSH sandbox {command}: {status}")
                target = payload.get("target")
                target_name = target.get("name") if isinstance(target, dict) else getattr(args, "name", "")
                print(f"Target: {target_name}")
                for check in payload.get("checks", []):
                    marker = "OK" if check.get("ok") else "WARN" if check.get("level") == "warning" else "FAIL"
                    print(f"  [{marker}] {check['name']}: {check['detail']}")
                    if check.get("repair") and not check.get("ok"):
                        print(f"        Repair: {check['repair']}")
                print(payload["next"])
            elif payload.get("ok"):
                print(f"Spark SSH sandbox {command}: OK")
                if command == "list":
                    targets = payload.get("targets") or []
                    if not targets:
                        print("No SSH sandbox targets configured.")
                    for target in targets:
                        print(f"  - {target['name']}: {target['user']}@{target['host']}:{target['port']} ({target['host_key_status']})")
                elif command == "add":
                    target = payload["target"]
                    print(f"Target: {target['name']} -> {target['user']}@{target['host']}:{target['port']}")
                    print("Host key: unverified")
                    for warning in payload.get("warnings", []):
                        print(f"Warning: {warning}")
                    print(payload["next"])
                elif command == "remove":
                    print(f"Removed target: {payload['target']}")
                elif command == "trust":
                    target = payload["target"]
                    host_key = payload["host_key"]
                    print(f"Target: {target['name']} -> {target['user']}@{target['host']}:{target['port']}")
                    print(f"Trusted host key: {host_key['fingerprint']} ({host_key['key_type']})")
                    print(payload["next"])
            else:
                print(f"Spark SSH sandbox {command}: failed")
                print(payload.get("error") or f"Target not found: {getattr(args, 'name', '')}")
        return exit_code

    if backend == "modal" and command in {"doctor", "smoke"}:
        if command == "doctor":
            payload = collect_modal_doctor_payload()
        else:
            payload = collect_modal_smoke_payload()
        exit_code = 0 if payload.get("ok") else 1
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            status = "OK" if payload.get("ok") else "needs attention"
            print(f"Spark Modal sandbox {command}: {status}")
            for check in payload.get("checks", []):
                marker = "OK" if check.get("ok") else "WARN" if check.get("level") == "warning" else "FAIL"
                print(f"  [{marker}] {check['name']}: {check['detail']}")
                if check.get("repair") and not check.get("ok"):
                    print(f"        Repair: {check['repair']}")
            print(payload["next"])
        return exit_code

    if backend == "docker" and command in {"doctor", "smoke"}:
        if command == "doctor":
            payload = collect_docker_doctor_payload()
        else:
            payload = collect_docker_smoke_payload(
                build=not bool(getattr(args, "no_build", False)),
                image=getattr(args, "image", "") or None,
                network=bool(getattr(args, "network", False)),
            )
        exit_code = 0 if payload.get("ok") else 1
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            status = "OK" if payload.get("ok") else "needs attention"
            print(f"Spark Docker sandbox {command}: {status}")
            for check in payload.get("checks", []):
                marker = "OK" if check.get("ok") else "WARN" if check.get("level") == "warning" else "FAIL"
                print(f"  [{marker}] {check['name']}: {check['detail']}")
                if check.get("repair") and not check.get("ok"):
                    print(f"        Repair: {check['repair']}")
            print(payload["next"])
        return exit_code

    manifest = CapabilityManifest(backend=backend)
    payload = {
        "ok": False,
        "backend": backend,
        "command": command,
        "implemented": False,
        "capabilities": manifest.to_dict(),
        "next": "Remote sandbox execution is planned but not implemented yet. Start with docs/REMOTE_SANDBOX_IMPLEMENTATION_PLAN.md.",
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print("Spark remote sandbox")
        print(f"Backend: {backend}")
        print(f"Command: {command}")
        print("Status: planned, not implemented yet")
        print("Next: follow docs/REMOTE_SANDBOX_IMPLEMENTATION_PLAN.md")
    return 2


APPROVAL_ENFORCED_ACTION_CLASSES = {
    "credential_mutation",
    "destructive_filesystem",
    "external_publish",
    "git_history_mutation",
    "identity_access_mutation",
    "network_exfiltration",
    "remote_code_execution",
    "container_privilege_escalation",
    "process_autostart_mutation",
}


def approval_enforcement_enabled() -> bool:
    return str(os.environ.get("SPARK_APPROVAL_ENFORCE", "1")).strip().lower() not in {"0", "false", "no", "off"}


def command_argv_for_approval(argv: list[str] | None) -> list[str]:
    return ["spark", *(list(argv) if argv is not None else sys.argv[1:])]


def approval_context_for_args(args: argparse.Namespace) -> CommandContext:
    return CommandContext(
        surface="cli",
        hosted=running_as_hosted_context(),
        non_interactive=bool(getattr(args, "non_interactive", False)) or not stdin_is_tty(),
    )


def should_enforce_approval(args: argparse.Namespace, decision: Any) -> bool:
    if not decision.requires_approval:
        return False
    if getattr(args, "command", "") == "approval":
        return False
    if decision.action_class not in APPROVAL_ENFORCED_ACTION_CLASSES:
        return False
    if getattr(args, "command", "") == "setup" and decision.action_class == "identity_access_mutation":
        return False
    return True


def enforce_cli_approval(args: argparse.Namespace, command_argv: list[str]) -> int | None:
    if not approval_enforcement_enabled():
        return None
    context = approval_context_for_args(args)
    decision = approval_required_for_command(command_argv, context)
    if not should_enforce_approval(args, decision):
        return None
    if decision.approval_mode == "blocked":
        print("Spark blocked a sensitive action because this shell is non-interactive.")
        print(f"Class: {decision.action_class}")
        print(f"Risk: {decision.risk}")
        print(f"Reason: {decision.reason}")
        print("Run the command again in an interactive terminal so Spark can ask for confirmation.")
        return 2
    print("Spark needs confirmation before continuing.")
    print(f"Class: {decision.action_class}")
    print(f"Risk: {decision.risk}")
    print(f"Reason: {decision.reason}")
    if decision.target_display:
        print(f"Target: {decision.target_display}")
    print(f"Type exactly: {decision.confirmation_phrase}")
    response = input("Approval phrase: ").strip().lower()
    if response != decision.confirmation_phrase:
        print("Approval not granted. Nothing changed.")
        return 2
    return None


def redact_sensitive_text(value: str) -> str:
    redacted = str(value)
    for pattern in SENSITIVE_VALUE_PATTERNS:
        if pattern.pattern.startswith("(?i)(api"):
            redacted = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", redacted)
        elif pattern.pattern.startswith("(?i)(bearer"):
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_shareable_text(value: str) -> str:
    redacted = redact_sensitive_text(value)
    spark_home = str(SPARK_HOME)
    if spark_home:
        redacted = redacted.replace(spark_home, "<spark-home>")
        redacted = redacted.replace(spark_home.replace("\\", "/"), "<spark-home>")
    home = str(Path.home())
    if home:
        redacted = redacted.replace(home, "~")
        redacted = redacted.replace(home.replace("\\", "/"), "~")
    redacted = redacted.replace("~/.spark", "<spark-home>")
    redacted = redacted.replace("~\\.spark", "<spark-home>")
    redacted = re.sub(r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s]+", "%USERPROFILE%", redacted)
    redacted = re.sub(r"(?i)\b/Users/[^/\s]+", "$HOME", redacted)
    redacted = re.sub(r"(?i)\b/home/[^/\s]+", "$HOME", redacted)
    redacted = re.sub(
        r"(?i)\b(Telegram(?:\s+admin)?\s+ID|Admin\s+ID|ALLOWED_TELEGRAM_IDS)(\s*[:=]\s*)(\d{5,16})\b",
        lambda match: f"{match.group(1)}{match.group(2)}[TELEGRAM_ID_REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b",
        "[PRIVATE_IP_REDACTED]",
        redacted,
    )
    return redacted


def redact_shareable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): redact_shareable_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_shareable_payload(item) for item in value]
    if isinstance(value, str):
        return redact_shareable_text(value)
    return value


SHARE_SAFETY_REMAINING_RISK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("token_like_value", re.compile(r"\b(?:bot)?\d{7,12}:[A-Za-z0-9_-]{30,}\b")),
    ("api_key_like_value", re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{16,}|sk-proj-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|gho_[A-Za-z0-9_]{16,}|ghp_[A-Za-z0-9_]{16,}|glpat-[A-Za-z0-9_\-]{16,}|xoxb-[A-Za-z0-9_\-]{16,}|xoxp-[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{16,})\b")),
    ("authorization_header", re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{16,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("windows_user_path", re.compile(r"(?i)\b[A-Z]:[\\/]Users[\\/][^\\/\s]+")),
    ("unix_user_path", re.compile(r"(?i)\b(?:/Users|/home)/[^/\s]+")),
    ("telegram_id_context", re.compile(r"(?i)\b(?:Telegram(?:\s+admin)?\s+ID|Admin\s+ID|ALLOWED_TELEGRAM_IDS)\s*[:=]\s*\d{5,16}\b")),
]


def collect_share_safety_findings(value: Any) -> list[dict[str, str]]:
    text = json.dumps(value, sort_keys=True, default=str) if not isinstance(value, str) else value
    findings: list[dict[str, str]] = []
    for name, pattern in SHARE_SAFETY_REMAINING_RISK_PATTERNS:
        if pattern.search(text):
            findings.append({"kind": name, "action": "review_or_redact_before_sharing"})
    return findings


def build_share_safety_manifest(value: Any, *, include_logs: bool, purpose: str) -> dict[str, Any]:
    return {
        "purpose": purpose,
        "uploaded": False,
        "review_required": True,
        "logs_included": bool(include_logs),
        "raw_logs_allowed": False,
        "redactions_applied": [
            "api_keys_tokens_and_authorization_headers",
            "telegram_bot_tokens",
            "home_and_spark_paths",
            "telegram_admin_id_context",
            "private_network_addresses",
        ],
        "remaining_risk_findings": collect_share_safety_findings(value),
        "safe_sharing_rules": [
            "Share only after reading the generated file locally.",
            "Do not include raw logs, chat transcripts, local project names, screenshots with secrets, or environment dumps.",
            "For upstream fixes, summarize the general bug and attach a focused code/test diff instead of a machine-specific report.",
        ],
    }


def redact_for_llm(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if re.search(r"(?i)(api[_-]?key|token|secret|password|authorization)", key_text):
                if isinstance(item, bool):
                    result[key_text] = item
                elif item in (None, "", [], {}):
                    result[key_text] = item
                else:
                    result[key_text] = "[REDACTED]"
            else:
                result[key_text] = redact_for_llm(item)
        return result
    if isinstance(value, list):
        return [redact_for_llm(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def collect_llm_doctor_context(problem: str, *, include_logs: bool = False, log_lines: int = 80) -> dict[str, Any]:
    status_payload = collect_status_payload()
    context: dict[str, Any] = {
        "problem": problem,
        "status": status_payload,
        "providers": provider_status_payload(),
        "verify": collect_verify_payload(deep=False),
        "local_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "safety": {
            "secrets_redacted": True,
            "logs_included": bool(include_logs),
            "mode": "advisory_only",
        },
    }
    if include_logs:
        logs: dict[str, list[str]] = {}
        for module in status_payload.get("modules", []):
            if not isinstance(module, dict) or not module.get("name"):
                continue
            name = str(module["name"])
            lines = tail_log_lines(module_log_path(name), log_lines)
            if lines:
                logs[name] = [redact_sensitive_text(line.rstrip()) for line in lines]
        context["logs"] = logs
    return redact_for_llm(context)


def render_llm_doctor_prompt(context: dict[str, Any]) -> str:
    return (
        "You are Spark Doctor, a local repair advisor for the Spark agent stack.\n"
        "The user explicitly asked you to diagnose a Spark problem. Work only from the redacted local context below.\n\n"
        "Security rules:\n"
        "- Never ask for or print secrets, tokens, API keys, cookies, private keys, or raw environment dumps.\n"
        "- Do not suggest raw provider API calls that require tokens; prefer Spark CLI repair commands such as `spark fix telegram`, `spark restart`, `spark verify`, and `spark logs`.\n"
        "- Do not recommend publishing logs unless the user has reviewed them.\n"
        "- Do not include local usernames, private project paths, Telegram ids, chat transcripts, raw logs, or machine-specific secrets in an upstream PR.\n"
        "- Prefer reversible commands and explicit confirmation before destructive actions.\n"
        "- If a fix could help upstream Spark, ask the user whether they want to prepare a sanitized upstream PR candidate after the local fix is understood.\n"
        "- The upstream question must be opt-in and must mention that nothing will be uploaded automatically.\n\n"
        "Engineering rules:\n"
        "- Think before coding: name assumptions and ask for missing information when needed.\n"
        "- Simplicity first: prefer the smallest repair that restores the user's system.\n"
        "- Surgical changes: avoid unrelated refactors.\n"
        "- Goal driven: give concrete verification commands.\n\n"
        "Return concise Markdown with these sections:\n"
        "1. Likely Cause\n"
        "2. Local Fix Plan\n"
        "3. Commands To Run\n"
        "4. Verification\n"
        "5. Upstream PR Candidate\n\n"
        "In section 5, say either \"Not a good upstream PR candidate\" or ask exactly one permission-style question like: "
        "\"Do you want me to prepare a sanitized upstream PR candidate so this can be fixed for other Spark users?\" "
        "If yes, point them to `spark doctor llm <problem> --save-report --upstream-report`.\n\n"
        "Redacted local context JSON:\n"
        f"{json.dumps(context, indent=2, sort_keys=True)}\n"
    )


def configured_llm_role_state(role: str) -> dict[str, Any]:
    setup_state = load_json(CONFIG_PATH, {})
    llm_state = setup_state.get("llm") if isinstance(setup_state, dict) else {}
    if not isinstance(llm_state, dict):
        return {}
    roles = llm_state.get("roles")
    if isinstance(roles, dict) and isinstance(roles.get(role), dict):
        state = dict(roles[role])
    else:
        state = dict(llm_state)
    state.setdefault("provider", llm_state.get("provider"))
    state.setdefault("model", llm_state.get("model"))
    state.setdefault("auth_mode", llm_state.get("auth_mode"))
    return state


def resolve_llm_doctor_target(args: argparse.Namespace) -> dict[str, Any]:
    requested_provider = getattr(args, "provider", None)
    requested_role = getattr(args, "role", "builder")
    role_order = [requested_role, "chat", "builder", "mission", "memory"]
    seen: set[str] = set()
    for role in role_order:
        if role in seen:
            continue
        seen.add(role)
        state = configured_llm_role_state(role)
        state_provider = str(state.get("provider") or "not_configured")
        provider = str(requested_provider or state_provider)
        if provider == "not_configured":
            continue
        spec = LLM_PROVIDER_ENV.get(provider)
        if not spec:
            continue
        use_role_defaults = provider == state_provider
        model = str(
            getattr(args, "model", None)
            or (state.get("model") if use_role_defaults else None)
            or spec.get("model_default")
            or ""
        )
        base_url = str(
            getattr(args, "base_url", None)
            or (state.get("base_url") if use_role_defaults else None)
            or spec.get("base_url_default")
            or ""
        )
        auth_mode = str(state.get("auth_mode") or "not_configured")
        if provider in {"openai", "zai", "kimi", "minimax", "openrouter", "huggingface"}:
            secret_id = spec.get("api_key_secret")
            api_key = fetch_secret(str(secret_id)) if secret_id else None
            if api_key:
                return {
                    "provider": provider,
                    "role": role,
                    "model": model,
                    "base_url": base_url,
                    "api_key": api_key,
                    "auth_mode": "api_key",
                }
        if provider == "ollama":
            return {
                "provider": provider,
                "role": role,
                "model": model,
                "base_url": base_url,
                "auth_mode": "local",
            }
        if provider == "codex" or (provider == "openai" and auth_mode == "codex_oauth"):
            codex = detect_codex_cli()
            if codex["present"]:
                return {
                    "provider": provider,
                    "role": role,
                    "model": model,
                    "base_url": base_url,
                    "auth_mode": "codex_oauth",
                    "cli_path": codex["path"],
                }
        if provider == "anthropic" and (requested_provider == "anthropic" or auth_mode == "claude_oauth"):
            claude = detect_claude_code()
            if claude["present"]:
                return {
                    "provider": provider,
                    "role": role,
                    "model": model,
                    "base_url": base_url,
                    "auth_mode": "claude_oauth",
                    "cli_path": claude["path"],
                }
        if auth_mode not in {"not_configured", ""}:
            return {
                "provider": provider,
                "role": role,
                "model": model,
                "base_url": base_url,
                "auth_mode": auth_mode,
                "unsupported": True,
            }
    raise SystemExit("No directly callable LLM provider is configured for Spark Doctor. Run `spark setup` and choose OpenAI, OpenRouter, Z.AI GLM, MiniMax, Hugging Face, or Ollama for chat/builder.")


def openai_compatible_chat_completion(target: dict[str, Any], prompt: str) -> str:
    base_url = str(target["base_url"]).rstrip("/")
    url = f"{base_url}/chat/completions"
    body = {
        "model": target["model"],
        "messages": [
            {"role": "system", "content": "You are Spark Doctor. Be concise, practical, and security careful."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {target['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    choices = payload.get("choices")
    if not choices:
        raise SystemExit("LLM provider returned no choices.")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content")
    if not content:
        raise SystemExit("LLM provider returned an empty doctor response.")
    return str(content)


def ollama_chat_completion(target: dict[str, Any], prompt: str) -> str:
    base_url = str(target["base_url"]).rstrip("/")
    url = f"{base_url}/api/chat"
    body = {
        "model": target["model"],
        "stream": False,
        "messages": [
            {"role": "system", "content": "You are Spark Doctor. Be concise, practical, and security careful."},
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    message = payload.get("message") if isinstance(payload, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not content:
        raise SystemExit("Ollama returned an empty doctor response.")
    return str(content)


def llm_cli_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def llm_cli_cwd() -> str:
    return str(SPARK_HOME if SPARK_HOME.exists() else Path.cwd())


def codex_cli_completion(target: dict[str, Any], prompt: str) -> str:
    codex_path = str(target.get("cli_path") or shutil.which("codex") or "codex")
    command = [
        codex_path,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
    ]
    model = str(target.get("model") or "").strip()
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    result = subprocess.run(
        command,
        cwd=llm_cli_cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        creationflags=llm_cli_creationflags(),
        env=shell_command_env(filtered=True),
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        detail = summarize_command_output(result) or f"codex exited with code {result.returncode}"
        raise SystemExit(detail)
    if not output:
        raise SystemExit("Codex CLI returned an empty response.")
    return output


def claude_cli_completion(target: dict[str, Any], prompt: str) -> str:
    claude_path = str(target.get("cli_path") or shutil.which("claude") or "claude")
    if os.name == "nt" and claude_path.lower().endswith(".ps1"):
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            claude_path,
            "-p",
            "--output-format",
            "text",
        ]
    else:
        command = [claude_path, "-p", "--output-format", "text"]
    model = str(target.get("model") or "").strip()
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    result = subprocess.run(
        command,
        cwd=llm_cli_cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        creationflags=llm_cli_creationflags(),
        env=shell_command_env(filtered=True),
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        detail = summarize_command_output(result) or f"claude exited with code {result.returncode}"
        raise SystemExit(detail)
    if not output:
        raise SystemExit("Claude CLI returned an empty response.")
    return output


def call_llm_doctor(target: dict[str, Any], prompt: str) -> str:
    if target.get("unsupported"):
        provider = target.get("provider")
        raise SystemExit(
            f"Spark Doctor cannot directly call {provider} via {target.get('auth_mode')} yet. "
            "Use --prompt-out to review the redacted prompt, or configure OpenAI Codex/Anthropic Claude/Z.AI GLM/Kimi/OpenRouter/Hugging Face/MiniMax/OpenAI/Ollama."
        )
    provider = target["provider"]
    if provider in {"openai", "zai", "kimi", "minimax", "openrouter", "huggingface"}:
        if target.get("auth_mode") == "codex_oauth":
            return codex_cli_completion(target, prompt)
        return openai_compatible_chat_completion(target, prompt)
    if provider == "codex":
        return codex_cli_completion(target, prompt)
    if provider == "anthropic" and target.get("auth_mode") == "claude_oauth":
        return claude_cli_completion(target, prompt)
    if provider == "ollama":
        return ollama_chat_completion(target, prompt)
    raise SystemExit(f"Spark Doctor cannot directly call provider `{provider}` yet.")


def write_doctor_report(content: str, *, prefix: str = "spark-doctor") -> Path:
    output_dir = SPARK_HOME / "doctor"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"{prefix}-{stamp}.md"
    path.write_text(content, encoding="utf-8")
    return path


def render_upstream_pr_candidate(problem: str, doctor_report: str) -> str:
    safe_problem = redact_shareable_text(problem).strip() or "Spark doctor repair"
    safe_report = redact_shareable_text(doctor_report).strip()
    manifest = build_share_safety_manifest(
        {"problem": safe_problem, "doctor_report": safe_report},
        include_logs=False,
        purpose="upstream_pr_candidate",
    )
    remaining_findings = manifest.get("remaining_risk_findings") or []
    remaining_text = (
        "None detected by Spark's local redaction scan."
        if not remaining_findings
        else "\n".join(f"- {item.get('kind')}: {item.get('action')}" for item in remaining_findings if isinstance(item, dict))
    )
    return (
        "# Spark Upstream PR Candidate\n\n"
        "This draft is sanitized for review, not automatically uploaded. Read it before sharing.\n\n"
        "## Share Safety Manifest\n"
        "- Uploaded: no\n"
        "- Review required: yes\n"
        "- Raw logs allowed: no\n"
        "- Remaining risk scan:\n"
        f"{remaining_text}\n\n"
        "## Safety Checklist\n"
        "- [ ] No API keys, bot tokens, secrets, cookies, private keys, or Authorization headers.\n"
        "- [ ] No personal chat transcripts, private project names, Telegram ids, or local usernames.\n"
        "- [ ] No raw logs unless they were manually reviewed and minimized.\n"
        "- [ ] The proposed change is useful for other Spark users, not only this local machine.\n"
        "- [ ] The PR includes a focused test or verification command.\n\n"
        "## User-Visible Problem\n"
        f"{safe_problem}\n\n"
        "## Doctor Summary To Convert Into A PR\n"
        f"{safe_report}\n\n"
        "## Recommended Upstream Shape\n"
        "- Keep the PR small and focused on one failure class.\n"
        "- Add or update a unit test that reproduces the failure without real secrets.\n"
        "- Prefer docs or repair-hint changes when code changes are not needed.\n"
        "- Do not include this whole doctor report in the PR body; summarize the general bug and the fix.\n"
    )


def cmd_doctor_llm(args: argparse.Namespace) -> int:
    problem = " ".join(getattr(args, "problem", []) or []).strip() or "Spark is not working correctly."
    context = collect_llm_doctor_context(
        problem,
        include_logs=bool(getattr(args, "include_logs", False)),
        log_lines=int(getattr(args, "log_lines", 80)),
    )
    prompt = render_llm_doctor_prompt(context)
    if getattr(args, "prompt_out", None):
        prompt_path = Path(args.prompt_out).expanduser()
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"Wrote redacted Spark Doctor prompt: {prompt_path}")
        return 0
    target = resolve_llm_doctor_target(args)
    try:
        response = call_llm_doctor(target, prompt)
    except urllib.error.HTTPError as exc:
        provider = target.get("provider", "unknown")
        if exc.code == 401:
            raise SystemExit(
                f"[FIX] Provider {provider} returned 401 Unauthorized.\n"
                f"  Check that your API key is valid: spark secrets list\n"
                f"  Reconfigure: spark setup --llm-provider {provider}"
            ) from None
        raise SystemExit(
            f"[FIX] Provider {provider} returned HTTP {exc.code}: {exc.reason}.\n"
            f"  Check provider status and your API key, then retry."
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        provider = target.get("provider", "unknown")
        raise SystemExit(
            f"[FIX] Could not reach provider {provider}: {exc}\n"
            f"  Check network connectivity and provider status, then retry.\n"
            f"  Repair: spark providers test --role chat"
        ) from None
    report = (
        "# Spark Doctor Report\n\n"
        f"Provider: {target['provider']} ({target.get('model') or 'default'})\n"
        f"Role: {target.get('role')}\n"
        f"Logs included: {bool(getattr(args, 'include_logs', False))}\n\n"
        f"{response.strip()}\n\n"
        "## Sharing Upstream\n"
        "This report is local. Do not paste it into a PR until you review it for private paths, project names, and sensitive context.\n"
        "If the fix is broadly useful, create a small PR with the code/test change, not raw logs or secrets.\n"
        "Question: Do you want to prepare a sanitized upstream PR candidate so this can be fixed for other Spark users? If yes, rerun this command with `--upstream-report`. Spark will still only write a local draft for your review.\n"
    )
    if getattr(args, "save_report", False):
        path = write_doctor_report(report)
        print(f"Saved Spark Doctor report: {path}")
    if getattr(args, "upstream_report", False):
        upstream = render_upstream_pr_candidate(problem, report)
        upstream_out = getattr(args, "upstream_out", None)
        if upstream_out:
            upstream_path = Path(upstream_out).expanduser()
            upstream_path.parent.mkdir(parents=True, exist_ok=True)
            upstream_path.write_text(upstream, encoding="utf-8")
        else:
            upstream_path = write_doctor_report(upstream, prefix="spark-upstream-pr-candidate")
        print(f"Saved sanitized upstream PR candidate: {upstream_path}")
        print("Review the checklist before opening a PR. Spark did not upload anything.")
    print(report)
    return 0


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
        "No LLM provider is configured. Run `spark setup` to choose an Agent provider and Mission provider."
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
    process_record: dict[str, Any] | None = None
    if isinstance(pids, dict):
        for process_key in tracked_process_keys_for_module(pids, "spark-telegram-bot"):
            candidate = pids.get(process_key)
            if not isinstance(candidate, dict):
                continue
            if pid_is_running(int(candidate.get("pid", 0))):
                process_record = candidate
                process_running = True
                break
    process_detail = (
        f"spark-telegram-bot is running under Spark supervision (pid {process_record.get('pid')})."
        if process_running and isinstance(process_record, dict)
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
    payload = {
        "ok": ok,
        "summary": "Spark Telegram repair",
        "checks": checks,
        "status_repair_hints": status_payload.get("repair_hints", []),
        "next_commands": [
            "spark status",
            "spark verify --onboarding",
            "spark verify --deep",
            "spark restart telegram-starter",
            "spark logs spark-telegram-bot --lines 80",
            "spark setup telegram-starter",
        ],
    }
    payload["route_context"] = build_fix_route_context("telegram", payload)
    return payload


def build_fix_route_context(target: str, payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    ok = all(bool(check.get("ok")) for check in checks if isinstance(check, dict))
    failed_check_names = [
        str(check.get("name") or "").strip()
        for check in checks
        if isinstance(check, dict) and not bool(check.get("ok"))
    ]
    target_labels = {
        "telegram": "telegram_runtime",
        "spawner": "spawner_ui",
        "providers": "provider_auth",
        "memory": "memory_runtime",
        "live": "spark_live",
        "update": "spark_update",
        "autostart": "spark_autostart",
    }
    scope_labels = {
        "telegram": "local_telegram_repair_guidance",
        "spawner": "local_spawner_repair_guidance",
        "providers": "provider_configuration_guidance",
        "memory": "memory_runtime_repair_guidance",
        "live": "spark_live_repair_guidance",
        "update": "spark_update_repair_guidance",
        "autostart": "spark_autostart_repair_guidance",
    }
    credential_checks = {"bot_token", "llm_roles", "provider roles"}
    consequence_risk = "credential" if any(name in credential_checks for name in failed_check_names) else "medium"
    route_fit = "blocked" if ok else "exact"
    return {
        "schema_version": "spark.repair_route_context.v1",
        "candidate_route": "spark.repair",
        "intent": "repair",
        "latest_instruction": "allow_execution",
        "intent_clarity": "explicit",
        "route_fit": route_fit,
        "consequence_risk": consequence_risk,
        "permission_required": "none",
        "authority_verdict": {
            "schema_version": "spark.authority_verdict.v1",
            "decision": "not_required",
            "source_owner": "spark-cli",
            "action_family": "spark.repair",
        },
        "capability_state": "available",
        "runner_state": "available",
        "confirmation_state": "not_required",
        "reversibility": "reversible",
        "repair_target": target_labels.get(target, "spark_runtime"),
        "repair_scope": scope_labels.get(target, "local_repair_guidance"),
        "health_evidence": "fresh_healthy" if ok else "fresh_degraded",
        "source_status": "present",
        "freshness": "current_turn",
        "joined_sources": ["spark-cli.fix", "spark-cli.status"],
        "failed_checks": failed_check_names[:8],
        "verification_command": f"spark fix {target} --json",
        "data_boundary": {
            "exports_raw_prompt": False,
            "exports_chat_id": False,
            "exports_provider_output": False,
            "exports_memory_body": False,
            "exports_transcript_body": False,
            "exports_audio": False,
            "exports_env_value": False,
            "exports_secret": False,
        },
    }


def collect_simple_fix_payload(target: str) -> dict[str, Any]:
    status_payload = collect_status_payload()
    provider_payload = provider_status_payload()
    status_modules = status_payload.get("modules") if isinstance(status_payload.get("modules"), list) else []
    spawner_module = next(
        (module for module in status_modules if isinstance(module, dict) and module.get("name") == "spawner-ui"),
        None,
    )
    recipes = {
        "spawner": {
            "summary": "Spark Spawner repair",
            "checks": [
                {
                    "name": "spawner-ui health",
                    "ok": bool(isinstance(spawner_module, dict) and spawner_module.get("healthy") is True),
                    "detail": (
                        str(spawner_module.get("detail"))
                        if isinstance(spawner_module, dict) and spawner_module.get("detail")
                        else "Spawner UI should answer on http://127.0.0.1:3333."
                    ),
                    "repair": "spark restart spawner-ui",
                },
                {
                    "name": "mission relay",
                    "ok": bool(provider_payload.get("ok")),
                    "detail": "Mission provider roles should be configured before /run.",
                    "repair": "spark providers status",
                },
            ],
            "next_commands": ["spark restart spawner-ui", "spark verify --onboarding", "spark logs spawner-ui --lines 80"],
        },
        "providers": {
            "summary": "Spark provider repair",
            "checks": [
                {
                    "name": "provider roles",
                    "ok": bool(provider_payload.get("ok")),
                    "detail": provider_payload.get("summary", "Provider status unavailable."),
                    "repair": "spark setup",
                }
            ],
            "next_commands": ["spark providers status", "spark providers test --role chat", "spark setup"],
        },
        "memory": {
            "summary": "Spark memory repair",
            "checks": [
                {
                    "name": "memory wiring",
                    "ok": bool(collect_verify_payload(deep=False).get("ok")),
                    "detail": "Builder, Researcher, and domain-chip-memory should be wired together.",
                    "repair": "spark verify --deep",
                }
            ],
            "next_commands": ["spark verify --deep", "spark status", "spark doctor llm \"Spark memory is not recalling\" --save-report"],
        },
        "live": {
            "summary": "Spark Live repair",
            "checks": [
                {
                    "name": "live readiness",
                    "ok": bool(status_payload.get("ok")),
                    "detail": "Spark Live expects Telegram profile(s), Spawner, providers, and memory to be ready.",
                    "repair": "spark live restart",
                }
            ],
            "next_commands": ["spark live status", "spark live restart", "spark live logs"],
        },
        "update": {
            "summary": "Spark update repair",
            "checks": [
                {
                    "name": "dirty module safety",
                    "ok": True,
                    "detail": "Use --skip-dirty when local module edits should not block clean modules from updating.",
                    "repair": "",
                }
            ],
            "next_commands": ["spark update --skip-dirty", "spark update --skip-dirty --skip-install-commands", "spark verify --onboarding"],
        },
        "autostart": {
            "summary": "Spark autostart repair",
            "checks": [
                {
                    "name": "login startup",
                    "ok": True,
                    "detail": "Use autostart status/on to make Spark Live start when the computer logs in.",
                    "repair": "",
                }
            ],
            "next_commands": ["spark autostart status", "spark autostart on --now", "spark fix autostart", "spark live status"],
        },
    }
    payload = recipes[target]
    payload["route_context"] = build_fix_route_context(target, payload)
    return payload


def collect_autostart_fix_payload() -> dict[str, Any]:
    profiles = autostart_telegram_profiles()
    configured = configured_telegram_profiles()
    manual = manual_telegram_profiles()
    expected_command = autostart_shell_command("start", "telegram-starter")
    hook_details: list[dict[str, Any]] = []
    installed = False

    def add_file_hook(name: str, path: Path | None, *, exists: bool | None = None) -> None:
        nonlocal installed
        if path is None:
            hook_details.append({"name": name, "path": "unavailable", "exists": False, "warnings": ["path unavailable"]})
            return
        audit = autostart_file_audit(path, expected_command=expected_command)
        if exists is not None:
            audit["exists"] = exists
        installed = installed or bool(audit["exists"])
        hook_details.append({"name": name, **audit})

    if sys.platform.startswith("linux") and running_under_wsl():
        add_file_hook("WSL Windows-login fallback", wsl_windows_startup_script_path())
    elif sys.platform.startswith("linux"):
        add_file_hook("Linux systemd service", linux_autostart_path(linux_autostart_scope()))
        add_file_hook("Linux desktop fallback", linux_xdg_autostart_path())
    elif sys.platform == "darwin":
        add_file_hook("macOS LaunchAgent", macos_autostart_path())
    elif sys.platform == "win32":
        task_result = run_autostart_helper(["schtasks", "/Query", "/TN", AUTOSTART_WINDOWS_TASK_NAME])
        task_installed = task_result.returncode == 0
        run_key_installed = windows_run_key_installed()
        installed = installed or task_installed or run_key_installed
        hook_details.append(
            {
                "name": "Windows logon task",
                "path": AUTOSTART_WINDOWS_TASK_NAME,
                "exists": task_installed,
                "warnings": [] if task_installed else ["scheduled task is not installed"],
            }
        )
        add_file_hook("Windows Startup fallback", windows_startup_script_path())
        hook_details.append(
            {
                "name": "Windows Run-key fallback",
                "path": windows_run_key_path(),
                "exists": run_key_installed,
                "warnings": [] if run_key_installed else ["Run-key fallback is not installed"],
            }
        )
    else:
        hook_details.append({"name": sys.platform, "path": "unsupported", "exists": False, "warnings": ["platform unsupported"]})

    existing_file_hooks = [hook for hook in hook_details if hook.get("exists") and hook.get("readable")]
    stale_hooks = [
        hook
        for hook in existing_file_hooks
        if hook.get("current_command") is False or hook.get("current_home") is False or hook.get("parent_private") is False
    ]
    hook_warnings = [
        warning
        for hook in hook_details
        for warning in hook.get("warnings", [])
        if hook.get("exists") or "platform unsupported" in str(warning) or "path unavailable" in str(warning)
    ]
    checks = [
        {
            "name": "OS login hook",
            "ok": installed,
            "detail": "At least one OS login autostart hook is installed." if installed else "No OS login autostart hook is installed.",
            "repair": "spark autostart on --now",
        },
        {
            "name": "current startup target",
            "ok": installed and not stale_hooks,
            "detail": (
                "Installed autostart hook(s) point at the current Spark command and home."
                if installed and not stale_hooks
                else "One or more installed autostart hook(s) look stale or writable by other local users."
                if installed and stale_hooks
                else "No autostart hook is installed; run `spark autostart on --now` to add one."
            ),
            "repair": "spark autostart on --now",
        },
        {
            "name": "Telegram profile selection",
            "ok": bool(profiles) or not configured,
            "detail": (
                f"Autostart profiles: {', '.join(profiles)}"
                if profiles
                else "No Telegram profiles are enabled for autostart."
            ),
            "repair": "spark autostart profile <profile> on",
        },
    ]
    return {
        "summary": "Spark autostart repair",
        "checks": checks,
        "hooks": hook_details,
        "warnings": hook_warnings,
        "telegram_profiles_configured": configured,
        "telegram_profiles_autostart": profiles,
        "telegram_profiles_manual": manual,
        "next_commands": [
            "spark autostart status",
            "spark autostart on --now",
            "spark autostart off",
            "spark live status",
        ],
    }


def cmd_fix(args: argparse.Namespace) -> int:
    if args.target == "secrets":
        if getattr(args, "redact_logs", False):
            result = redact_secret_surface_logs()
            changed = result.get("changed", [])
            print("Spark log redaction")
            print("")
            if changed:
                print(f"[OK] Redacted secret-like values in {len(changed)} log file(s).")
                for path in changed:
                    print(f"      {path}")
            else:
                print(f"[OK] No log files needed redaction ({result.get('scanned_files', 0)} scanned).")
            print("")
            print("Next:")
            print("  spark verify --deep")
            return 0

        payload = collect_secret_surface_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload.get("ok") else 1
        print("Spark secret surface check")
        print("")
        marker = "[OK]" if payload.get("ok") else "[FIX]"
        print(f"{marker} generated configs/logs: {payload['detail']}")
        for finding in payload.get("findings", []):
            counts = ", ".join(f"{key}={value}" for key, value in finding.get("counts", {}).items())
            print(f"      {finding.get('path')} ({counts})")
        if not payload.get("ok"):
            print("")
            print("Repair:")
            print("  - Run `spark fix secrets --redact-logs` to redact local generated logs.")
            print("  - Rerun `spark setup` after updating modules so keychain-backed secrets are removed from generated env files.")
            print("  - Run `spark verify --deep` again before sharing any diagnostics upstream.")
        return 0 if payload.get("ok") else 1

    if args.target in {"spawner", "providers", "memory", "live", "update", "autostart"}:
        payload = collect_autostart_fix_payload() if args.target == "autostart" else collect_simple_fix_payload(args.target)
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if all(check.get("ok") for check in payload.get("checks", [])) else 1
        print(payload["summary"])
        print("")
        for check in payload["checks"]:
            marker = "[OK]" if check["ok"] else "[FIX]"
            print(f"{marker} {check['name']}: {check['detail']}")
            if not check["ok"] and check.get("repair"):
                print(f"      {check['repair']}")
        if args.target == "autostart" and payload.get("hooks"):
            print("")
            print("Hooks:")
            for hook in payload["hooks"]:
                installed_text = "yes" if hook.get("exists") else "no"
                print(f"  - {hook.get('name')}: installed={installed_text}; {hook.get('path')}")
                for warning in hook.get("warnings", []):
                    print(f"      warning: {warning}")
        print("")
        print("Useful commands:")
        for command in payload["next_commands"]:
            print(f"  {command}")
        return 0 if all(check.get("ok") for check in payload.get("checks", [])) else 1

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
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider openai --openai-api-key <key>",
            },
            {
                "id": "codex",
                "label": "OpenAI Codex",
                "auth": ["codex_oauth"],
                "oauth_available": bool(codex["present"]),
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider codex",
            },
            {
                "id": "anthropic",
                "label": "Anthropic Claude",
                "auth": ["claude_oauth", "api_key"],
                "oauth_available": bool(claude["present"]),
                "recommended_for": ["chat", "builder"],
                "setup": "spark setup --llm-provider anthropic",
            },
            {
                "id": "openrouter",
                "label": "OpenRouter",
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "memory"],
                "setup": "spark setup --llm-provider openrouter --openrouter-api-key <key> --openrouter-model <model>",
            },
            {
                "id": "zai",
                "label": "Z.AI GLM",
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider zai --zai-api-key <key>",
            },
            {
                "id": "kimi",
                "label": "Kimi / Moonshot",
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "memory", "mission"],
                "setup": "spark setup --llm-provider kimi --kimi-api-key <key> --kimi-model <model>",
            },
            {
                "id": "huggingface",
                "label": "Hugging Face",
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "memory"],
                "setup": "spark setup --llm-provider huggingface --huggingface-api-key <key> --huggingface-model <model>",
            },
            {
                "id": "lmstudio",
                "label": "LM Studio",
                "auth": ["local"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "memory", "mission", "local/private"],
                "setup": "spark setup --llm-provider lmstudio --lmstudio-model <loaded-model-id>",
            },
            {
                "id": "minimax",
                "label": "MiniMax",
                "auth": ["api_key"],
                "oauth_available": False,
                "recommended_for": ["chat", "builder", "mission"],
                "setup": "spark setup --llm-provider minimax --minimax-api-key <key>",
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
            elif provider == "codex" and detect_codex_cli()["present"]:
                auth_mode = "codex_oauth"
            elif provider == "openai":
                base_kind = openai_base_url_kind(str(state.get("base_url") or llm_state.get("base_url") or ""))
                if base_kind == "local":
                    auth_mode = "local"
                elif base_kind == "default" and detect_codex_cli()["present"]:
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
            "base_url": state.get("base_url") or llm_state.get("base_url") or "",
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


def resolve_provider_test_target(role: str, provider: str | None = None) -> dict[str, Any]:
    args = argparse.Namespace(
        role=role,
        provider=provider,
        model=None,
        base_url=None,
    )
    return resolve_llm_doctor_target(args)


def provider_test_payload(*, role: str = "chat", provider: str | None = None) -> dict[str, Any]:
    try:
        target = resolve_provider_test_target(role, provider)
    except SystemExit as exc:
        return {
            "ok": False,
            "role": role,
            "provider": provider or "configured",
            "detail": str(exc),
            "repair": "spark setup",
        }
    safe_target = redact_for_llm(target)
    if target.get("unsupported"):
        return {
            "ok": False,
            "role": role,
            "provider": target.get("provider"),
            "model": target.get("model"),
            "auth_mode": target.get("auth_mode"),
            "detail": f"Provider {target.get('provider')} is configured but Spark CLI cannot directly probe this auth mode yet.",
            "repair": "spark providers status",
            "target": safe_target,
        }
    prompt = "Reply with exactly PING_OK. No extra words."
    try:
        response = call_llm_doctor(target, prompt).strip()
    except (SystemExit, urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "role": role,
            "provider": target.get("provider"),
            "model": target.get("model"),
            "auth_mode": target.get("auth_mode"),
            "detail": redact_sensitive_text(str(exc)),
            "repair": "spark setup",
            "target": safe_target,
        }
    return {
        "ok": "PING_OK" in response,
        "role": role,
        "provider": target.get("provider"),
        "model": target.get("model"),
        "auth_mode": target.get("auth_mode"),
        "detail": response if "PING_OK" in response else "Provider replied, but not with PING_OK.",
        "repair": "" if "PING_OK" in response else "spark setup",
        "target": safe_target,
    }


def cmd_providers(args: argparse.Namespace) -> int:
    if args.providers_command == "recommend":
        payload = provider_recommendations_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        print_llm_provider_recommendations(payload)
        return 0
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
    if args.providers_command == "test":
        payload = provider_test_payload(role=args.role, provider=args.provider)
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        marker = "[OK]" if payload.get("ok") else "[FIX]"
        print("Spark provider test")
        print("")
        print(
            f"{marker} {payload.get('role')} -> {payload.get('provider')} "
            f"({payload.get('model') or 'model unknown'}): {payload.get('detail')}"
        )
        if not payload.get("ok") and payload.get("repair"):
            print(f"Repair: {payload['repair']}")
        return 0 if payload["ok"] else 1
    raise SystemExit(f"Unknown providers command: {args.providers_command}")


def print_llm_provider_recommendations(payload: dict[str, Any]) -> None:
    print(terminal_color(f" {payload['summary']} ", "spark-title"))
    print(payload["default_rule"])
    print("")
    print(terminal_color("Best starting points", "spark-section"))
    print("  OpenAI Codex subscription:     spark setup --llm-provider codex")
    print("     Sign in first with:         codex login")
    print("")
    print("  Anthropic Claude subscription: spark setup --llm-provider anthropic")
    print('     Verify first with:          claude -p "hello"')
    print("")
    print("  Z.AI GLM API route:            spark setup --llm-provider zai --zai-api-key <key>")
    print("  Kimi/Moonshot API route:       spark setup --llm-provider kimi --kimi-api-key <key>")
    print("  Local/private desktop route:   spark setup --llm-provider lmstudio")
    print("  Local/private terminal:        spark setup --llm-provider ollama")
    print("")
    print(terminal_color("Provider guide", "spark-section"))
    for provider in payload["providers"]:
        models = ", ".join(provider["recommended_models"])
        provider_id = str(provider["id"])
        provider_pad = " " * max(1, 18 - len(provider_id))
        print(f"  {terminal_color(provider_id, 'spark-provider')}{provider_pad} {provider['lane']}")
        print(f"    Models: {models}")
        print(f"    Best for: {provider['best_for']}")
        print(f"    Start: {provider['getting_started']}")
        print("")


def cmd_recommend(args: argparse.Namespace) -> int:
    if args.recommend_command in {"llms", "providers"}:
        payload = provider_recommendations_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        print_llm_provider_recommendations(payload)
        return 0
    raise SystemExit(f"Unknown recommend command: {args.recommend_command}")


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


def env_path_candidates(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return []
    return [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def env_named_path_candidates(prefix: str, suffix: str) -> list[Path]:
    candidates: list[Path] = []
    for name, raw in os.environ.items():
        if not name.startswith(prefix) or not name.endswith(suffix) or not raw.strip():
            continue
        candidates.append(Path(raw).expanduser())
    return candidates


def unique_path_candidates(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    candidates: list[Path] = []
    for path in paths:
        key = os.path.normcase(os.path.normpath(str(path.expanduser())))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path.expanduser())
    return candidates


def installed_path_candidate(installed: object, module_name: str) -> Path | None:
    path = installed_record_path(installed, module_name)
    return path if path is not None and path.exists() else None


def first_existing_path(paths: list[Path]) -> Path | None:
    for candidate in paths:
        if candidate.exists():
            return candidate
    return None


def specialization_path_candidates(installed: object) -> list[Path]:
    candidates = [
        *env_path_candidates("SPARK_SPECIALIZATION_PATH_ROOTS"),
        *env_named_path_candidates("SPARK_SWARM_SPECIALIZATION_PATH_", "_REPO"),
    ]
    if isinstance(installed, dict):
        for name in sorted(installed):
            if str(name).startswith("specialization-path-"):
                candidate = installed_path_candidate(installed, str(name))
                if candidate is not None:
                    candidates.append(candidate)
    return unique_path_candidates(candidates)


def telegram_gateway_candidates(installed: object) -> list[Path]:
    candidates = env_path_candidates("SPARK_TELEGRAM_BOT_ROOT")
    candidate = installed_path_candidate(installed, "spark-telegram-bot")
    if candidate is not None:
        candidates.append(candidate)
    return candidates


def telegram_gateway_is_usable(path: Path) -> bool:
    return any(
        candidate.exists()
        for candidate in (
            path / "spark.toml",
            path / "package.json",
            path / "pyproject.toml",
            path / "src",
        )
    )


def specialization_path_is_usable(path: Path) -> bool:
    return any(
        candidate.exists()
        for candidate in (
            path / "specialization-path.json",
            path / "scripts" / "run_autoloop.py",
            path / "specialization-path" / "path.manifest.json",
            path / "path.manifest.json",
            path / "pyproject.toml",
        )
    )


def specialization_path_key(path: Path) -> str:
    for manifest in (
        path / "specialization-path.json",
        path / "specialization-path" / "path.manifest.json",
        path / "path.manifest.json",
    ):
        if not manifest.exists():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            for key in ("pathKey", "path_key", "key"):
                raw = payload.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    name = path.name
    if name.startswith("specialization-path-"):
        return name.removeprefix("specialization-path-")
    return name


def specialization_loop_status_command(path: Path, swarm_root: Path | None) -> tuple[list[str], dict[str, str]]:
    python = os.environ.get("SPARK_SWARM_BRIDGE_PYTHON") or sys.executable
    env = dict(os.environ)
    if swarm_root:
        bridge_src = swarm_root / "apps" / "bridge" / "src"
        if bridge_src.exists():
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(bridge_src) if not existing else f"{bridge_src}{os.pathsep}{existing}"
    return (
        [
            python,
            "-m",
            "spark_swarm_bridge.cli",
            "specialization-path",
            "status",
            specialization_path_key(path),
            str(path),
            "--json",
        ],
        env,
    )


def parse_json_object_from_stdout(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def validate_specialization_loop_status_packet(packet: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for field in ("schemaId", "pathKey", "decision", "evidenceState", "claimBoundary"):
        if packet.get(field) in (None, "", []):
            issues.append(f"missing {field}")
    decision = str(packet.get("decision") or "").strip().lower()
    comparison = packet.get("comparison")
    rounds = packet.get("rounds")
    evidence_decisions = {"improved", "held_steady", "regressed"}
    if decision in evidence_decisions:
        if not isinstance(comparison, dict):
            issues.append("comparison is not an object")
            comparison = {}
        if not isinstance(rounds, dict):
            issues.append("rounds is not an object")
            rounds = {}
        if comparison.get("baselineScore") is None:
            issues.append("missing comparison.baselineScore")
        if comparison.get("candidateScore") is None:
            issues.append("missing comparison.candidateScore")
        if comparison.get("delta") is None:
            issues.append("missing comparison.delta")
        if rounds.get("completed") is None:
            issues.append("missing rounds.completed")
    if decision == "improved":
        held_out = str(packet.get("heldOutStatus") or "").strip().lower()
        trap = str(packet.get("trapStatus") or "").strip().lower()
        if held_out not in {"passed", "pass"}:
            issues.append("improved claim requires held-out proof")
        if trap not in {"passed", "pass"}:
            issues.append("improved claim requires trap proof")
    return not issues, issues


def summarize_specialization_loop_status_packet(packet: dict[str, Any]) -> str:
    label = str(packet.get("pathLabel") or packet.get("pathKey") or "specialization path")
    decision = str(packet.get("decision") or "unknown").replace("_", " ")
    comparison = packet.get("comparison") if isinstance(packet.get("comparison"), dict) else {}
    baseline = comparison.get("baselineScore")
    candidate = comparison.get("candidateScore")
    delta = comparison.get("delta")
    proof = (
        f"held-out {packet.get('heldOutStatus', 'unknown')}, "
        f"trap {packet.get('trapStatus', 'unknown')}"
    )
    if baseline is not None and candidate is not None and delta is not None:
        return f"{label} status packet says {decision}; baseline {baseline}, candidate {candidate}, delta {delta}; {proof}."
    return f"{label} status packet says {decision}; {proof}."


def collect_specialization_loop_proofs(paths: list[Path], swarm_root: Path | None) -> list[dict[str, Any]]:
    proofs: list[dict[str, Any]] = []
    for path in paths:
        path_key = specialization_path_key(path)
        command, env = specialization_loop_status_command(path, swarm_root)
        proof: dict[str, Any] = {
            "path": str(path),
            "path_key": path_key,
            "ok": False,
            "detail": "",
            "issues": [],
        }
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            proof["detail"] = f"{path_key} status packet could not be read: {exc}"
            proof["issues"] = ["status command failed"]
            proofs.append(proof)
            continue
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            proof["detail"] = f"{path_key} status command exited {result.returncode}: {stderr[:240]}"
            proof["issues"] = ["status command failed"]
            proofs.append(proof)
            continue
        packet = parse_json_object_from_stdout(result.stdout)
        if packet is None:
            proof["detail"] = f"{path_key} status command did not return a JSON object."
            proof["issues"] = ["status packet was not JSON"]
            proofs.append(proof)
            continue
        ok, issues = validate_specialization_loop_status_packet(packet)
        proof.update(
            {
                "ok": ok,
                "detail": summarize_specialization_loop_status_packet(packet),
                "issues": issues,
                "packet": packet,
            }
        )
        proofs.append(proof)
    return proofs


def collect_specialization_loop_payload(*, proof: bool = False) -> dict[str, Any]:
    installed = load_json(REGISTRY_PATH, {})
    telegram_root = first_existing_path(telegram_gateway_candidates(installed))
    labs_root = first_existing_path([
        *env_path_candidates("SPARK_DOMAIN_CHIP_LABS_ROOT"),
        *env_path_candidates("SPARK_DOMAIN_CHIP_LABS_REPO"),
        *(candidate for candidate in [installed_path_candidate(installed, "spark-domain-chip-labs")] if candidate is not None),
    ])
    swarm_root = first_existing_path([
        *env_path_candidates("SPARK_SWARM_ROOT"),
        *env_path_candidates("SPARK_SWARM_RUNTIME_ROOT"),
        *(candidate for candidate in [installed_path_candidate(installed, "spark-swarm")] if candidate is not None),
    ])
    sibling_root = swarm_root.parent if swarm_root else None
    if not labs_root and sibling_root:
        labs_root = first_existing_path([sibling_root / "spark-domain-chip-labs"])
    path_roots = specialization_path_candidates(installed)
    if sibling_root:
        path_roots = unique_path_candidates([*path_roots, *sibling_root.glob("specialization-path-*")])
    usable_paths = [candidate for candidate in path_roots if specialization_path_is_usable(candidate)]

    telegram_ok = bool(telegram_root and telegram_gateway_is_usable(telegram_root))
    labs_schema_dir = labs_root / "docs" / "creator_system" / "schemas" if labs_root else None
    labs_ok = bool(
        labs_root
        and (labs_root / "src" / "chip_labs").exists()
        and labs_schema_dir
        and (labs_schema_dir / "creator-mission-status.schema.json").exists()
        and (labs_schema_dir / "specialization-loop-status.schema.json").exists()
    )
    swarm_ok = bool(
        swarm_root
        and (swarm_root / "config" / "specialization-paths.json").exists()
    )
    path_ok = bool(usable_paths)
    status_proofs = collect_specialization_loop_proofs(usable_paths, swarm_root) if proof and usable_paths else []
    status_proof_ok = bool(status_proofs) and all(bool(item.get("ok")) for item in status_proofs)

    checks = [
        {
            "name": "telegram_specialization_gateway",
            "ok": telegram_ok,
            "required": True,
            "detail": (
                f"spark-telegram-bot found at {telegram_root}; Telegram can surface specialization-loop status and safe prompts."
                if telegram_ok
                else "spark-telegram-bot is not installed or discoverable as SPARK_TELEGRAM_BOT_ROOT."
            ),
            "repair": "Run `spark setup telegram-starter`, install spark-telegram-bot, or set SPARK_TELEGRAM_BOT_ROOT to its repo path.",
        },
        {
            "name": "domain_chip_labs",
            "ok": labs_ok,
            "required": True,
            "detail": (
                f"spark-domain-chip-labs found at {labs_root} with creator and specialization-loop schemas."
                if labs_ok
                else "spark-domain-chip-labs is not installed or discoverable as SPARK_DOMAIN_CHIP_LABS_ROOT."
            ),
            "repair": "Install or update spark-domain-chip-labs, or set SPARK_DOMAIN_CHIP_LABS_ROOT to its repo path.",
        },
        {
            "name": "spark_swarm_specialization_registry",
            "ok": swarm_ok,
            "required": True,
            "detail": (
                f"spark-swarm specialization registry found at {swarm_root}."
                if swarm_ok
                else "spark-swarm is not installed or discoverable as SPARK_SWARM_ROOT."
            ),
            "repair": "Install spark-swarm or set SPARK_SWARM_ROOT to its repo path.",
        },
        {
            "name": "specialization_path",
            "ok": path_ok,
            "required": True,
            "detail": (
                f"{len(usable_paths)} specialization path root(s) are discoverable."
                if path_ok
                else "No usable specialization-path-* root is installed or listed in SPARK_SPECIALIZATION_PATH_ROOTS."
            ),
            "repair": "Install at least one specialization-path-* repo or set SPARK_SPECIALIZATION_PATH_ROOTS.",
            "paths": [str(path) for path in usable_paths],
        },
    ]
    if proof:
        checks.append(
            {
                "name": "specialization_loop_status_packet",
                "ok": status_proof_ok,
                "required": True,
                "detail": (
                    f"{len(status_proofs)} specialization path status packet(s) read and validated."
                    if status_proof_ok
                    else "Canonical specialization-loop status packet proof is missing or invalid."
                ),
                "repair": "Run `spark-swarm specialization-path status <path_key> <repo> --json` locally and fix missing benchmark evidence before claiming improvement.",
                "proofs": status_proofs,
            }
        )
    ok = all(bool(check["ok"]) for check in checks if check.get("required", True))
    return {
        "ok": ok,
        "summary": "Spark specialization loop verification",
        "checks": checks,
        "telegram_root": str(telegram_root) if telegram_root else None,
        "labs_root": str(labs_root) if labs_root else None,
        "swarm_root": str(swarm_root) if swarm_root else None,
        "specialization_paths": [str(path) for path in usable_paths],
        "proof_requested": bool(proof),
        "status_proofs": status_proofs,
        "safe_next_moves": [
            "Run `spark doctor specialization-loop` for plain-language repair guidance.",
            "Set SPARK_TELEGRAM_BOT_ROOT, SPARK_DOMAIN_CHIP_LABS_ROOT, SPARK_SWARM_ROOT, or SPARK_SPECIALIZATION_PATH_ROOTS when repos live outside Spark's installed registry.",
            "Use `spark verify --specialization-loop --proof` when you want canonical status-packet proof without starting a run.",
        ],
        "next_commands": [
            "spark verify --specialization-loop --json",
            "spark verify --specialization-loop --proof --json",
            "chip-labs creator-run-smoke <run-dir> --recompute --fail-on-blocked",
            "spark-swarm specialization-path status <path_key> <repo> --json",
        ],
        "boundary": "This check inspects discoverability. With --proof it also reads canonical status packets. It does not start runs, publish, delete, or repair automatically.",
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
    spawner_runtime_env = dict(spawner_env)
    spawner_path = installed_record_path(installed, "spawner-ui")
    if spawner_path is not None and spawner_path.exists():
        try:
            spawner_runtime_env = module_runtime_env(load_module(spawner_path))
        except (OSError, SystemExit, tomllib.TOMLDecodeError):
            spawner_runtime_env = dict(spawner_env)
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

    secret_surface = collect_secret_surface_payload()
    checks.append(
        {
            "name": "secret_surface",
            "ok": bool(secret_surface.get("ok")),
            "required": True,
            "detail": str(secret_surface.get("detail") or ""),
            "repair": str(secret_surface.get("repair") or "spark fix secrets"),
            "findings": secret_surface.get("findings", []),
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
    builder_ref_errors = builder_runtime_ref_errors(installed, gateway_env)
    checks.append(
        {
            "name": "builder_runtime_source",
            "ok": not builder_ref_errors,
            "required": True,
            "detail": (
                "Telegram generated runtime config points at the installed Builder module."
                if not builder_ref_errors
                else "; ".join(builder_ref_errors[:4])
            ),
            "repair": "spark update spark-intelligence-builder --skip-dirty --skip-install-commands",
        }
    )
    voice_expected = VOICE_MODULE_NAME in expected_modules or bool(
        isinstance(setup_state, dict)
        and isinstance(setup_state.get("voice"), dict)
        and setup_state["voice"].get("enabled")
    )
    if voice_expected:
        voice_secret_expected = bool(
            isinstance(setup_state, dict)
            and isinstance(setup_state.get("voice"), dict)
            and setup_state["voice"].get("elevenlabs_secret_configured")
        )
        voice_ok = (
            VOICE_MODULE_NAME in installed_names
            and bool(builder_env.get("SPARK_VOICE_COMMS_ROOT"))
            and "ELEVENLABS_API_KEY" not in builder_env
            and (not voice_secret_expected or "voice.elevenlabs.api_key" in secret_keys)
        )
        checks.append(
            {
                "name": "builder_voice_bridge",
                "ok": voice_ok,
                "required": True,
                "detail": (
                    "Builder has the voice chip root, and any ElevenLabs key stays in Spark secrets."
                    if voice_ok
                    else "Voice chip install, Builder voice root, or voice secret hygiene needs repair."
                ),
                "repair": f"spark setup {TELEGRAM_VOICE_BUNDLE}",
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
        and bool(spawner_env.get("TELEGRAM_RELAY_SECRET") or spawner_runtime_env.get("TELEGRAM_RELAY_SECRET"))
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
            "spark verify --onboarding",
            "spark verify --deep",
            "spark fix telegram",
            "spark start telegram-starter",
            "spark logs spark-telegram-bot --lines 80",
            "spark logs spawner-ui --lines 80",
        ],
    }


def collect_sandbox_verify_payload() -> dict[str, Any]:
    from .sandbox.docker import collect_docker_doctor_payload
    from .sandbox.modal import collect_modal_doctor_payload
    from .sandbox.ssh import collect_ssh_doctor_payload, load_ssh_targets

    docs = [
        REPO_ROOT / "docs" / "AGENTIC_REMOTE_SANDBOX_SECURITY_RESEARCH.md",
        REPO_ROOT / "docs" / "REMOTE_SANDBOX_SECURITY_CHECKLIST.md",
        REPO_ROOT / "docs" / "REMOTE_SANDBOX_IMPLEMENTATION_PLAN.md",
        REPO_ROOT / "docs" / "SSH_REMOTE_SANDBOX_ARCHITECTURE.md",
        REPO_ROOT / "docs" / "MODAL_SANDBOX_ARCHITECTURE.md",
    ]
    missing_docs = [str(path.relative_to(REPO_ROOT)) for path in docs if not path.exists()]
    checks: list[dict[str, Any]] = [
        {
            "name": "sandbox_security_docs",
            "ok": not missing_docs,
            "required": True,
            "level": "info" if not missing_docs else "error",
            "detail": "Remote sandbox security docs are present." if not missing_docs else f"Missing docs: {', '.join(missing_docs)}.",
            "repair": "Restore the remote sandbox docs before publishing sandbox integrations.",
        }
    ]

    docker = collect_docker_doctor_payload(timeout=3)
    checks.append({
        "name": "docker_doctor",
        "ok": bool(docker.get("ok")),
        "required": False,
        "level": "info" if docker.get("ok") else "warning",
        "detail": "Docker sandbox doctor is ready." if docker.get("ok") else "Docker is optional and not fully available.",
        "repair": "" if docker.get("ok") else "spark sandbox docker doctor --json",
    })

    ssh_targets: list[dict[str, Any]] = []
    try:
        targets = load_ssh_targets()
    except ValueError as error:
        checks.append({
            "name": "ssh_target_store",
            "ok": False,
            "required": True,
            "level": "error",
            "detail": str(error),
            "repair": "Review <spark-home>/config/ssh_targets.json.",
        })
        targets = {}

    if targets:
        for name, target in targets.items():
            doctor = collect_ssh_doctor_payload(name)
            ssh_targets.append({
                "name": name,
                "host": target.host,
                "user": target.user,
                "doctor_ok": bool(doctor.get("ok")),
            })
            checks.append({
                "name": f"ssh_doctor_{name}",
                "ok": bool(doctor.get("ok")),
                "required": True,
                "level": "info" if doctor.get("ok") else "error",
                "detail": f"SSH target `{name}` doctor passed." if doctor.get("ok") else f"SSH target `{name}` doctor needs attention.",
                "repair": f"spark sandbox ssh doctor {name} --json",
            })
    else:
        checks.append({
            "name": "ssh_targets",
            "ok": True,
            "required": False,
            "level": "info",
            "detail": "No SSH sandbox targets are configured yet.",
            "repair": "spark sandbox ssh add <name> --host <host> --user <user> --identity-file <path>",
        })

    modal = collect_modal_doctor_payload()
    checks.append({
        "name": "modal_doctor",
        "ok": bool(modal.get("ok")),
        "required": False,
        "level": "info" if modal.get("ok") else "warning",
        "detail": "Modal doctor is ready." if modal.get("ok") else "Modal is optional and not fully configured.",
        "repair": "spark sandbox modal doctor --json",
    })

    required_ok = all(bool(check["ok"]) for check in checks if check.get("required", True))
    return {
        "ok": required_ok,
        "summary": "Spark remote sandbox verification",
        "checks": checks,
        "docker_doctor": docker,
        "ssh_targets": ssh_targets,
        "modal_doctor": modal,
        "next_commands": [
            "spark sandbox docker doctor --json",
            "spark sandbox docker smoke --json",
            "spark sandbox ssh doctor <name> --remote-probe --json",
            "spark sandbox ssh smoke <name> --json",
            "spark sandbox modal doctor --json",
            "spark sandbox modal smoke --json",
        ],
    }


def current_uid() -> int | None:
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return None
    try:
        return int(getuid())
    except OSError:
        return None


def proc_uid_for_pid(pid: int) -> int | None:
    status_path = Path("/proc") / str(pid) / "status"
    try:
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Uid:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1])
    except (OSError, ValueError):
        return None
    return None


def tracked_runtime_uids() -> list[int]:
    uids: list[int] = []
    for record in load_pids().values():
        if not isinstance(record, dict):
            continue
        try:
            pid = int(record.get("pid", 0))
        except (TypeError, ValueError):
            continue
        if not pid or not pid_is_running(pid):
            continue
        uid = proc_uid_for_pid(pid)
        if uid is not None:
            uids.append(uid)
    return uids


def docker_socket_present() -> bool:
    return Path("/var/run/docker.sock").exists()


HOSTED_SENSITIVE_MOUNTPOINTS = {
    "/root",
    "/home/spark/.ssh",
    "/home/spark/.aws",
    "/home/spark/.azure",
    "/home/spark/.config/gcloud",
    "/home/spark/.docker",
    "/home/spark/.config/chromium",
    "/home/spark/.config/google-chrome",
}

HOSTED_CLOUD_CREDENTIAL_ENV_KEYS = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "CLOUDFLARE_API_TOKEN",
    "RAILWAY_TOKEN",
    "VERCEL_TOKEN",
    "FLY_API_TOKEN",
}


def decode_mountinfo_path(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def mountinfo_mountpoints(text: str) -> list[str]:
    mountpoints: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5:
            mountpoints.append(decode_mountinfo_path(parts[4]))
    return mountpoints


def hosted_sensitive_mount_errors(mountinfo_path: Path = Path("/proc/self/mountinfo")) -> list[str]:
    if os.name == "nt":
        return []
    try:
        mountinfo = mountinfo_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except OSError as exc:
        return [f"Could not inspect Linux mount table: {exc}."]

    errors: list[str] = []
    for mountpoint in mountinfo_mountpoints(mountinfo):
        normalized = mountpoint.rstrip("/") or "/"
        if normalized in HOSTED_SENSITIVE_MOUNTPOINTS:
            errors.append(f"Sensitive mountpoint is visible inside hosted Spark: {normalized}.")
    return errors


def hosted_cloud_credential_env_errors(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    exposed = [key for key in sorted(HOSTED_CLOUD_CREDENTIAL_ENV_KEYS) if source.get(key)]
    return [f"Hosted Spark should not receive cloud/admin credential env vars: {', '.join(exposed)}."] if exposed else []


def hosted_unsafe_home_paths() -> set[str]:
    unsafe = {"/", "/root"}
    try:
        unsafe.add(str(Path.home().resolve()))
    except RuntimeError:
        pass
    return unsafe


def hosted_spark_home_is_safe(value: str) -> bool:
    expanded = Path(value).expanduser()
    candidates = {value.strip(), str(expanded)}
    try:
        candidates.add(str(expanded.resolve()))
    except OSError:
        pass
    return not any(candidate in hosted_unsafe_home_paths() for candidate in candidates)


HOSTED_WEAK_SECRET_MARKERS = {
    "***",
    "admin",
    "changeme",
    "change-me",
    "change-me-now",
    "default",
    "dev",
    "password",
    "placeholder",
    "secret",
    "spark",
    "test",
    "token",
    "your_api_key",
}


def hosted_api_key_strength_errors(ui_key: str, bridge_key: str) -> list[str]:
    errors: list[str] = []
    values = {
        "SPARK_UI_API_KEY": (ui_key or "").strip(),
        "SPARK_BRIDGE_API_KEY": (bridge_key or "").strip(),
    }
    for name, value in values.items():
        lowered = value.lower()
        if not value:
            errors.append(f"{name} is missing.")
            continue
        if any(char.isspace() for char in value):
            errors.append(f"{name} contains whitespace.")
        if len(value) < 24:
            errors.append(f"{name} is shorter than 24 characters.")
        if lowered in HOSTED_WEAK_SECRET_MARKERS or any(
            marker in lowered for marker in ("changeme", "password", "placeholder")
        ):
            errors.append(f"{name} looks like a placeholder.")
    if values["SPARK_UI_API_KEY"] and values["SPARK_UI_API_KEY"] == values["SPARK_BRIDGE_API_KEY"]:
        errors.append("SPARK_UI_API_KEY and SPARK_BRIDGE_API_KEY must be different.")
    return errors


def hosted_allowed_host_errors(allowed_hosts: list[str]) -> list[str]:
    errors: list[str] = []
    blocked = {"*", "0.0.0.0", "::", "localhost", "127.0.0.1", "::1"}
    for host in allowed_hosts:
        normalized = host.strip().lower()
        host_without_port = normalized
        if normalized.startswith("[") and "]" in normalized:
            host_without_port = normalized[1 : normalized.index("]")]
        elif normalized.count(":") == 1:
            host_without_port = normalized.split(":", 1)[0]
        if normalized in blocked:
            errors.append(f"SPARK_ALLOWED_HOSTS contains unsafe host {host!r}.")
        if "*" in normalized:
            errors.append(f"SPARK_ALLOWED_HOSTS must not contain wildcards ({host!r}).")
        if "://" in normalized or "/" in normalized:
            errors.append(f"SPARK_ALLOWED_HOSTS must contain hostnames only, not URLs ({host!r}).")
        if ":" in normalized and not normalized.startswith("["):
            errors.append(f"SPARK_ALLOWED_HOSTS must not include ports ({host!r}).")
        try:
            address = ipaddress.ip_address(host_without_port)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast):
            errors.append(f"SPARK_ALLOWED_HOSTS must not contain private or local network addresses ({host!r}).")
    return errors


def hosted_secret_file_permission_errors(paths: list[Path] | None = None) -> list[str]:
    if os.name == "nt":
        return []
    errors: list[str] = []
    for path in paths or [SECRETS_FILE_PATH]:
        try:
            mode = path.stat().st_mode & 0o777
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"Could not inspect {path}: {exc}.")
            continue
        if mode & 0o077:
            errors.append(f"{path} is {oct(mode)}; hosted secret files should be 0600.")
    return errors


def hosted_llm_role_providers(env: dict[str, str] | None = None) -> dict[str, str]:
    source = env if env is not None else os.environ
    default_provider = (source.get("SPARK_LLM_PROVIDER") or "").strip().lower()
    return {
        "chat": (source.get("SPARK_CHAT_LLM_PROVIDER") or default_provider).strip().lower(),
        "builder": (source.get("SPARK_BUILDER_LLM_PROVIDER") or default_provider).strip().lower(),
        "memory": (source.get("SPARK_MEMORY_LLM_PROVIDER") or default_provider).strip().lower(),
        "mission": (source.get("SPARK_MISSION_LLM_PROVIDER") or default_provider).strip().lower(),
    }


def hosted_headless_provider_errors(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    role_providers = hosted_llm_role_providers(source)
    errors: list[str] = []

    if not any(role_providers.values()):
        return ["No hosted LLM provider is configured."]

    for role, provider in role_providers.items():
        if not provider or provider in {"none", "not_configured"}:
            errors.append(f"{role} provider is not configured.")
            continue

        auth_mode = (source.get(f"SPARK_{role.upper()}_LLM_AUTH_MODE") or source.get("SPARK_LLM_AUTH_MODE") or "").strip().lower()
        if auth_mode == "codex_oauth":
            errors.append(f"{role} uses Codex OAuth; hosted Docker/Railway needs a dedicated OPENAI_API_KEY.")
        elif provider == "codex" and not (source.get("OPENAI_API_KEY") or "").strip():
            errors.append(f"{role} uses Codex CLI but OPENAI_API_KEY is not configured for hosted mode.")
        elif provider == "anthropic" and auth_mode == "claude_oauth":
            errors.append(f"{role} uses Claude Code OAuth/CLI; hosted Docker/Railway needs ANTHROPIC_API_KEY.")
        elif provider == "anthropic" and not (source.get("ANTHROPIC_API_KEY") or "").strip():
            errors.append(f"{role} uses Anthropic Claude but ANTHROPIC_API_KEY is not configured for hosted mode.")

    return errors


def hosted_local_provider_endpoint_errors(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    role_providers = hosted_llm_role_providers(source)
    errors: list[str] = []
    local_provider_urls = {
        "lmstudio": source.get("LMSTUDIO_BASE_URL") or source.get("SPARK_LMSTUDIO_BASE_URL") or "",
        "ollama": source.get("OLLAMA_URL") or source.get("SPARK_OLLAMA_URL") or "",
    }
    for role, provider in role_providers.items():
        if provider not in local_provider_urls:
            continue
        url = local_provider_urls[provider]
        if not url:
            continue
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            errors.append(
                f"{role} uses {provider} at {url}; hosted Docker/Railway should use host.docker.internal or a reachable private provider URL."
            )
    return errors


def proc_status_fields(status_path: Path = Path("/proc/self/status")) -> dict[str, str]:
    fields: dict[str, str] = {}
    try:
        text = status_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return fields
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def linux_no_new_privileges_enabled(status_path: Path = Path("/proc/self/status")) -> bool | None:
    fields = proc_status_fields(status_path)
    if "NoNewPrivs" not in fields:
        return None
    return fields["NoNewPrivs"].split()[0] == "1"


def linux_effective_capabilities_dropped(status_path: Path = Path("/proc/self/status")) -> bool | None:
    fields = proc_status_fields(status_path)
    value = fields.get("CapEff")
    if value is None:
        return None
    try:
        return int(value.split()[0], 16) == 0
    except ValueError:
        return None


def linux_root_filesystem_read_only(mountinfo_path: Path = Path("/proc/self/mountinfo")) -> bool | None:
    if os.name == "nt":
        return None
    try:
        mountinfo = mountinfo_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    for line in mountinfo.splitlines():
        parts = line.split()
        if len(parts) >= 6 and decode_mountinfo_path(parts[4]) == "/":
            options = set(parts[5].split(","))
            return "ro" in options
    return None


def hosted_spawner_base_url() -> str:
    port = (
        os.environ.get("SPARK_SPAWNER_PORT")
        or os.environ.get("PORT")
        or os.environ.get("SPARK_PORT")
        or "3333"
    )
    return f"http://127.0.0.1:{str(port).strip()}"


def hosted_deep_mission_smoke(timeout_seconds: int = 90) -> dict[str, Any]:
    ui_key = os.environ.get("SPARK_UI_API_KEY") or ""
    bridge_key = os.environ.get("SPARK_BRIDGE_API_KEY") or ""
    if not ui_key or not bridge_key:
        return {
            "name": "hosted_deep_mission_smoke",
            "ok": False,
            "required": True,
            "detail": "Hosted mission smoke needs SPARK_UI_API_KEY and SPARK_BRIDGE_API_KEY.",
            "repair": "Set hosted API keys, restart Spark Live, then rerun spark verify --hosted --deep.",
        }

    base_url = hosted_spawner_base_url().rstrip("/")
    marker = "SPARK_HOSTED_DEEP_OK"
    request_id = f"hosted-deep-{int(time.time())}"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-spawner-ui-key": ui_key,
        "x-api-key": bridge_key,
    }
    payload = {
        "goal": f"Reply with exactly: {marker}",
        "providers": [os.environ.get("SPARK_LLM_PROVIDER") or "codex"],
        "promptMode": "simple",
        "requestId": request_id,
    }
    try:
        request = urllib.request.Request(
            f"{base_url}/api/spark/run",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            start_payload = json.loads(response.read().decode("utf-8") or "{}")
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "name": "hosted_deep_mission_smoke",
            "ok": False,
            "required": True,
            "detail": f"Could not start protected hosted mission smoke: {exc}",
            "repair": "Run spark live status and spark logs spawner-ui --lines 80.",
        }

    mission_id = str(start_payload.get("missionId") or start_payload.get("id") or request_id)
    deadline = time.time() + timeout_seconds
    last_detail = "Mission was accepted; waiting for board result."
    while time.time() < deadline:
        try:
            request = urllib.request.Request(f"{base_url}/api/mission-control/board", headers=headers, method="GET")
            with urllib.request.urlopen(request, timeout=10) as response:
                board_text = response.read().decode("utf-8")
            if marker in board_text:
                return {
                    "name": "hosted_deep_mission_smoke",
                    "ok": True,
                    "required": True,
                    "detail": f"Protected mission path completed with {marker} ({mission_id}).",
                    "repair": "",
                }
            if mission_id in board_text:
                last_detail = f"Mission {mission_id} is visible on the board but has not emitted {marker} yet."
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last_detail = f"Board poll failed while waiting for {mission_id}: {exc}"
        time.sleep(3)

    return {
        "name": "hosted_deep_mission_smoke",
        "ok": False,
        "required": True,
        "detail": last_detail,
        "repair": "Check spark logs spawner-ui --lines 80 and verify the hosted mission provider has working credentials.",
    }


def collect_hosted_security_payload(*, deep: bool = False) -> dict[str, Any]:
    role_providers = hosted_llm_role_providers()
    provider_errors = hosted_headless_provider_errors()
    local_provider_endpoint_errors = hosted_local_provider_endpoint_errors()
    allowed_hosts = [host.strip() for host in (os.environ.get("SPARK_ALLOWED_HOSTS") or "").split(",") if host.strip()]
    allowed_host_errors = hosted_allowed_host_errors(allowed_hosts)
    ui_key = os.environ.get("SPARK_UI_API_KEY") or ""
    bridge_key = os.environ.get("SPARK_BRIDGE_API_KEY") or ""
    hosted_key_errors = hosted_api_key_strength_errors(ui_key, bridge_key)
    secret_file_errors = hosted_secret_file_permission_errors()
    sensitive_mount_errors = hosted_sensitive_mount_errors()
    cloud_credential_errors = hosted_cloud_credential_env_errors()
    spawner_host = (os.environ.get("SPARK_SPAWNER_HOST") or "").strip()
    public_bind = spawner_host in {"0.0.0.0", "::"} or bool(allowed_hosts)
    runtime_uids = tracked_runtime_uids()
    uid = current_uid()
    runtime_non_root_ok = all(runtime_uid != 0 for runtime_uid in runtime_uids) if runtime_uids else (uid is None or uid != 0)
    runtime_uid_detail = (
        f"Spark tracked runtime process uid(s): {', '.join(str(runtime_uid) for runtime_uid in sorted(set(runtime_uids)))}."
        if runtime_uids
        else (
            f"Spark runtime is not root (uid={uid})."
            if uid is not None and uid != 0
            else "This platform does not expose a Unix uid; non-root runtime is checked inside Linux/Docker hosted environments."
            if uid is None
            else "Spark runtime appears to be running as root; hosted containers should drop to the spark user after volume prep."
        )
    )
    spark_home_value = os.environ.get("SPARK_HOME", str(SPARK_HOME))
    spark_home = Path(spark_home_value).expanduser().resolve()
    spark_home_ref = public_local_path_ref(spark_home)
    if spark_home_ref.startswith("<local-path>/"):
        spark_home_ref = "<spark-home>"
    no_new_privileges = linux_no_new_privileges_enabled()
    capabilities_dropped = linux_effective_capabilities_dropped()
    root_read_only = linux_root_filesystem_read_only()
    hosted_runtime = bool(os.environ.get("SPARK_LIVE_CONTAINER") or os.environ.get("RAILWAY_ENVIRONMENT"))
    strict_pins_required = hosted_runtime or public_bind

    checks = [
        {
            "name": "non_root_runtime",
            "ok": runtime_non_root_ok,
            "required": True,
            "detail": runtime_uid_detail,
            "repair": "Use the Spark Live Docker entrypoint or run as a non-root user after chowning the state volume.",
        },
        {
            "name": "no_docker_socket",
            "ok": not docker_socket_present(),
            "required": True,
            "detail": (
                "Docker socket is not mounted."
                if not docker_socket_present()
                else "Docker socket is visible inside the container; this is effectively host-root access."
            ),
            "repair": "Remove any /var/run/docker.sock mount before running hosted Spark.",
        },
        {
            "name": "container_no_new_privileges",
            "ok": no_new_privileges is not False,
            "required": False,
            "detail": (
                "Linux no-new-privileges is enabled."
                if no_new_privileges is True
                else "Linux no-new-privileges is disabled; this weakens container escape resistance."
                if no_new_privileges is False
                else "This platform does not expose Linux NoNewPrivs."
            ),
            "repair": "Run hosted Spark with `--security-opt no-new-privileges` or the equivalent platform policy.",
        },
        {
            "name": "container_capabilities",
            "ok": capabilities_dropped is not False,
            "required": False,
            "detail": (
                "Linux effective capabilities are dropped."
                if capabilities_dropped is True
                else "Linux effective capabilities are still present; drop all capabilities where the host allows it."
                if capabilities_dropped is False
                else "This platform does not expose Linux capability status."
            ),
            "repair": "Run hosted Spark with `--cap-drop ALL` where supported.",
        },
        {
            "name": "container_read_only_root",
            "ok": root_read_only is not False,
            "required": False,
            "detail": (
                "Container root filesystem is read-only."
                if root_read_only is True
                else "Container root filesystem is writable; prefer a read-only root filesystem plus writable Spark state volume."
                if root_read_only is False
                else "This platform does not expose root filesystem mount mode."
            ),
            "repair": "Use Docker `--read-only` plus tmpfs for /tmp and a dedicated writable Spark state volume where supported.",
        },
        {
            "name": "no_sensitive_mounts",
            "ok": not sensitive_mount_errors,
            "required": True,
            "detail": (
                "; ".join(sensitive_mount_errors)
                if sensitive_mount_errors
                else "No obvious SSH, browser profile, cloud credential, root, or Docker config mounts are visible."
            ),
            "repair": "Mount only the Spark state volume, normally /data/spark. Do not mount host homes, SSH keys, cloud config, browser profiles, or /.",
        },
        {
            "name": "no_cloud_admin_credentials",
            "ok": not cloud_credential_errors,
            "required": True,
            "detail": (
                "; ".join(cloud_credential_errors)
                if cloud_credential_errors
                else "No cloud/admin deployment tokens are present in the hosted Spark runtime env."
            ),
            "repair": "Remove cloud deployment credentials from the Spark Live service env; keep only Spark/LLM/Telegram secrets needed by the agent.",
        },
        {
            "name": "spark_home_boundary",
            "ok": hosted_spark_home_is_safe(spark_home_value),
            "required": True,
            "detail": f"Spark home is isolated at {spark_home_ref}.",
            "repair": "Set SPARK_HOME to an isolated volume such as /data/spark.",
        },
        {
            "name": "allowed_hosts",
            "ok": ((not public_bind) or bool(allowed_hosts)) and not allowed_host_errors,
            "required": True,
            "detail": (
                "; ".join(allowed_host_errors)
                if allowed_host_errors
                else (
                    f"Spawner public host allowlist: {', '.join(allowed_hosts)}."
                    if allowed_hosts
                    else "Spawner is not publicly bound, so SPARK_ALLOWED_HOSTS is not required for this context."
                )
            ),
            "repair": "Set SPARK_ALLOWED_HOSTS to the exact hosted domain, with no scheme, path, wildcard, or loopback host.",
        },
        {
            "name": "hosted_api_keys",
            "ok": (not public_bind) or not hosted_key_errors,
            "required": True,
            "detail": (
                "; ".join(hosted_key_errors)
                if hosted_key_errors and public_bind
                else (
                "Hosted UI and bridge API keys are configured; Spark Live maps the bridge key to control/event routes at startup."
                    if bool(bridge_key) and bool(ui_key)
                    else "Spawner is not publicly bound, so hosted UI/bridge API keys are not required for this context."
                    if not public_bind
                    else "Hosted/public Spawner needs SPARK_UI_API_KEY plus SPARK_BRIDGE_API_KEY."
                )
            ),
            "repair": "Set different random SPARK_UI_API_KEY and SPARK_BRIDGE_API_KEY platform secrets, at least 24 characters each.",
        },
        {
            "name": "headless_provider",
            "ok": not provider_errors and not local_provider_endpoint_errors,
            "required": True,
            "detail": (
                "Hosted LLM roles are API/local-network compatible: "
                + ", ".join(f"{role}={provider or 'not set'}" for role, provider in role_providers.items())
                if not provider_errors and not local_provider_endpoint_errors
                else "; ".join(provider_errors + local_provider_endpoint_errors)
            ),
            "repair": "Use API-key providers for hosted Spark: zai, kimi, openrouter, huggingface, minimax, openai, codex with OPENAI_API_KEY, anthropic with ANTHROPIC_API_KEY, or a reachable LM Studio/Ollama endpoint.",
        },
        {
            "name": "strict_runtime_pins",
            "ok": (not strict_pins_required) or runtime_guard_is_strict(),
            "required": True,
            "detail": (
                "Strict runtime pins are enforced for hosted/public Spark."
                if runtime_guard_is_strict()
                else "Strict runtime pins are not required for this local-only context."
                if not strict_pins_required
                else "Hosted/public Spark should block dirty or off-pin runtime modules."
            ),
            "repair": "Set SPARK_STRICT_RUNTIME_PINS=1 for hosted Docker/Railway deployments.",
        },
        {
            "name": "hosted_secret_file_permissions",
            "ok": not secret_file_errors,
            "required": True,
            "detail": (
                "; ".join(secret_file_errors)
                if secret_file_errors
                else (
                    "Hosted secret files are private on this platform."
                    if os.name != "nt"
                    else "Windows hosted secret file permissions are handled by the OS/keychain path."
                )
            ),
            "repair": "Run `chmod 600 <spark-home>/config/secrets.local.json` or rerun `spark setup` so Spark can harden the secret file.",
        },
    ]

    secret_surface = collect_secret_surface_payload()
    checks.append(
        {
            "name": "secret_surface",
            "ok": bool(secret_surface.get("ok")),
            "required": True,
            "detail": str(secret_surface.get("detail") or ""),
            "repair": str(secret_surface.get("repair") or "spark fix secrets"),
            "findings": secret_surface.get("findings", []),
        }
    )

    if deep:
        checks.append(hosted_deep_mission_smoke())

    return {
        "ok": all(bool(check["ok"]) for check in checks if check.get("required", True)),
        "summary": "Spark hosted security verification",
        "checks": checks,
        "next_commands": [
            "spark live status",
            "spark verify --onboarding",
            "spark providers test --role chat",
            "spark verify --hosted --deep",
            "spark logs spawner-ui --lines 80",
        ],
    }


def onboarding_checklist() -> list[str]:
    return [
        "Open your Spark bot in Telegram.",
        "If Telegram asks for a start code, send /start.",
        "Choose what Spark can do when asked. For first builds, choose Level 4 so Mission Control can inspect and build in local workspaces.",
        "Run spark providers test --role chat and confirm the selected LLM replies with PING_OK.",
        "Send /diagnose in Telegram and confirm Telegram, LLM, memory, and Spawner look OK.",
        "Send a normal message, then try a tiny build with /run say exactly OK.",
        "When you are ready, ask Spark how it can improve for your workflows.",
        "If anything is quiet or confusing, run spark fix telegram.",
    ]


def first_run_smoke_telegram_script() -> list[str]:
    return [
        "/start",
        "/access 4",
        "/diagnose",
        "/remember I like concise warm replies",
        "/recall concise warm replies",
        '/run Build a tiny static HTML page called Spark first-run smoke. It should have one file, index.html, with a dark Mission Control panel, a green "Spark Live OK" status, and the text "Telegram to Spawner relay worked". Do not add package files, do not install dependencies, and keep it simple enough to finish fast.',
        "/board",
    ]


def collect_first_run_smoke_payload(*, deep: bool = True) -> dict[str, Any]:
    payload = collect_verify_payload(deep=deep)
    payload = dict(payload)
    payload["summary"] = "Spark first-run smoke"
    payload["deep"] = deep
    payload["onboarding_checklist"] = onboarding_checklist()
    payload["telegram_script"] = first_run_smoke_telegram_script()
    payload["success_criteria"] = [
        "Telegram /diagnose reports Telegram, providers, memory, and Spawner as ready.",
        "The /remember then /recall probe returns the saved preference.",
        "The tiny static /run sends progress, completion, and a preview link.",
        "The generated workspace contains index.html with Spark Live OK and Telegram-to-Spawner relay text.",
        "The generated workspace does not require package.json, node_modules, or dependency installation.",
    ]
    payload["next_commands"] = [
        "spark smoke first-run",
        "spark providers test --role chat",
        "spark logs spark-telegram-bot --lines 80",
        "spark logs spawner-ui --lines 80",
        "spark fix telegram",
        "spark fix spawner",
    ]
    return payload


def print_first_run_smoke_payload(payload: dict[str, Any]) -> None:
    print(payload["summary"])
    print(f"Bundle: {payload.get('bundle', 'telegram-starter')}")
    print(f"Mode: {'deep local checks' if payload.get('deep') else 'quick local checks'}")
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
    print("Telegram first-run script:")
    for item in payload["telegram_script"]:
        print(f"  {item}")
    print("")
    print("Pass criteria:")
    for item in payload["success_criteria"]:
        print(f"  - {item}")
    print("")
    print("Repair commands:")
    for command in payload["next_commands"][1:]:
        print(f"  {command}")


def cmd_smoke(args: argparse.Namespace) -> int:
    command = getattr(args, "smoke_command", None)
    if command != "first-run":
        raise SystemExit("Choose a smoke command, for example: spark smoke first-run")

    payload = collect_first_run_smoke_payload(deep=not bool(getattr(args, "quick", False)))
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload["ok"] else 1
    print_first_run_smoke_payload(payload)
    return 0 if payload["ok"] else 1


def print_hosted_security_payload(payload: dict[str, Any]) -> None:
    print(payload["summary"])
    for check in payload["checks"]:
        marker = "[OK]" if check["ok"] else "[FIX]"
        print(f"{marker} {check['name']}: {check['detail']}")
        if not check["ok"] and check.get("repair"):
            print(f"      {check['repair']}")


def cmd_verify(args: argparse.Namespace) -> int:
    if getattr(args, "registry_pins", False):
        payload = collect_registry_pin_drift_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print(payload["summary"])
        for check in payload["checks"]:
            marker = "[OK]" if check["ok"] else "[FIX]"
            print(f"{marker} {check['name']}: {check['detail']}")
            print(f"      pinned: {check['pinned_commit']}")
            if check.get("remote_head"):
                print(f"      remote: {check['remote_head']}")
        return 0 if payload["ok"] else 1

    if getattr(args, "provenance", False):
        payload = collect_module_provenance_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print(payload["summary"])
        print(f"Mode: {payload['mode']}")
        for check in payload["checks"]:
            marker = "[OK]" if check["ok"] else "[FIX]"
            print(f"{marker} {check['name']}: {check['detail']}")
            for warning in check.get("warnings", []):
                print(f"      warning: {warning}")
        return 0 if payload["ok"] else 1

    if getattr(args, "installers", False) or getattr(args, "hosted_installers", False):
        payload = collect_installer_integrity_payload(hosted=bool(getattr(args, "hosted_installers", False)))
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print(payload["summary"])
        for check in payload["checks"]:
            marker = "[OK]" if check["ok"] else "[FIX]"
            print(f"{marker} {check['name']}: {check['detail']}")
            if not check["ok"] and check.get("expected_sha256"):
                print(f"      expected: {check['expected_sha256']}")
                print(f"      actual:   {check['actual_sha256']}")
        return 0 if payload["ok"] else 1

    if getattr(args, "sandboxes", False):
        payload = collect_sandbox_verify_payload()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print(payload["summary"])
        for check in payload["checks"]:
            marker = "[OK]" if check["ok"] else "[WARN]" if check.get("level") == "warning" else "[FIX]"
            print(f"{marker} {check['name']}: {check['detail']}")
            if not check["ok"] and check.get("repair"):
                print(f"      {check['repair']}")
        return 0 if payload["ok"] else 1

    if getattr(args, "specialization_loop", False):
        payload = collect_specialization_loop_payload(proof=bool(getattr(args, "proof", False)))
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print(payload["summary"])
        for check in payload["checks"]:
            marker = "[OK]" if check["ok"] else "[FIX]"
            print(f"{marker} {check['name']}: {check['detail']}")
            if not check["ok"] and check.get("repair"):
                print(f"      {check['repair']}")
        proofs = payload.get("status_proofs")
        if isinstance(proofs, list) and proofs:
            print("")
            print("Status proof:")
            for proof in proofs:
                if not isinstance(proof, dict):
                    continue
                marker = "[OK]" if proof.get("ok") else "[FIX]"
                print(f"{marker} {proof.get('path_key', 'path')}: {proof.get('detail')}")
                issues = proof.get("issues")
                if issues:
                    print(f"      issues: {', '.join(str(issue) for issue in issues)}")
        safe_next_moves = payload.get("safe_next_moves")
        if isinstance(safe_next_moves, list) and safe_next_moves:
            print("")
            print("Safe next moves:")
            for move in safe_next_moves:
                print(f"  - {move}")
        print("")
        print("Useful commands:")
        for command in payload["next_commands"]:
            print(f"  {command}")
        if payload.get("boundary"):
            print("")
            print("Boundary:")
            print(f"  {payload['boundary']}")
        return 0 if payload["ok"] else 1

    if getattr(args, "hosted", False):
        payload = collect_hosted_security_payload(deep=bool(getattr(args, "deep", False)))
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1
        print_hosted_security_payload(payload)
        return 0 if payload["ok"] else 1

    onboarding = bool(getattr(args, "onboarding", False))
    payload = collect_verify_payload(deep=bool(getattr(args, "deep", False) or onboarding))
    if onboarding:
        payload["summary"] = "Spark onboarding verification"
        payload["onboarding_checklist"] = onboarding_checklist()
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
    if onboarding:
        print("")
        print("Start in Telegram:")
        for index, item in enumerate(onboarding_checklist(), start=1):
            print(f"  {index}. {item}")
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


def resolve_exact_stop_module_names(target: str | None, installed_modules: dict[str, Module], tracked_pids: dict[str, Any]) -> list[str]:
    if not tracked_pids:
        return []
    if target is None:
        return resolve_stop_module_names(target, installed_modules, tracked_pids)
    requested_names = expand_targets(target, installed_modules, include_all=True)
    ordered_names = [
        module.name
        for module in topologically_sort_modules(
            {name: installed_modules[name] for name in requested_names if name in installed_modules}
        )
    ]
    expanded_ordered_names: list[str] = []
    for name in reversed(ordered_names):
        if name == "spark-telegram-bot":
            tracked_bot_keys = tracked_process_keys_for_module(tracked_pids, "spark-telegram-bot")
            expanded_ordered_names.extend(tracked_bot_keys or [name])
        else:
            expanded_ordered_names.append(name)
    extra_names = [name for name in requested_names if name not in installed_modules]
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
    ready_check_override: str | None = None,
) -> tuple[bool, str]:
    ready_check = ready_check_override or module.ready_check
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
                    result = run_runtime_command(
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
                request = urllib.request.Request(ready_check, headers=ready_check_headers(ready_check))
                with urllib.request.urlopen(request, timeout=2) as response:
                    if 200 <= int(response.status) < 400:
                        return True, ready_check
                    last_error = f"ready check returned HTTP {response.status}"
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = str(error)
        else:
            result = run_runtime_command(
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


def ready_check_headers(ready_check: str) -> dict[str, str]:
    if not ready_check.startswith(("http://", "https://")):
        return {}
    parsed = urllib.parse.urlparse(ready_check)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return {}
    key = os.environ.get("SPARK_UI_API_KEY") or os.environ.get("SPARK_BRIDGE_API_KEY")
    if not key:
        return {}
    return {"x-spawner-ui-key": key, "x-api-key": key}


def direct_node_package_script_argv(command: str, cwd: Path) -> list[str] | None:
    parts = split_single_argv_command(command, "Runtime command")
    if len(parts) < 3 or parts[0].lower() != "npm" or parts[1] != "run":
        return None
    script_name = parts[2]
    remainder = parts[3:]
    extra_args: list[str] = []
    if remainder:
        if remainder[0] != "--":
            return None
        extra_args = remainder[1:]

    package_json = cwd / "package.json"
    if not package_json.exists():
        return None
    try:
        package_data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    scripts = package_data.get("scripts")
    script = scripts.get(script_name) if isinstance(scripts, dict) else None
    if not isinstance(script, str) or not script.strip():
        return None
    try:
        script_parts = split_single_argv_command(script, "Package script")
    except SystemExit:
        return None
    if not script_parts:
        return None

    node = resolve_runtime_binary("node")
    if not node:
        return None
    script_executable = script_parts[0].lower()
    if script_executable == "node":
        return [node, *script_parts[1:], *extra_args]
    if script_executable == "vite":
        vite_bin = cwd / "node_modules" / "vite" / "bin" / "vite.js"
        if vite_bin.exists():
            return [node, str(vite_bin), *script_parts[1:], *extra_args]
    if script_executable == "ts-node":
        ts_node_bin = cwd / "node_modules" / "ts-node" / "dist" / "bin.js"
        if ts_node_bin.exists():
            return [node, str(ts_node_bin), *script_parts[1:], *extra_args]
    return None


def user_safe_startup_detail(detail: str) -> str:
    if "TELEGRAM_RELAY_SECRET" in detail or "telegram.relay_secret" in detail:
        return "Spark could not finish connecting Telegram. Run `spark setup telegram-starter --resume`, then `spark start telegram-starter`."
    return detail


def format_start_warning(module: Module, detail: str, process: subprocess.Popen[Any], profile: str | None = None) -> str:
    detail = user_safe_startup_detail(detail)
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
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                return int(line)
            except ValueError:
                continue
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
    if module.name == "spawner-ui":
        raw_port = module_runtime_env(module, profile).get("SPARK_SPAWNER_PORT")
        if raw_port:
            try:
                return [int(raw_port)]
            except (TypeError, ValueError):
                return []
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


def replace_or_append_flag(argv: list[str], flag: str, value: str) -> list[str]:
    updated = list(argv)
    try:
        index = updated.index(flag)
    except ValueError:
        updated.extend([flag, value])
        return updated
    if index + 1 < len(updated):
        updated[index + 1] = value
    else:
        updated.append(value)
    return updated


def module_runtime_command_argv(module: Module, command: str, cwd: Path, env: dict[str, str]) -> list[str]:
    argv = direct_node_package_script_argv(command, cwd) or runtime_command_argv(command)
    if module.name != "spawner-ui":
        return argv
    bind_host = (env.get("SPARK_SPAWNER_HOST") or "").strip()
    bind_port = (env.get("SPARK_SPAWNER_PORT") or "").strip()
    if bind_host:
        argv = replace_or_append_flag(argv, "--host", bind_host)
    if bind_port:
        argv = replace_or_append_flag(argv, "--port", bind_port)
    return argv


def spawner_should_use_liveness_endpoint(env: dict[str, str]) -> bool:
    return bool(
        running_as_hosted_context()
        or env.get("SPARK_LIVE_CONTAINER")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("SPARK_ALLOWED_HOSTS")
        or str(env.get("SPARK_HOSTED_PRIVATE_PREVIEW") or "").strip().lower() in {"1", "true", "yes", "on"}
    )


def spawner_runtime_port(module: Module, env: dict[str, str]) -> str:
    bind_port = (env.get("SPARK_SPAWNER_PORT") or os.environ.get("SPARK_SPAWNER_PORT") or "").strip()
    if bind_port:
        return bind_port
    ready_check = module.ready_check or ""
    if ready_check.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(ready_check)
        if parsed.port:
            return str(parsed.port)
    return "3333"


def spawner_runtime_health_url(module: Module, env: dict[str, str]) -> str:
    path = "/api/health/live" if spawner_should_use_liveness_endpoint(env) else "/api/providers"
    return f"http://127.0.0.1:{spawner_runtime_port(module, env)}{path}"


def module_runtime_ready_check(module: Module, env: dict[str, str]) -> str:
    if module.name == "spawner-ui":
        bind_port = (env.get("SPARK_SPAWNER_PORT") or "").strip()
        if bind_port:
            return spawner_runtime_health_url(module, env)
    return module.ready_check


def expected_runtime_process_names(installed_names: set[str], setup_state: dict[str, Any]) -> list[str]:
    names: list[str] = []
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    has_profiles = isinstance(profiles, dict) and bool(profiles)
    external_telegram = telegram_ingress_is_external(setup_state if isinstance(setup_state, dict) else {})
    if "spark-telegram-bot" in installed_names and not has_profiles and not external_telegram:
        names.append("spark-telegram-bot")
    if "spawner-ui" in installed_names:
        names.append("spawner-ui")
    if isinstance(profiles, dict) and "spark-telegram-bot" in installed_names and not external_telegram:
        for profile, profile_state in sorted(profiles.items()):
            if isinstance(profile_state, dict) and telegram_profile_should_autostart(profile_state):
                process_key = module_process_key("spark-telegram-bot", str(profile))
                if process_key not in names:
                    names.append(process_key)
    return names


def telegram_profile_runtime_status(setup_state: dict[str, Any], pids: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = setup_state.get("telegram_profiles")
    if not isinstance(profiles, dict):
        return []
    statuses: list[dict[str, Any]] = []
    primary_profile = primary_telegram_profile(setup_state)
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
                "primary": normalized == primary_profile,
                "autostart": telegram_profile_should_autostart(profile_state),
                "log_path": public_local_path_ref(module_log_path("spark-telegram-bot", normalized)),
            }
        )
    return statuses


def terminate_same_user_listener_on_port(port: int, *, label: str) -> str | None:
    if port <= 0:
        return None
    listener_pid = listening_pid_for_tcp_port(port)
    if not listener_pid or not pid_is_running(listener_pid):
        return None
    listener_uid = proc_uid_for_pid(listener_pid)
    if listener_uid is not None and listener_uid != os.getuid():
        return f"{label} port {port} is already held by pid {listener_pid} owned by another user."
    try:
        os.kill(listener_pid, signal.SIGTERM)
    except OSError as exc:
        return f"{label} port {port} is already held by pid {listener_pid}, and Spark could not stop it: {exc}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not pid_is_running(listener_pid):
            return f"Stopped stale {label} listener on port {port} (pid {listener_pid})."
        time.sleep(0.1)
    try:
        os.kill(listener_pid, signal.SIGKILL)
    except OSError:
        pass
    active_listener = listening_pid_for_tcp_port(port)
    if active_listener and active_listener == listener_pid:
        return f"{label} port {port} is still held by stale pid {listener_pid}."
    return f"Force-stopped stale {label} listener on port {port} (pid {listener_pid})."


def start_module(module: Module, *, allow_boot_warnings: bool = False, profile: str | None = None) -> bool:
    command = module.run_command
    if not command:
        return True
    enforce_module_trust_scan(module, module.name)
    require_write_allowed(module.path, safe_root=spark_write_safe_root(), subject=f"{module.name} module root")
    if module.name == "spark-telegram-bot":
        validate_telegram_profile_token_identity(profile)

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
    argv = module_runtime_command_argv(module, command, module.path, subprocess_env)
    ready_check = module_runtime_ready_check(module, subprocess_env)
    relay_port = 0
    if module.name == "spark-telegram-bot":
        relay_port_raw = (subprocess_env.get("TELEGRAM_RELAY_PORT") or "").strip()
        try:
            relay_port = int(relay_port_raw or "0")
        except ValueError:
            relay_port = 0
    popen_kwargs: dict[str, Any] = {
        "cwd": str(module.path),
        "shell": False,
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
        if module.name == "spark-telegram-bot" and relay_port:
            stale_listener_note = terminate_same_user_listener_on_port(relay_port, label=display_name)
            if stale_listener_note:
                print(stale_listener_note)
                append_process_log(module.name, stale_listener_note, profile=profile)

        log_handle = log_path.open("a", encoding="utf-8")
        popen_kwargs["stdout"] = log_handle
        try:
            process = subprocess.Popen(argv, **popen_kwargs)
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
            "ready_check": ready_check,
        }
        save_pids(pids)
    print(f"Started {display_name} (pid {process.pid})")
    ready, detail = wait_for_ready_check(module, process=process, profile=profile, ready_check_override=ready_check)
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
    ensure_runtime_telegram_relay_secret(target_modules)
    if not emit_runtime_supply_chain_guard(target_modules, args):
        return 1
    requested_names = set(expand_targets(args.target, modules, include_all=True))
    for module in target_modules:
        if not module.run_command:
            if module.name in requested_names:
                print(f"Skipping {module.name}: no run.default command declared")
            continue
        if module.name == "spark-telegram-bot" and profile == DEFAULT_TELEGRAM_PROFILE:
            for telegram_profile in telegram_profiles_to_start_by_default():
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
        if getattr(args, "cascade", False):
            target_names = resolve_stop_module_names(args.target, installed_modules, pids)
        else:
            target_names = resolve_exact_stop_module_names(args.target, installed_modules, pids)
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
            if not emit_runtime_supply_chain_guard([module], args):
                return 1
            start_code = 0
            if not start_module(
                module,
                allow_boot_warnings=getattr(args, "allow_boot_warnings", False),
                profile=profile,
            ):
                start_code = 1
            return start_code or stop_code
    restart_modules = (
        resolve_restart_modules(args.target, installed_modules, load_pids())
        if getattr(args, "cascade", False)
        else resolve_start_modules(args.target, installed_modules)
    )
    if not emit_runtime_supply_chain_guard(restart_modules, args):
        return 1
    stop_code = cmd_stop(args)
    start_code = 0
    for module in restart_modules:
        if not module.run_command:
            print(f"Skipping {module.name}: no run.default command declared")
            continue
        if module.name == "spark-telegram-bot":
            for telegram_profile in telegram_profiles_to_start_by_default():
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
        if isinstance(profile_state, dict) and telegram_profile_should_autostart(profile_state)
    )


def manual_telegram_profiles() -> list[str]:
    autostart_profiles = set(autostart_telegram_profiles())
    return [profile for profile in configured_telegram_profiles() if profile not in autostart_profiles]


def configured_telegram_profiles() -> list[str]:
    setup_state = load_json(CONFIG_PATH, {})
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    if not isinstance(profiles, dict):
        return []
    return sorted(
        normalize_telegram_profile(profile)
        for profile, profile_state in profiles.items()
        if isinstance(profile_state, dict)
    )


def telegram_profiles_to_start_by_default() -> list[str]:
    profiles = autostart_telegram_profiles()
    if profiles:
        return profiles
    if configured_telegram_profiles():
        return []
    return [DEFAULT_TELEGRAM_PROFILE]


def autostart_should_include_telegram_profiles(target: str) -> bool:
    return target in {"telegram-starter", "spark-telegram-bot"}


def validate_autostart_target(target: str) -> str:
    value = str(target or "").strip()
    if not AUTOSTART_TARGET_PATTERN.fullmatch(value):
        raise SystemExit("Autostart target must match ^[a-z0-9-]+$.")
    return value


def spark_action_shell_command(action: str, target: str, *, profile: str | None = None) -> str:
    target = validate_autostart_target(target)
    args = spark_invocation_args() + [action]
    if action == "start":
        args.append("--allow-boot-warnings")
    if profile and normalize_telegram_profile(profile) != DEFAULT_TELEGRAM_PROFILE:
        args.extend(["--profile", normalize_telegram_profile(profile)])
    args.append(target)
    return shell_join(args)


def autostart_shell_commands(action: str, target: str) -> list[str]:
    target = validate_autostart_target(target)
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


def render_linux_xdg_autostart_entry(*, start_command: str) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Spark Telegram Agent
Comment=Start Spark when this desktop session logs in
Exec=/bin/sh -lc {shlex.quote(start_command)}
Terminal=false
X-GNOME-Autostart-enabled=true
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


def linux_xdg_autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{AUTOSTART_SERVICE_NAME}.desktop"


def systemctl_command(scope: str, *args: str) -> list[str]:
    if scope == "system":
        return ["systemctl", *args]
    return ["systemctl", "--user", *args]


def macos_autostart_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{AUTOSTART_LAUNCHD_LABEL}.plist"


def running_under_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return "microsoft" in release or "wsl" in release


def available_wsl_distros() -> list[str]:
    result = run_autostart_helper(["wsl.exe", "-l", "-q"])
    if result.returncode != 0:
        return []
    output = (result.stdout or "").replace("\x00", "")
    distros: list[str] = []
    for line in output.splitlines():
        distro = line.strip().strip("*").strip()
        if distro and distro.lower() != "windows subsystem for linux distributions:":
            distros.append(distro)
    return distros


def wsl_distro_name() -> str | None:
    configured = os.environ.get("WSL_DISTRO_NAME", "").strip()
    if configured:
        return configured
    distros = available_wsl_distros()
    if len(distros) == 1:
        return distros[0]
    return None


def windows_path_to_wsl_path(path_text: str) -> Path:
    value = path_text.strip().strip('"')
    match = re.match(r"^([A-Za-z]):\\(.*)$", value)
    if match:
        drive = match.group(1).lower()
        tail = match.group(2).replace("\\", "/")
        return Path(f"/mnt/{drive}/{tail}")
    return Path(value)


def wsl_windows_appdata_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return windows_path_to_wsl_path(appdata)
    command = ["cmd.exe", "/d", "/c", "echo", "%APPDATA%"]
    result = run_autostart_helper(command)
    if result.returncode != 0:
        print_helper_failure(command, result)
        return None
    output = (result.stdout or "").strip().splitlines()
    return windows_path_to_wsl_path(output[-1]) if output else None


def wsl_windows_startup_script_path() -> Path | None:
    appdata = wsl_windows_appdata_path()
    if appdata is None:
        return None
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{AUTOSTART_SERVICE_NAME}.vbs"


def render_wsl_windows_startup_script(start_command: str, *, distro_name: str | None = None) -> str:
    resolved_distro = distro_name or wsl_distro_name()
    if not resolved_distro:
        raise ValueError("Could not determine the WSL distro name for Windows-login autostart.")
    command = subprocess.list2cmdline(
        [
            "wsl.exe",
            "-d",
            resolved_distro,
            "--cd",
            str(Path.home()),
            "--exec",
            "sh",
            "-lc",
            start_command,
        ]
    )
    return "Set shell = CreateObject(\"WScript.Shell\")\r\n" f"shell.Run {vbs_string(command)}, 0, False\r\n"


def windows_startup_script_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{AUTOSTART_SERVICE_NAME}.vbs"


def windows_startup_legacy_cmd_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{AUTOSTART_SERVICE_NAME}.cmd"


def windows_run_key_path() -> str:
    return r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"


def windows_run_key_command(startup_path: Path) -> str:
    return f'wscript.exe "{startup_path}"'


def vbs_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def write_windows_startup_script(path: Path, start_command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    hidden_command = f"%ComSpec% /d /s /c {start_command}"
    path.write_text(
        "Set shell = CreateObject(\"WScript.Shell\")\r\n"
        f"shell.CurrentDirectory = {vbs_string(str(SPARK_HOME))}\r\n"
        f"shell.Environment(\"PROCESS\")(\"SPARK_HOME\") = {vbs_string(str(SPARK_HOME))}\r\n"
        f"shell.Run {vbs_string(hidden_command)}, 0, False\r\n",
        encoding="ascii",
    )


def windows_cmd_c(command: str) -> str:
    return "cmd.exe /c " + subprocess.list2cmdline([command])


def run_autostart_helper(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def print_helper_failure(command: list[str], result: subprocess.CompletedProcess[str]) -> None:
    detail = (result.stderr or result.stdout or "").strip()
    print(f"Autostart helper failed ({shell_join(command)}): {detail or f'exit {result.returncode}'}")


def install_windows_fallback_autostart(start_command: str) -> tuple[Path, bool]:
    startup_path = windows_startup_script_path()
    write_windows_startup_script(startup_path, start_command)
    legacy_cmd_path = windows_startup_legacy_cmd_path()
    if legacy_cmd_path.exists():
        legacy_cmd_path.unlink()
    run_key_command = [
        "reg",
        "add",
        windows_run_key_path(),
        "/v",
        AUTOSTART_WINDOWS_TASK_NAME,
        "/t",
        "REG_SZ",
        "/d",
        windows_run_key_command(startup_path),
        "/f",
    ]
    result = run_autostart_helper(run_key_command)
    if result.returncode != 0:
        print_helper_failure(run_key_command, result)
        return startup_path, False
    return startup_path, True


def windows_run_key_installed() -> bool:
    result = run_autostart_helper(
        ["reg", "query", windows_run_key_path(), "/v", AUTOSTART_WINDOWS_TASK_NAME]
    )
    return result.returncode == 0


def install_wsl_windows_login_bridge(start_command: str) -> tuple[Path | None, bool]:
    startup_path = wsl_windows_startup_script_path()
    if startup_path is None:
        return None, False
    distro_name = wsl_distro_name()
    if not distro_name:
        return startup_path, False
    startup_path.parent.mkdir(parents=True, exist_ok=True)
    startup_path.write_text(render_wsl_windows_startup_script(start_command, distro_name=distro_name), encoding="ascii")
    return startup_path, True


def autostart_file_audit(path: Path, *, expected_command: str, expected_home: Path | None = None) -> dict[str, Any]:
    audit: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "readable": False,
        "current_command": None,
        "current_home": None,
        "parent_private": None,
        "warnings": [],
    }
    if not path.exists():
        return audit
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        audit["warnings"].append(f"could not read autostart file: {exc}")
        return audit
    audit["readable"] = True
    audit["current_command"] = expected_command in content
    home = expected_home or SPARK_HOME
    audit["current_home"] = str(home) in content or expected_command in content
    try:
        parent_mode = stat.S_IMODE(path.parent.stat().st_mode)
    except OSError as exc:
        audit["warnings"].append(f"could not inspect parent directory permissions: {exc}")
    else:
        audit["parent_private"] = (parent_mode & 0o022) == 0
        if not audit["parent_private"]:
            audit["warnings"].append(
                f"parent directory is group/world writable ({oct(parent_mode)}): {path.parent}"
            )
    if audit["current_command"] is False:
        audit["warnings"].append("autostart command does not match the current Spark startup command")
    if audit["current_home"] is False:
        audit["warnings"].append("autostart file does not point at the current Spark home")
    return audit


def print_autostart_file_audit(label: str, path: Path, *, expected_command: str) -> list[str]:
    audit = autostart_file_audit(path, expected_command=expected_command)
    if not audit["exists"]:
        return []
    if audit["readable"]:
        print(f"{label} current command: " + ("yes" if audit["current_command"] else "no"))
        print(f"{label} current Spark home: " + ("yes" if audit["current_home"] else "no"))
        if audit["parent_private"] is not None:
            print(f"{label} parent private: " + ("yes" if audit["parent_private"] else "no"))
    else:
        print(f"{label} readable: no")
    warnings = [str(item) for item in audit.get("warnings", [])]
    for warning in warnings:
        print(f"{label} warning: {warning}")
    if warnings:
        print("Repair: spark autostart on --now")
    return warnings


def cmd_autostart_install(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    target = validate_autostart_target(args.target or "telegram-starter")
    start_command = autostart_shell_command("start", target)
    stop_command = autostart_shell_command("stop", target)
    failures = 0

    if sys.platform.startswith("linux") and running_under_wsl():
        startup_path, installed = install_wsl_windows_login_bridge(start_command)
        if installed and startup_path is not None:
            print(f"Installed WSL Windows-login fallback: {startup_path}")
        else:
            failures += 1
            if startup_path is None:
                print("Could not install WSL Windows-login fallback because Windows APPDATA was unavailable.")
            else:
                print("Could not install WSL Windows-login fallback because the WSL distro name could not be determined.")
                print("Run from inside the target WSL distro, or set WSL_DISTRO_NAME and try again.")
        if args.now:
            now_command = ["sh", "-lc", start_command]
            result = run_autostart_helper(now_command)
            if result.returncode != 0:
                failures += 1
                print_helper_failure(now_command, result)
                print(f"Manual fallback for this session: {start_command}")
        print("Spark will start at Windows login with: " + start_command)
        return 1 if failures else 0

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
        if scope == "user":
            xdg_path = linux_xdg_autostart_path()
            xdg_path.parent.mkdir(parents=True, exist_ok=True)
            xdg_path.write_text(
                render_linux_xdg_autostart_entry(start_command=start_command),
                encoding="utf-8",
            )
            xdg_path.chmod(0o600)
            print(f"Installed Linux desktop autostart fallback: {xdg_path}")
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
            startup_path, run_key_installed = install_windows_fallback_autostart(start_command)
            print(f"Installed Windows Startup fallback: {startup_path}")
            print("Installed Windows Run-key fallback: " + ("yes" if run_key_installed else "no"))
            if not run_key_installed:
                failures += 1
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
    if sys.platform.startswith("linux") and running_under_wsl():
        startup_path = wsl_windows_startup_script_path()
        if startup_path is not None and startup_path.exists():
            startup_path.unlink()
            print(f"Removed WSL Windows-login fallback: {startup_path}")
        return 0

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
        xdg_path = linux_xdg_autostart_path()
        if xdg_path.exists():
            xdg_path.unlink()
            print(f"Removed Linux desktop autostart fallback: {xdg_path}")
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
        legacy_cmd_path = windows_startup_legacy_cmd_path()
        if legacy_cmd_path.exists():
            legacy_cmd_path.unlink()
            print(f"Removed legacy Windows Startup fallback: {legacy_cmd_path}")
            failures = 0 if failures else failures
        run_key_command = ["reg", "delete", windows_run_key_path(), "/v", AUTOSTART_WINDOWS_TASK_NAME, "/F"]
        result = run_autostart_helper(run_key_command)
        if result.returncode == 0:
            print(f"Removed Windows Run-key fallback: {AUTOSTART_WINDOWS_TASK_NAME}")
            failures = 0 if failures else failures
        return 1 if failures else 0

    raise SystemExit(f"Autostart is not supported on this platform yet: {sys.platform}")


def cmd_autostart_profile(args: argparse.Namespace) -> int:
    profile = normalize_telegram_profile(getattr(args, "profile", None))
    enabled = getattr(args, "state", "") == "on"
    setup_state = load_json(CONFIG_PATH, {})
    profiles = setup_state.get("telegram_profiles") if isinstance(setup_state, dict) else None
    if not isinstance(profiles, dict) or profile not in profiles or not isinstance(profiles.get(profile), dict):
        print(f"Telegram profile is not configured: {profile}")
        print("Configure it first with:")
        print(f"  spark setup --profile {profile} --bot-token <BOTFATHER_TOKEN>")
        return 1
    profiles[profile]["autostart"] = enabled
    save_json(CONFIG_PATH, setup_state)
    state_text = "will start when Spark Live starts" if enabled else "will stay manual at login"
    print(f"Telegram profile {profile}: {state_text}.")
    print("Refresh OS startup with:")
    print("  spark autostart on --now")
    return 0


def cmd_autostart_status(_: argparse.Namespace) -> int:
    profiles = autostart_telegram_profiles()
    profile_text = ", ".join(profiles) if profiles else "none"
    configured = configured_telegram_profiles()
    configured_text = ", ".join(configured) if configured else "none"
    manual = manual_telegram_profiles()
    manual_text = ", ".join(manual) if manual else "none"
    expected_start_command = autostart_shell_command("start", "telegram-starter")
    if sys.platform.startswith("linux") and running_under_wsl():
        startup_path = wsl_windows_startup_script_path()
        installed = bool(startup_path and startup_path.exists())
        print(f"WSL Windows-login fallback: {startup_path or 'unavailable'}")
        print("Installed: " + ("yes" if installed else "no"))
        print(f"Telegram profiles configured: {configured_text}")
        print(f"Telegram profiles in autostart: {profile_text}")
        print(f"Telegram profiles manual/off: {manual_text}")
        if startup_path is not None:
            print_autostart_file_audit("WSL Windows-login fallback", startup_path, expected_command=expected_start_command)
        return 0

    if sys.platform.startswith("linux"):
        scope = linux_autostart_scope()
        service_path = linux_autostart_path(scope)
        xdg_path = linux_xdg_autostart_path()
        service_installed = service_path.exists()
        xdg_installed = xdg_path.exists()
        print(f"Linux systemd {scope} service: {service_path}")
        print("Installed: " + ("yes" if service_installed or xdg_installed else "no"))
        print("Systemd service installed: " + ("yes" if service_installed else "no"))
        print(f"Linux desktop fallback: {xdg_path}")
        print("Linux desktop fallback installed: " + ("yes" if xdg_installed else "no"))
        print(f"Telegram profiles configured: {configured_text}")
        print(f"Telegram profiles in autostart: {profile_text}")
        print(f"Telegram profiles manual/off: {manual_text}")
        if service_installed:
            result = run_autostart_helper(systemctl_command(scope, "is-enabled", service_path.name))
            enabled = (result.stdout or result.stderr or "").strip() or f"exit {result.returncode}"
            print(f"Enabled: {enabled}")
            print_autostart_file_audit("Systemd service", service_path, expected_command=expected_start_command)
        if xdg_installed:
            print_autostart_file_audit("Linux desktop fallback", xdg_path, expected_command=expected_start_command)
        return 0
    if sys.platform == "darwin":
        plist_path = macos_autostart_path()
        print(f"macOS LaunchAgent: {plist_path}")
        installed = plist_path.exists()
        print("Installed: " + ("yes" if installed else "no"))
        print(f"Telegram profiles configured: {configured_text}")
        print(f"Telegram profiles in autostart: {profile_text}")
        print(f"Telegram profiles manual/off: {manual_text}")
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
            print_autostart_file_audit("LaunchAgent", plist_path, expected_command=expected_start_command)
        return 0
    if sys.platform == "win32":
        result = run_autostart_helper(["schtasks", "/Query", "/TN", AUTOSTART_WINDOWS_TASK_NAME])
        print(f"Windows task: {AUTOSTART_WINDOWS_TASK_NAME}")
        task_installed = result.returncode == 0
        startup_path = windows_startup_script_path()
        startup_installed = startup_path.exists()
        run_key_installed = windows_run_key_installed()
        print("Installed: " + ("yes" if task_installed or startup_installed or run_key_installed else "no"))
        print("Task installed: " + ("yes" if task_installed else "no"))
        print(f"Startup fallback: {startup_path}")
        print("Startup fallback installed: " + ("yes" if startup_installed else "no"))
        print("Run-key fallback installed: " + ("yes" if run_key_installed else "no"))
        print(f"Telegram profiles configured: {configured_text}")
        print(f"Telegram profiles in autostart: {profile_text}")
        print(f"Telegram profiles manual/off: {manual_text}")
        if startup_installed:
            print_autostart_file_audit("Startup fallback", startup_path, expected_command=expected_start_command)
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
        value = read_secret_interactive(
            f"  Paste value for {args.secret_id} (typing is masked; type @clipboard to use copied value): "
        )
    else:
        value = sys.stdin.read().strip()
    value = resolve_secret_input(value)
    if not value:
        raise SystemExit(f"Refusing to store empty value for {args.secret_id}.")
    backend = store_secret(args.secret_id, value, preferred=args.backend)
    # This prints the secret label and backend, never the stored value.
    # codeql[py/clear-text-logging-sensitive-data]
    print(f"Stored {args.secret_id} in {backend}.")
    return 0


def cmd_secrets_get(args: argparse.Namespace) -> int:
    value = fetch_secret(args.secret_id)
    if value is None:
        raise SystemExit(f"No value stored for {args.secret_id}.")
    if args.reveal:
        # `spark secrets get --reveal` is an explicit local operator command.
        # codeql[py/clear-text-logging-sensitive-data]
        print(value)
    else:
        masked = value[:4] + "..." + value[-2:] if len(value) > 6 else "***"
        # The value is masked by default; the printed id is a label.
        # codeql[py/clear-text-logging-sensitive-data]
        print(f"{args.secret_id} -> {masked} (pass --reveal to print full value)")
    return 0


def cmd_secrets_delete(args: argparse.Namespace) -> int:
    if delete_secret(args.secret_id):
        # This prints only the secret label after deletion.
        # codeql[py/clear-text-logging-sensitive-data]
        print(f"Deleted {args.secret_id}.")
        return 0
    # This prints only the secret label.
    # codeql[py/clear-text-logging-sensitive-data]
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
    if getattr(args, "continue_update", False):
        print("Continuing update; modules already at their registry pins will be skipped naturally.")
    dirty = dirty_update_modules(modules)
    if dirty and getattr(args, "stash_local_runtime", False):
        print("Stashing local runtime edits before update:")
        stash_failures: list[tuple[Module, str]] = []
        for module, _detail in dirty:
            ok, stash_detail = stash_module_local_changes(module)
            print(f"  - {module.name}: {'ok' if ok else 'failed'} - {stash_detail}")
            if not ok:
                stash_failures.append((module, stash_detail))
        if stash_failures:
            print("")
            print("Update stopped before touching running processes because stashing failed.")
            for module, detail in stash_failures:
                print(f"  - {module.name}: {detail}")
            return 1
        dirty = []
    if dirty and not getattr(args, "skip_dirty", False):
        print_dirty_update_preflight(dirty)
        return 1
    skipped_dirty = {module.name: detail for module, detail in dirty} if getattr(args, "skip_dirty", False) else {}
    if skipped_dirty:
        print("Skipping dirty modules before touching services:")
        for module_name in skipped_dirty:
            module_path = next((module.path for module in modules if module.name == module_name), "")
            print(f"  - {module_name}: inspect with `git -C \"{module_path}\" status --short`")
        modules = [module for module in modules if module.name not in skipped_dirty]
        if not modules:
            print("No clean modules left to update.")
            return 0
    updated_modules: list[str] = []
    stopped_processes: list[str] = []
    for module in modules:
        if module_is_git_managed(module.path):
            ok, detail = update_module_source(module)
            print(f"git update {module.name}: {'ok' if ok else 'failed'} - {detail}")
            if not ok:
                print(f"Update stopped before touching running processes for {module.name}.")
                print(
                    "Repair: inspect local changes with "
                    f"`git -C \"{module.path}\" status --short`, then commit/stash them "
                    "or reinstall once the module source is clean. Then run `spark update --continue`."
                )
                return 1
            module = load_module(module.path)
        with pid_file_lock():
            pids = load_pids()
            process_keys = tracked_process_keys_for_module(pids, module.name)
        for process_key in process_keys:
            with pid_file_lock():
                record = load_pids().get(process_key, {})
            pid = int(record.get("pid", 0)) if isinstance(record, dict) else 0
            if pid and pid_is_running(pid):
                print(f"Stopping {process_key} before update so install commands can replace locked files.")
                stopped_processes.append(process_key)
            stop_tracked_process_key(process_key)
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
        updated_modules.append(module.name)
    refreshed = refresh_telegram_builder_runtime_refs(load_json(REGISTRY_PATH, {}))
    if refreshed:
        print(f"Refreshed Builder runtime refs in {len(refreshed)} generated Telegram config file(s).")
    print("")
    print("Update summary:")
    print(f"  Updated: {', '.join(updated_modules) if updated_modules else 'none'}")
    if skipped_dirty:
        print(f"  Skipped dirty: {', '.join(skipped_dirty)}")
    else:
        print("  Skipped dirty: none")
    if stopped_processes:
        print(f"  Stopped runtime process(es): {', '.join(stopped_processes)}")
        if update_should_restart_live(args, stopped_processes):
            print("  Autostart is enabled, so Spark will restart the live stack now.")
            restart_code = cmd_live(argparse.Namespace(live_command="restart"))
            status_code = print_update_live_status_summary()
            if restart_code != 0 or status_code != 0:
                return restart_code or status_code
        else:
            print("  Next: run `spark live restart`, then `spark live status`.")
    else:
        print("  Runtime processes stopped: none")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    if getattr(args, "all", False) and args.target:
        raise SystemExit("Use either a target or --all, not both.")
    if getattr(args, "purge_home", False) and not getattr(args, "yes", False):
        raise SystemExit("Refusing to purge Spark home without --yes.")

    ensure_state_dirs()
    modules = resolve_installed_target_modules(args.target)
    if modules:
        installed_modules = resolve_installed_modules()
        blockers = detect_uninstall_blockers(modules, installed_modules)
        if blockers and not args.force:
            raise SystemExit("Cannot uninstall because other installed modules depend on it: " + "; ".join(blockers))

    failures = 0
    if getattr(args, "remove_autostart", False):
        failures += cmd_autostart_uninstall(argparse.Namespace())

    if not modules:
        print("No installed Spark modules recorded.")
        if getattr(args, "remove_user_path", False):
            removed = remove_spark_bin_from_windows_user_path()
            print("Removed Spark bin from Windows user PATH." if removed else "Spark bin was not present in Windows user PATH.")
        if getattr(args, "purge_home", False):
            removed_home = purge_spark_home()
            print(f"Removed Spark home: {SPARK_HOME}" if removed_home else f"Spark home was not present: {SPARK_HOME}")
        return 1 if failures else 0
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
    if getattr(args, "remove_user_path", False):
        removed = remove_spark_bin_from_windows_user_path()
        print("Removed Spark bin from Windows user PATH." if removed else "Spark bin was not present in Windows user PATH.")
    if getattr(args, "purge_home", False):
        removed_home = purge_spark_home()
        print(f"Removed Spark home: {SPARK_HOME}" if removed_home else f"Spark home was not present: {SPARK_HOME}")
    return 1 if failures else 0


def onboarding_guide_payload() -> dict[str, Any]:
    return {
        "title": "Spark starter guide",
        "goal": "Install Spark, choose how it thinks, connect Telegram, then start chatting and building with your agent.",
        "operating_systems": ["Windows PowerShell/CMD", "macOS Terminal", "Linux shell", "WSL Ubuntu shell"],
        "starter_bundle": [
            {
                "module": "spark-telegram-bot",
                "role": "Telegram front door. Owns the bot token, runs long polling, and receives your chat commands.",
            },
            {
                "module": "spark-intelligence-builder",
                "role": "Runtime router. Handles identity, memory bridge, provider routing, and domain-chip activation.",
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
            {
                "module": "spark-voice-comms",
                "role": "Optional in telegram-voice-starter. Handles speech I/O hooks for transcription, voice setup, and spoken replies.",
            },
        ],
        "setup": {
            "interactive": "spark setup",
            "autostart_default": "spark setup installs login autostart by default; use spark setup --no-autostart to keep Spark manual.",
            "botfather": [
                "Open Telegram and message @BotFather.",
                "Send /newbot and follow BotFather's prompts.",
                "Copy the token BotFather gives you.",
                "Message @userinfobot and copy your numeric Telegram id.",
                "Run spark setup again with the bot token and admin id if you did not provide them during install.",
            ],
            "llm_roles": [
                {"role": "default", "use": "One provider for Agent and Mission. This is the easiest first setup."},
                {"role": "agent", "use": "Telegram chat, runtime reasoning, memory synthesis, and recall."},
                {"role": "mission", "use": "Spawner/Mission Control builds, research, coding work, and longer tracked missions."},
            ],
            "llm_examples": [
                "spark setup",
                "spark setup --llm-provider codex --codex-model gpt-5.5",
                "spark setup --llm-provider anthropic",
                "spark setup --llm-provider zai --zai-api-key <ZAI_API_KEY>",
                "spark setup --llm-provider kimi --kimi-api-key <KIMI_API_KEY>",
                "spark setup --llm-provider openrouter --openrouter-api-key <OPENROUTER_API_KEY> --openrouter-model <MODEL>",
                "spark setup --llm-provider huggingface --huggingface-api-key <HF_TOKEN> --huggingface-model <MODEL>",
                "spark setup --llm-provider minimax --minimax-api-key <MINIMAX_API_KEY>",
                "spark setup --llm-provider ollama --ollama-url http://localhost:11434 --ollama-model <MODEL>",
                "spark setup --llm-provider openai --openai-api-key <OPENAI_API_KEY> --openai-model gpt-5.5",
                "spark setup --with-voice --elevenlabs-api-key @clipboard",
                "spark setup --agent-llm-provider zai --mission-llm-provider codex",
                "spark setup --chat-llm-provider openai --builder-llm-provider openai --memory-llm-provider ollama --mission-llm-provider minimax",
            ],
            "llm_auth_note": "The easiest path is `spark setup` and the guided picker. You can use one provider for Agent and Mission, or split them during setup. `--agent-llm-provider` sets Telegram chat, runtime reasoning, memory, and recall together. `--mission-llm-provider` sets Spawner/Mission Control build work separately. OpenAI Codex or ChatGPT users should choose OpenAI Codex after `codex login`. Anthropic Claude users should choose Anthropic Claude after installing Claude Code and checking `claude -p \"hello\"`. Z.AI GLM, Kimi/Moonshot, OpenRouter, MiniMax, Hugging Face, and OpenAI API use API keys. Ollama and LM Studio are local.",
        },
        "access": {
            "default": "Spark setup automatically creates a Level 4 safe workspace and points Mission Control at it.",
            "plain_language": "Level 4 means Spark can work in its Spark workspace. It does not mean whole-computer access.",
            "stronger_local": "Docker is the first stronger local sandbox when it is installed and running.",
            "cloud": "Modal is for disposable cloud/GPU work and starts with no Spark secrets or project files by default.",
            "remote": "SSH is for a machine the user owns and controls; it is not a sandbox by itself.",
            "level5": "Level 5 whole-computer mode is explicit opt-in with spark access setup --level 5 --enable-high-agency.",
            "commands": ["spark access guide", "spark access setup", "spark sandbox docker doctor", "spark sandbox docker smoke"],
        },
        "quick_start": [
            {"title": "Choose how Spark thinks", "steps": [
                "Run: spark setup",
                "Choose one provider for Agent and Mission unless you already know you want a split.",
                "OpenAI Codex, Claude Code, Ollama, and LM Studio can use local sign-in or local services; API providers ask for a key.",
                "If paste is awkward, copy the value first and type @clipboard when Spark asks.",
            ]},
            {"title": "Connect Telegram", "steps": [
                "Open Telegram and message @BotFather.",
                "Send /newbot and copy the token BotFather gives you.",
                "Message @userinfobot and copy your numeric Telegram id.",
                "Paste Telegram values only into local Spark setup, never into a website.",
            ]},
            {"title": "Turn Spark on", "steps": [
                "Run: spark live start",
                "Run: spark live status",
                "Run: spark providers test --role chat",
                "To start Spark automatically when this computer logs in, run: spark autostart on --now.",
                "If login startup seems stale or missing, run: spark fix autostart.",
            ]},
            {"title": "Start chatting and building", "steps": [
                "Open your Spark bot in Telegram.",
                "If Telegram asks for a start code, send /start.",
                "Choose what Spark can do when asked. For first builds, choose Level 4 so Mission Control can inspect and build in local workspaces.",
                "Use a lower level only when you want chat, memory, diagnostics, public research, or remote missions without local files.",
                "Send /diagnose and make sure Telegram, LLM, memory, and Spawner look OK.",
                "Send a normal message, then try a tiny build with /run say exactly OK.",
                "When you are ready, ask Spark how it can improve for your workflows; your agent will guide the next step.",
            ]},
        ],
        "start": [
            "spark autostart on --now",
            "Open your Spark bot in Telegram; if it asks for a start code, send /start.",
            "Choose what Spark can do when asked. For Mission Control builds on this computer, send /access 4.",
            "Use a lower access level only when you want Spark kept away from local folders.",
            "Send /diagnose in Telegram.",
            "spark verify --onboarding",
        ],
        "multi_bot_profiles": [
            "Use named profiles when you want one or more Telegram bots on the same Spark install.",
            "Each profile gets its own bot token, local relay port, pid, and log file.",
            "Profiles still share the same local Builder, memory, LLM roles, and Spawner unless you intentionally split those later.",
            "Example: spark setup --profile qa-bot --bot-token @clipboard --admin-telegram-ids <YOUR_TELEGRAM_ID>",
            "Then run: spark start spark-telegram-bot --profile qa-bot",
        ],
        "access_levels": [
            {"level": "1", "about": "Chat, memory, recall, and diagnostics. No Spawner builds."},
            {"level": "2", "about": "Requested remote missions. Spark only starts Spawner after you clearly ask."},
            {"level": "3", "about": "Public links, docs, and GitHub research, plus requested missions. Does not inspect local folders."},
            {"level": "4", "about": "Recommended for builders. Spark works inside its safe workspace by default, with Mission Control builds, debugging, repo inspection, and deeper missions. Destructive actions still need explicit approval."},
        ],
        "telegram_commands": [
            { "command": "/start", "use": "Show the basic command surface." },
            { "command": "/myid", "use": "Show your numeric Telegram id for admin setup." },
            { "command": "/diagnose", "use": "Check Telegram, LLM, memory, Spark runtime, and mission relay health." },
            { "command": "/remember <note>", "use": "Save a memory through Spark's memory path when available." },
            { "command": "/recall <query>", "use": "Search your Spark memory when available." },
            { "command": "/run <goal>", "use": "Create a Spawner mission from Telegram." },
            { "command": "/board", "use": "Show current mission board/status." },
            { "command": "/access <1|2|3|4>", "use": "Adjust what Spark may do in this Telegram chat." },
            { "command": "/mission status <id>", "use": "Inspect a mission." },
            { "command": "normal message", "use": "Ask Spark to answer through the configured LLM provider." },
        ],
        "operator_commands": [
            { "command": "spark status", "use": "Human-readable health check and repair hints." },
            { "command": "spark live status", "use": "Check whether Spark Live is running quietly in the background." },
            { "command": "spark verify", "use": "Launch-readiness proof for modules, LLM roles, Telegram long polling, Builder memory, Spawner relay, and running processes." },
            { "command": "spark verify --onboarding", "use": "First-user checklist for Telegram, allowed actions, memory, and a tiny Spawner mission." },
            { "command": "spark smoke first-run", "use": "Guided first-run proof: local readiness checks, Telegram script, memory probe, tiny static build, and preview pass criteria." },
            { "command": "spark fix telegram", "use": "Targeted quiet-bot repair checklist: token, admin ids, memory bridge, LLM roles, process, and logs." },
            { "command": "spark fix autostart", "use": "Targeted login-startup repair checklist: installed hooks, stale paths, permissions, and Telegram profile selection." },
            { "command": "spark fix spawner", "use": "Targeted repair checklist when /run, Kanban, Canvas, preview links, or Mission Control is not reachable." },
            { "command": "spark providers test --role chat", "use": "Send a tiny PING_OK probe through the selected chat LLM." },
            { "command": "spark security audit", "use": "Check secrets, provider wiring, Telegram long polling, and runtime health." },
            { "command": "spark support bundle", "use": "Create a local redacted support archive. Nothing uploads automatically." },
            { "command": "spark doctor --json", "use": "Structured diagnostics for agents and support." },
            { "command": "spark os compile", "use": "Compile a redacted local Spark OS system map, authority view, capability catalog, trace index, memory movement index, and gaps report." },
            { "command": "spark os authority", "use": "Inspect redacted access, sandbox, browser approval, and publication authority contracts." },
            { "command": "spark os capabilities", "use": "Inspect redacted capability cards for Labs and Swarm surfaces." },
            { "command": "spark os trace", "use": "Inspect redacted trace health, repair gaps, and cross-system join shape." },
            { "command": "spark os memory", "use": "Inspect redacted memory movement counts and authority buckets." },
            { "command": "spark doctor llm \"<problem>\" --save-report", "use": "Ask the user's configured LLM for a redacted repair plan." },
            { "command": "spark autostart on --now", "use": "Turn on the Telegram agent now and every time this computer logs in." },
            { "command": "spark autostart status", "use": "Check whether login autostart is installed and points at the current Spark home." },
            { "command": "spark autostart profile <profile> off", "use": "Keep one Telegram bot profile manual while the rest of Spark can still start at login." },
            { "command": "spark autostart off", "use": "Remove OS login autostart while leaving Spark installed." },
            { "command": "spark onboard", "use": "Resume setup, start Spark, and wait for the first Telegram /start bridge." },
            { "command": "spark logs spark-telegram-bot", "use": "Read Telegram gateway logs." },
            { "command": "spark logs spark-telegram-bot --profile qa-bot", "use": "Read logs for a named Telegram bot profile." },
            { "command": "spark logs spawner-ui", "use": "Read mission-control logs." },
            { "command": "spark secrets list", "use": "Confirm configured secret ids without printing secret values." },
            { "command": "spark setup", "use": "Rerun onboarding safely when changing bot, admin ids, or LLM provider." },
            { "command": "spark setup --with-voice", "use": "Install and attach Spark Voice Comms, then finish voice setup from Telegram with /voice self-test." },
        ],
        "command_reference": [
            { "command": "spark list", "use": "List local Spark modules with manifests." },
            { "command": "spark install <target>", "use": "Install a module by registry name, local path, or git URL." },
            { "command": "spark setup [bundle]", "use": "Configure a starter bundle; installs login autostart by default unless --no-autostart is passed." },
            { "command": "spark setup --with-voice", "use": "Alias for the Telegram voice starter bundle; optional ElevenLabs key can be passed with --elevenlabs-api-key." },
            { "command": "spark onboard [bundle]", "use": "Resume setup or restart onboarding until the Telegram first-message bridge is confirmed." },
            { "command": "spark status [--json]", "use": "Run module healthchecks with repair hints." },
            { "command": "spark os compile [--json]", "use": "Write read-only Spark OS system-map, authority, capability, trace, memory movement, and gap reports under ~/.spark/state/system-map." },
            { "command": "spark os authority [--json]", "use": "Inspect metadata-only authority levels, sandbox lanes, guarded actions, browser approvals, and publication gates." },
            { "command": "spark os capabilities [--json]", "use": "Inspect metadata-only capability cards and promotion blockers." },
            { "command": "spark os trace [--json]", "use": "Inspect metadata-only trace health, missing refs, high-severity open events, and cross-system joins." },
            { "command": "spark os memory [--json]", "use": "Inspect metadata-only memory movement, authority buckets, record counts, and KB artifact counts." },
            { "command": "spark doctor [--json]", "use": "Run diagnostic status output." },
            { "command": "spark doctor llm \"<problem>\"", "use": "Ask the configured LLM for a redacted repair plan." },
            { "command": "spark support bundle", "use": "Create a local redacted support bundle." },
            { "command": "spark verify [--onboarding|--deep|--installers|--sandboxes]", "use": "Verify launch-critical wiring, onboarding, deeper runtime checks, installer integrity, or optional Docker/SSH/Modal sandbox readiness." },
            { "command": "spark smoke first-run [--quick|--json]", "use": "Check first-run readiness and print the exact Telegram smoke script for Mission Control." },
            { "command": "spark fix <target>", "use": "Run targeted repair guidance for telegram, secrets, spawner, providers, memory, live, update, or autostart." },
            { "command": "spark access status|guide|setup|disable-level5", "use": "Prepare, explain, and verify Spark workspace access, optional sandbox lanes, and explicit Level 5 guardrail state." },
            { "command": "spark providers list|status|test|recommend", "use": "Inspect, test, and choose LLM provider wiring." },
            { "command": "spark recommend llms|providers", "use": "Recommend Spark setup choices." },
            { "command": "spark security audit", "use": "Audit local security posture." },
            { "command": "spark sandbox docker|ssh|modal", "use": "Run Docker doctor/no-secret smoke, manage SSH targets and host-key trust, and run explicit no-secret Modal smoke." },
            { "command": "spark approval classify -- <command>", "use": "Classify whether a command requires approval." },
            { "command": "spark telegram connect [profile]", "use": "Connect or rotate a Telegram bot profile token." },
            { "command": "spark update [target]", "use": "Refresh installed modules from current source paths." },
            { "command": "spark uninstall [target]", "use": "Remove installed modules and generated config." },
            { "command": "spark start [target]", "use": "Start modules or starter bundles." },
            { "command": "spark stop [target]", "use": "Stop tracked Spark processes." },
            { "command": "spark restart [target]", "use": "Restart modules or starter bundles." },
            { "command": "spark live status|start|run|restart|stop|logs|verify", "use": "Control and inspect Spark Live." },
            { "command": "spark autostart install|on|uninstall|off|profile|status", "use": "Control OS login startup and per-profile autostart." },
            { "command": "spark guide [--advanced|--json]", "use": "Show onboarding, advanced guidance, and this command reference." },
            { "command": "spark init <name>", "use": "Scaffold a new Spark module." },
            { "command": "spark search [query]", "use": "Search the local blessed registry." },
            { "command": "spark config get|set|unset|list", "use": "Read or write user config at ~/.spark/config/config.json." },
            { "command": "spark secrets list|set|get|delete", "use": "Manage stored secrets without exposing values by default." },
            { "command": "spark logs <module>", "use": "Show process logs for an installed module." },
        ],
        "troubleshooting": [
            "Bot receives no messages: make sure only one polling process is running, then restart spark-telegram-bot.",
            "Second bot receives no messages: run spark restart spark-telegram-bot --profile <profile> and check spark logs spark-telegram-bot --profile <profile>.",
            "Bot is quiet and you are not sure why: run spark fix telegram.",
            "Bot says admin only: send /myid, add that numeric id during spark setup, then restart.",
            "LLM does not answer: rerun spark setup to choose your Agent and Mission provider, then run spark status.",
            "Fresh install feels incomplete: run spark smoke first-run and follow the first [FIX] line or Telegram script step.",
            "Login startup is stale or confusing: run spark fix autostart, then spark autostart on --now if needed.",
            "/run, Kanban, Canvas, or preview links fail: run spark fix spawner, then check spark logs spawner-ui.",
            "Spark says it cannot inspect this workspace: send /access 4 so Mission Control can inspect and build in local folders on this computer.",
            "Memory does not work: run spark status and repair Spark runtime/domain-chip-memory hints first.",
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
    access = payload.get("access") if isinstance(payload.get("access"), dict) else {}
    if access:
        print("Safe access")
        print(f"   {access['default']}")
        print(f"   {access['plain_language']}")
        print(f"   {access['stronger_local']}")
        print("")
    for index, section in enumerate(payload["quick_start"], start=1):
        print(f"{index}. {section['title']}")
        for step in section["steps"]:
            print(f"   - {step}")
        print("")
    print("What you can say in Telegram")
    for item in payload["telegram_commands"]:
        if item["command"] in {"/start", "/myid", "/diagnose", "/remember <note>", "/recall <query>", "/run <goal>", "/board", "/access <1|2|3|4>"}:
            print(f"   {item['command']}: {item['use']}")
    print("")
    print("If something feels stuck")
    for item in payload["operator_commands"]:
        if item["command"] in {"spark live status", "spark verify --onboarding", "spark fix telegram", "spark fix spawner", "spark logs spark-telegram-bot", "spark logs spawner-ui"}:
            print(f"   {item['command']}: {item['use']}")
    print("   spark guide --advanced: Provider splits, multiple bots, allowed actions, modules, and support commands.")
    print("")
    if getattr(args, "advanced", False):
        print("Advanced setup")
        print("Provider control")
        for item in payload["setup"]["llm_roles"]:
            print(f"   - {item['role']}: {item['use']}")
        print(f"   {payload['setup']['llm_auth_note']}")
        for command in payload["setup"]["llm_examples"]:
            print(f"   {command}")
        print("")
        print("Run another Telegram bot")
        for item in payload["multi_bot_profiles"]:
            print(f"   - {item}")
        print("")
        print("What Spark can do")
        for item in payload["access_levels"]:
            print(f"   - {item['about']}")
        if access:
            print(f"   - {access['level5']}")
        print("   Change it in Telegram with /access <1|2|3|4>.")
        print("")
        print("How the modules work together")
        for item in payload["starter_bundle"]:
            print(f"   {item['module']}: {item['role']}")
        print("")
        print("Useful Spark CLI commands")
        for item in payload["operator_commands"]:
            print(f"   {item['command']}: {item['use']}")
        print("")
        print("Full command reference")
        for item in payload["command_reference"]:
            print(f"   {item['command']}: {item['use']}")
        print("")
        print("Troubleshooting")
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
    install_parser.add_argument("--skip-install-commands", action="store_true", help="Skip post-install commands (pip install, npm install) for this module")
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
    setup_parser.add_argument("--skip-install-commands", action="store_true", help="Skip install commands (pip install, npm install) for all bundle modules")
    setup_parser.add_argument(
        "--run-install-commands",
        action="store_true",
        help="Re-run dependency install commands for already installed modules",
    )
    setup_parser.add_argument("--skip-runtime-check", action="store_true", help="Skip [runtime].version constraint enforcement")
    setup_parser.add_argument("--trust", action="store_true", help="Approve running install commands and hooks for non-blessed bundle modules without prompting")
    setup_parser.add_argument("--resume", action="store_true", help="Skip install steps that succeeded on a prior attempt")
    setup_parser.add_argument(
        "--with-voice",
        action="store_true",
        help=f"Install and attach the voice chip by using the {TELEGRAM_VOICE_BUNDLE} bundle.",
    )
    setup_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip interactive preflight and secret prompts (require --secret for every required secret).",
    )
    setup_autostart_install_group = setup_parser.add_mutually_exclusive_group()
    setup_autostart_install_group.add_argument(
        "--autostart",
        dest="autostart",
        action="store_true",
        default=True,
        help="Install OS login autostart after setup (default)",
    )
    setup_autostart_install_group.add_argument(
        "--no-autostart",
        dest="autostart",
        action="store_false",
        help="Keep Spark manual after setup; you can enable it later with `spark autostart on --now`",
    )
    setup_parser.set_defaults(autostart=True)
    setup_start_group = setup_parser.add_mutually_exclusive_group()
    setup_start_group.add_argument(
        "--start-now",
        dest="start_now",
        action="store_true",
        help="Start Spark immediately after configuration (default)",
    )
    setup_start_group.add_argument(
        "--no-start-now",
        dest="start_now",
        action="store_false",
        help="Configure Spark without starting it after setup",
    )
    setup_parser.set_defaults(start_now=True)
    setup_wait_group = setup_parser.add_mutually_exclusive_group()
    setup_wait_group.add_argument(
        "--wait-first-message",
        dest="wait_first_message",
        action="store_true",
        default=True,
        help="After starting Spark interactively, wait for the first Telegram /start message (default for terminals)",
    )
    setup_wait_group.add_argument(
        "--no-wait-first-message",
        dest="wait_first_message",
        action="store_false",
        help="Do not wait for the first Telegram message after setup",
    )
    setup_parser.add_argument(
        "--wait-first-message-seconds",
        type=int,
        default=None,
        help="Override how long setup waits for the first Telegram /start message; default is 60 seconds for interactive terminals and 0 for non-interactive runs",
    )
    setup_parser.add_argument("--secret", action="append", help="Provide manifest secret values as key=value; use @clipboard, @env:NAME, or @file:path for secret input")
    setup_parser.add_argument("--bot-token", help="Telegram BotFather token, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--external-telegram-ingress", action="store_true", help=argparse.SUPPRESS)
    setup_parser.add_argument(
        "--skip-telegram-token-check",
        action="store_true",
        help="Skip live Telegram getMe token validation before saving a new bot token (offline/dev only)",
    )
    setup_parser.add_argument("--admin-telegram-ids")
    setup_parser.add_argument("--telegram-relay-secret")
    setup_parser.add_argument("--telegram-relay-port", type=int, help="Local Telegram mission relay port for a named profile")
    setup_parser.add_argument(
        "--profile",
        default=DEFAULT_TELEGRAM_PROFILE,
        help="Configure a named Telegram bot profile",
    )
    setup_autostart_group = setup_parser.add_mutually_exclusive_group()
    setup_autostart_group.add_argument(
        "--telegram-autostart",
        dest="telegram_autostart",
        action="store_true",
        default=None,
        help="Start this Telegram profile whenever Spark Live/autostart starts",
    )
    setup_autostart_group.add_argument(
        "--no-telegram-autostart",
        dest="telegram_autostart",
        action="store_false",
        help="Keep this Telegram profile manual; it will not start at login",
    )
    setup_parser.add_argument(
        "--memory-sidecars",
        type=parse_memory_sidecars,
        default=None,
        metavar="NAMES",
        help="Optional advanced memory sidecars to configure, comma-separated. Use graphiti-kuzu to enable the local Graphiti/Kuzu shadow lane; use none to disable.",
    )
    setup_parser.add_argument(
        "--graphiti-kuzu-db-path",
        help="Override the local Graphiti/Kuzu sidecar database path. Defaults to Builder home sidecars/graphiti/kuzu.",
    )
    setup_parser.add_argument("--spawner-ui-url", default="http://127.0.0.1:3333")
    setup_parser.add_argument("--llm-provider", choices=LLM_PROVIDER_CHOICES, help="Default provider for Agent and Mission unless a role-specific provider is set")
    setup_parser.add_argument("--agent-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for the Spark Agent: chat, runtime reasoning, memory, and recall")
    setup_parser.add_argument("--chat-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for Telegram chat replies")
    setup_parser.add_argument("--builder-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Expert: provider for runtime reasoning and orchestration inside Agent")
    setup_parser.add_argument("--memory-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for memory synthesis and recall")
    setup_parser.add_argument("--mission-llm-provider", choices=LLM_PROVIDER_CHOICES, help="Provider for Mission: Spawner/Mission Control builds, research, coding, and longer tracked work")
    setup_parser.add_argument("--zai-api-key", help="Z.AI GLM coding endpoint API key, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--zai-base-url", default="https://api.z.ai/api/coding/paas/v4/")
    setup_parser.add_argument("--zai-model", default="glm-5.1")
    setup_parser.add_argument("--openai-api-key", help="OpenAI API key, @clipboard, @env:NAME, or @file:path; optional for local OpenAI-compatible servers")
    setup_parser.add_argument("--openai-base-url", default="https://api.openai.com/v1", help="OpenAI-compatible base URL, for example https://api.openai.com/v1 or http://localhost:1234/v1 for LM Studio")
    setup_parser.add_argument("--openai-model", default="gpt-5.5", help="OpenAI/OpenAI-compatible model name")
    setup_parser.add_argument("--anthropic-api-key", help="Anthropic Claude API key, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--anthropic-base-url", default="https://api.anthropic.com")
    setup_parser.add_argument("--anthropic-model", default="sonnet")
    setup_parser.add_argument("--openrouter-api-key", help="OpenRouter API key, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--openrouter-base-url", default="https://openrouter.ai/api/v1")
    setup_parser.add_argument("--openrouter-model", default="openai/gpt-5.5")
    setup_parser.add_argument("--kimi-api-key", help="Kimi/Moonshot API key, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--kimi-base-url", default="https://api.moonshot.ai/v1")
    setup_parser.add_argument("--kimi-model", default="kimi-k2.6")
    setup_parser.add_argument("--huggingface-api-key", help="Hugging Face token, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--huggingface-base-url", default="https://router.huggingface.co/v1")
    setup_parser.add_argument("--huggingface-model", default="google/gemma-4-26B-A4B-it:fastest")
    setup_parser.add_argument("--lmstudio-base-url", default="http://localhost:1234/v1")
    setup_parser.add_argument("--lmstudio-model", default="local-model")
    setup_parser.add_argument("--minimax-api-key", help="MiniMax API key, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--minimax-base-url", default="https://api.minimax.io/v1")
    setup_parser.add_argument("--minimax-model", default="MiniMax-M2.7")
    setup_parser.add_argument("--elevenlabs-api-key", help="Optional ElevenLabs API key for Spark voice, @clipboard, @env:NAME, or @file:path")
    setup_parser.add_argument("--ollama-url", default="http://localhost:11434")
    setup_parser.add_argument("--ollama-model", default="llama3.2:3b")
    setup_parser.add_argument("--codex-model", default="gpt-5.5")
    setup_parser.set_defaults(func=cmd_setup)

    onboard_parser = subparsers.add_parser("onboard", help="Resume setup, start Spark, and open the first Telegram chat")
    onboard_parser.add_argument("bundle", nargs="?", help="Bundle to onboard (default: pending setup bundle, configured bundle, or telegram-starter)")
    onboard_parser.add_argument("--non-interactive", action="store_true", help="Do not prompt while resuming setup")
    onboard_autostart_group = onboard_parser.add_mutually_exclusive_group()
    onboard_autostart_group.add_argument("--autostart", dest="autostart", action="store_true", default=True, help="Install or preserve login autostart while resuming setup")
    onboard_autostart_group.add_argument("--no-autostart", dest="autostart", action="store_false", help="Keep Spark manual while resuming setup")
    onboard_start_group = onboard_parser.add_mutually_exclusive_group()
    onboard_start_group.add_argument("--start-now", dest="start_now", action="store_true", default=True, help="Start Spark now (default)")
    onboard_start_group.add_argument("--no-start-now", dest="start_now", action="store_false", help="Show onboarding steps without starting Spark")
    onboard_wait_group = onboard_parser.add_mutually_exclusive_group()
    onboard_wait_group.add_argument("--wait-first-message", dest="wait_first_message", action="store_true", default=True, help="Wait for the first Telegram /start message when interactive")
    onboard_wait_group.add_argument("--no-wait-first-message", dest="wait_first_message", action="store_false", help="Do not wait for the first Telegram message")
    onboard_parser.add_argument("--wait-first-message-seconds", type=int, default=None, help="Override the first-message wait timeout")
    onboard_parser.set_defaults(func=cmd_onboard)

    os_parser = subparsers.add_parser("os", help="Inspect Spark as a local agent operating system")
    os_subparsers = os_parser.add_subparsers(dest="os_command", required=True)
    os_compile_parser = os_subparsers.add_parser("compile", help="Compile a read-only Spark OS system map")
    os_compile_parser.add_argument("--desktop", default=str(Path.home() / "Desktop"), help="Desktop root containing Spark repos")
    os_compile_parser.add_argument("--spark-home", default=str(SPARK_HOME), help="Spark home directory")
    os_compile_parser.add_argument("--registry", default=str(LOCAL_REGISTRY_PATH), help="spark-cli registry.json path")
    os_compile_parser.add_argument("--out", default=str(STATE_DIR / "system-map"), help="Output directory for generated reports")
    os_compile_parser.add_argument("--json", action="store_true", help="Emit a compact JSON summary after writing files")
    os_compile_parser.set_defaults(func=cmd_os_compile)
    os_capabilities_parser = os_subparsers.add_parser("capabilities", help="Inspect compiled Spark capability cards")
    os_capabilities_parser.add_argument("--desktop", default=str(Path.home() / "Desktop"), help="Desktop root containing Spark repos")
    os_capabilities_parser.add_argument("--spark-home", default=str(SPARK_HOME), help="Spark home directory")
    os_capabilities_parser.add_argument("--registry", default=str(LOCAL_REGISTRY_PATH), help="spark-cli registry.json path")
    os_capabilities_parser.add_argument("--json", action="store_true", help="Emit capability cards as JSON")
    os_capabilities_parser.set_defaults(func=cmd_os_capabilities)
    os_authority_parser = os_subparsers.add_parser("authority", help="Inspect compiled Spark authority contracts")
    os_authority_parser.add_argument("--desktop", default=str(Path.home() / "Desktop"), help="Desktop root containing Spark repos")
    os_authority_parser.add_argument("--spark-home", default=str(SPARK_HOME), help="Spark home directory")
    os_authority_parser.add_argument("--registry", default=str(LOCAL_REGISTRY_PATH), help="spark-cli registry.json path")
    os_authority_parser.add_argument("--json", action="store_true", help="Emit authority contracts as JSON")
    os_authority_parser.set_defaults(func=cmd_os_authority)
    os_trace_parser = os_subparsers.add_parser("trace", help="Inspect compiled Spark trace health")
    os_trace_parser.add_argument("--desktop", default=str(Path.home() / "Desktop"), help="Desktop root containing Spark repos")
    os_trace_parser.add_argument("--spark-home", default=str(SPARK_HOME), help="Spark home directory")
    os_trace_parser.add_argument("--registry", default=str(LOCAL_REGISTRY_PATH), help="spark-cli registry.json path")
    os_trace_parser.add_argument("--json", action="store_true", help="Emit trace health as JSON")
    os_trace_parser.set_defaults(func=cmd_os_trace)
    os_memory_parser = os_subparsers.add_parser("memory", help="Inspect compiled Spark memory movement")
    os_memory_parser.add_argument("--desktop", default=str(Path.home() / "Desktop"), help="Desktop root containing Spark repos")
    os_memory_parser.add_argument("--spark-home", default=str(SPARK_HOME), help="Spark home directory")
    os_memory_parser.add_argument("--registry", default=str(LOCAL_REGISTRY_PATH), help="spark-cli registry.json path")
    os_memory_parser.add_argument("--json", action="store_true", help="Emit memory movement as JSON")
    os_memory_parser.set_defaults(func=cmd_os_memory)

    status_parser = subparsers.add_parser("status", help="Run module healthchecks")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subparsers.add_parser("doctor", help="Run diagnostic status and emit structured output")
    doctor_subparsers = doctor_parser.add_subparsers(dest="doctor_command")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    doctor_specialization_loop_parser = doctor_subparsers.add_parser("specialization-loop", help="Inspect specialization-loop discoverability without starting runs")
    doctor_specialization_loop_parser.add_argument("--json", action="store_true")
    doctor_specialization_loop_parser.add_argument("--proof", action="store_true", help="Read canonical specialization-loop status packets without starting runs")
    doctor_specialization_loop_parser.set_defaults(func=cmd_doctor)

    doctor_llm_parser = doctor_subparsers.add_parser("llm", help="Ask the user's configured LLM for a redacted Spark repair plan")
    doctor_llm_parser.add_argument("problem", nargs="*", help="Problem statement, for example: Telegram is quiet after restart")
    doctor_llm_parser.add_argument("--role", choices=LLM_ROLES, default="builder", help="Preferred LLM role to use (default: builder)")
    doctor_llm_parser.add_argument("--provider", choices=LLM_PROVIDER_CHOICES, help="Override the configured provider for this doctor run")
    doctor_llm_parser.add_argument("--model", help="Override the configured model for this doctor run")
    doctor_llm_parser.add_argument("--base-url", help="Override the configured OpenAI-compatible/Ollama base URL")
    doctor_llm_parser.add_argument("--include-logs", action="store_true", help="Include redacted module log tails in the doctor prompt")
    doctor_llm_parser.add_argument("--log-lines", type=int, default=80, help="Number of log lines per module when --include-logs is set")
    doctor_llm_parser.add_argument("--prompt-out", help="Write the redacted prompt to a file instead of calling the LLM")
    doctor_llm_parser.add_argument("--save-report", action="store_true", help="Save the doctor report under ~/.spark/doctor")
    doctor_llm_parser.add_argument("--upstream-report", action="store_true", help="Write a sanitized upstream PR candidate draft; never uploads automatically")
    doctor_llm_parser.add_argument("--upstream-out", help="Path for --upstream-report output")
    doctor_llm_parser.set_defaults(func=cmd_doctor)

    support_parser = subparsers.add_parser("support", help="Create local redacted support bundles for troubleshooting")
    support_subparsers = support_parser.add_subparsers(dest="support_command", required=True)
    support_bundle_parser = support_subparsers.add_parser("bundle", help="Write a local redacted support archive")
    support_bundle_parser.add_argument("--include-logs", action="store_true", help="Include redacted log tails after local review")
    support_bundle_parser.add_argument("--log-lines", type=int, default=120, help="Number of log lines per module when --include-logs is set")
    support_bundle_parser.add_argument("--json", action="store_true", help="Print the redacted bundle payload instead of writing a zip")
    support_bundle_parser.set_defaults(func=cmd_support)

    verify_parser = subparsers.add_parser("verify", help="Verify launch-critical Spark wiring end to end")
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.add_argument("--deep", action="store_true", help="Run live write/read memory smoke checks in addition to static wiring checks")
    verify_parser.add_argument("--onboarding", action="store_true", help="Run first-user onboarding checks and print the Telegram finish checklist")
    verify_parser.add_argument("--installers", action="store_true", help="Verify installer script hashes against the committed manifest")
    verify_parser.add_argument("--hosted-installers", action="store_true", help="Also compare agent.sparkswarm.ai installers against the committed manifest")
    verify_parser.add_argument("--hosted", action="store_true", help="Verify hosted Docker/Railway security posture")
    verify_parser.add_argument("--provenance", action="store_true", help="Report blessed module commit-pin, signature, and attestation posture")
    verify_parser.add_argument("--registry-pins", action="store_true", help="Verify blessed registry pins match each module's remote HEAD")
    verify_parser.add_argument("--sandboxes", action="store_true", help="Verify optional SSH/Modal sandbox readiness without running cloud smoke jobs")
    verify_parser.add_argument("--specialization-loop", action="store_true", help="Verify Domain Chip Labs, Swarm, and specialization-path loop surfaces are discoverable")
    verify_parser.add_argument("--proof", action="store_true", help="With --specialization-loop, read canonical status packets without starting runs")
    verify_parser.set_defaults(func=cmd_verify)

    smoke_parser = subparsers.add_parser("smoke", help="Run guided first-run Spark smoke checks")
    smoke_subparsers = smoke_parser.add_subparsers(dest="smoke_command", required=True)
    first_run_smoke_parser = smoke_subparsers.add_parser("first-run", help="Check local onboarding readiness and print the Telegram first-run script")
    first_run_smoke_parser.add_argument("--json", action="store_true")
    first_run_smoke_parser.add_argument("--quick", action="store_true", help="Skip deep local memory smoke checks")
    first_run_smoke_parser.set_defaults(func=cmd_smoke)

    fix_parser = subparsers.add_parser("fix", help="Run targeted repair guidance for common Spark issues")
    fix_parser.add_argument(
        "target",
        nargs="?",
        choices=["telegram", "secrets", "spawner", "providers", "memory", "live", "update", "autostart"],
        default="telegram",
    )
    fix_parser.add_argument("--redact-logs", action="store_true", help="For `spark fix secrets`, redact secret-like values in local generated logs")
    fix_parser.add_argument("--json", action="store_true")
    fix_parser.set_defaults(func=cmd_fix)

    providers_parser = subparsers.add_parser("providers", help="Inspect Spark LLM provider choices and role wiring")
    providers_sub = providers_parser.add_subparsers(dest="providers_command", required=True)
    providers_recommend_parser = providers_sub.add_parser("recommend", help="Recommend LLM paths for paid, API-key, and local setups")
    providers_recommend_parser.add_argument("--json", action="store_true")
    providers_recommend_parser.set_defaults(func=cmd_providers)
    providers_list_parser = providers_sub.add_parser("list", help="List supported LLM providers and setup paths")
    providers_list_parser.add_argument("--json", action="store_true")
    providers_list_parser.set_defaults(func=cmd_providers)
    providers_status_parser = providers_sub.add_parser("status", help="Show chat/build/memory/mission provider readiness")
    providers_status_parser.add_argument("--json", action="store_true")
    providers_status_parser.set_defaults(func=cmd_providers)
    providers_test_parser = providers_sub.add_parser("test", help="Send a tiny PING_OK probe through one configured role")
    providers_test_parser.add_argument("--role", choices=LLM_ROLES, default="chat", help="LLM role to test")
    providers_test_parser.add_argument("--provider", choices=LLM_PROVIDER_CHOICES, help="Override the configured provider")
    providers_test_parser.add_argument("--json", action="store_true")
    providers_test_parser.set_defaults(func=cmd_providers)

    recommend_parser = subparsers.add_parser("recommend", help="Recommend Spark setup choices")
    recommend_sub = recommend_parser.add_subparsers(dest="recommend_command", required=True)
    recommend_llms_parser = recommend_sub.add_parser("llms", help="Recommend LLM providers for Spark")
    recommend_llms_parser.add_argument("--json", action="store_true")
    recommend_llms_parser.set_defaults(func=cmd_recommend)
    recommend_providers_parser = recommend_sub.add_parser("providers", help="Recommend LLM providers for Spark")
    recommend_providers_parser.add_argument("--json", action="store_true")
    recommend_providers_parser.set_defaults(func=cmd_recommend)

    security_parser = subparsers.add_parser("security", help="Audit Spark's local security posture")
    security_subparsers = security_parser.add_subparsers(dest="security_command", required=True)
    security_audit_parser = security_subparsers.add_parser("audit", help="Check secrets, provider wiring, ingress mode, and runtime health")
    security_audit_parser.add_argument("--deep", action="store_true", help="Include deep verification checks")
    security_audit_parser.add_argument("--hosted", action="store_true", help="Include Docker/Railway hosted security checks")
    security_audit_parser.add_argument("--json", action="store_true")
    security_audit_parser.set_defaults(func=cmd_security)
    security_revoke_parser = security_subparsers.add_parser(
        "revoke-all",
        help="Panic button: stop Spark, rotate local control keys, remove local secrets, and write a support bundle",
    )
    security_revoke_parser.add_argument("--dry-run", action="store_true", help="Report what would change without mutating local state")
    security_revoke_parser.add_argument("--include-logs", action="store_true", help="Include redacted logs in the support bundle")
    security_revoke_parser.add_argument("--json", action="store_true")
    security_revoke_parser.set_defaults(func=cmd_security)

    access_parser = subparsers.add_parser("access", help="Prepare Spark's local access lanes without technical sandbox choices")
    access_subparsers = access_parser.add_subparsers(dest="access_command", required=True)
    access_status_parser = access_subparsers.add_parser("status", help="Show the current recommended access lane")
    access_status_parser.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5], default=4)
    access_status_parser.add_argument("--goal", default="", help="Optional task goal used to recommend Docker, SSH, Modal, or workspace")
    access_status_parser.add_argument("--json", action="store_true")
    access_status_parser.set_defaults(func=cmd_access)
    access_guide_parser = access_subparsers.add_parser("guide", help="Explain Spark's safe access path in plain language")
    access_guide_parser.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5], default=4)
    access_guide_parser.add_argument("--goal", default="", help="Optional task goal used to recommend Docker, SSH, Modal, or workspace")
    access_guide_parser.add_argument("--json", action="store_true")
    access_guide_parser.set_defaults(func=cmd_access)
    access_setup_parser = access_subparsers.add_parser("setup", help="Create the safe Level 4 workspace and show optional lanes")
    access_setup_parser.add_argument("--level", type=int, choices=[4, 5], default=4)
    access_setup_parser.add_argument("--goal", default="", help="Optional task goal used to recommend Docker, SSH, Modal, or workspace")
    access_setup_parser.add_argument("--with", dest="with_lane", choices=["docker", "ssh", "modal"], help="Prefer a guided optional lane after the workspace is ready")
    access_setup_parser.add_argument(
        "--enable-high-agency",
        action="store_true",
        help="For --level 5 only: write local safety settings so Spark can use whole-computer operator mode after refresh",
    )
    access_setup_parser.add_argument("--json", action="store_true")
    access_setup_parser.set_defaults(func=cmd_access)
    access_disable_parser = access_subparsers.add_parser(
        "disable-level5",
        help="Disable whole-computer operator guardrails and return to sandbox-first access after restart",
    )
    access_disable_parser.add_argument("--json", action="store_true")
    access_disable_parser.set_defaults(func=cmd_access)

    sandbox_parser = subparsers.add_parser("sandbox", help="Manage optional Docker, SSH, and Modal sandbox checks")
    sandbox_subparsers = sandbox_parser.add_subparsers(dest="sandbox_backend", required=True)
    sandbox_docker_parser = sandbox_subparsers.add_parser("docker", help="Run Docker sandbox readiness checks")
    sandbox_docker_subparsers = sandbox_docker_parser.add_subparsers(dest="docker_command", required=True)
    sandbox_docker_doctor_parser = sandbox_docker_subparsers.add_parser("doctor", help="Run Docker diagnostics")
    sandbox_docker_doctor_parser.add_argument("--json", action="store_true")
    sandbox_docker_doctor_parser.set_defaults(func=cmd_sandbox)
    sandbox_docker_smoke_parser = sandbox_docker_subparsers.add_parser("smoke", help="Run a no-secret Docker sandbox smoke")
    sandbox_docker_smoke_parser.add_argument("--json", action="store_true")
    sandbox_docker_smoke_parser.add_argument("--image", default="", help="Docker image tag to build/run")
    sandbox_docker_smoke_parser.add_argument("--no-build", action="store_true", help="Use an existing sandbox image instead of building")
    sandbox_docker_smoke_parser.add_argument("--network", action="store_true", help="Allow bridge networking for this explicit smoke")
    sandbox_docker_smoke_parser.set_defaults(func=cmd_sandbox)

    sandbox_ssh_parser = sandbox_subparsers.add_parser("ssh", help="Manage SSH remote sandbox targets")
    sandbox_ssh_subparsers = sandbox_ssh_parser.add_subparsers(dest="ssh_command", required=True)
    sandbox_ssh_add_parser = sandbox_ssh_subparsers.add_parser("add", help="Add an SSH target record")
    sandbox_ssh_add_parser.add_argument("name")
    sandbox_ssh_add_parser.add_argument("--host", required=True)
    sandbox_ssh_add_parser.add_argument("--user", required=True)
    sandbox_ssh_add_parser.add_argument("--identity-file", required=True)
    sandbox_ssh_add_parser.add_argument("--port", type=int, default=22)
    sandbox_ssh_add_parser.add_argument("--json", action="store_true")
    sandbox_ssh_add_parser.set_defaults(func=cmd_sandbox)
    sandbox_ssh_list_parser = sandbox_ssh_subparsers.add_parser("list", help="List configured SSH sandbox targets")
    sandbox_ssh_list_parser.add_argument("--json", action="store_true")
    sandbox_ssh_list_parser.set_defaults(func=cmd_sandbox)
    sandbox_ssh_trust_parser = sandbox_ssh_subparsers.add_parser("trust", help="Scan and trust an SSH host key without logging in")
    sandbox_ssh_trust_parser.add_argument("name")
    sandbox_ssh_trust_parser.add_argument("--fingerprint", help="Require this SHA256 host-key fingerprint")
    sandbox_ssh_trust_parser.add_argument("--json", action="store_true")
    sandbox_ssh_trust_parser.set_defaults(func=cmd_sandbox)
    sandbox_ssh_doctor_parser = sandbox_ssh_subparsers.add_parser("doctor", help="Run SSH target diagnostics")
    sandbox_ssh_doctor_parser.add_argument("name")
    sandbox_ssh_doctor_parser.add_argument("--json", action="store_true")
    sandbox_ssh_doctor_parser.add_argument("--remote-probe", action="store_true", help="Run a fixed read-only SSH connection probe after host-key trust")
    sandbox_ssh_doctor_parser.set_defaults(func=cmd_sandbox)
    sandbox_ssh_smoke_parser = sandbox_ssh_subparsers.add_parser("smoke", help="Run SSH hashed-probe smoke")
    sandbox_ssh_smoke_parser.add_argument("name")
    sandbox_ssh_smoke_parser.add_argument("--json", action="store_true")
    sandbox_ssh_smoke_parser.add_argument("--keep-debug-files", action="store_true")
    sandbox_ssh_smoke_parser.set_defaults(func=cmd_sandbox)
    sandbox_ssh_remove_parser = sandbox_ssh_subparsers.add_parser("remove", help="Remove an SSH sandbox target")
    sandbox_ssh_remove_parser.add_argument("name")
    sandbox_ssh_remove_parser.add_argument("--json", action="store_true")
    sandbox_ssh_remove_parser.set_defaults(func=cmd_sandbox)

    sandbox_modal_parser = sandbox_subparsers.add_parser("modal", help="Run Modal sandbox checks")
    sandbox_modal_subparsers = sandbox_modal_parser.add_subparsers(dest="modal_command", required=True)
    sandbox_modal_doctor_parser = sandbox_modal_subparsers.add_parser("doctor", help="Run Modal diagnostics")
    sandbox_modal_doctor_parser.add_argument("--json", action="store_true")
    sandbox_modal_doctor_parser.set_defaults(func=cmd_sandbox)
    sandbox_modal_smoke_parser = sandbox_modal_subparsers.add_parser("smoke", help="Run Modal no-secret smoke")
    sandbox_modal_smoke_parser.add_argument("--json", action="store_true")
    sandbox_modal_smoke_parser.set_defaults(func=cmd_sandbox)

    approval_parser = subparsers.add_parser("approval", help="Classify sensitive Spark actions before enforcement")
    approval_subparsers = approval_parser.add_subparsers(dest="approval_command", required=True)
    approval_classify_parser = approval_subparsers.add_parser("classify", help="Report whether a command should require approval")
    approval_classify_parser.add_argument("--json", action="store_true")
    approval_classify_parser.add_argument("--hosted", action="store_true", help="Classify as a hosted/VPS action")
    approval_classify_parser.add_argument("--surface", default="cli", help="Surface requesting the action, for example cli, telegram, or spark-live")
    approval_classify_parser.add_argument("--non-interactive", action="store_true", help="Classify as a non-interactive call")
    approval_classify_parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to classify; use -- before the command")
    approval_classify_parser.set_defaults(func=cmd_approval)

    telegram_parser = subparsers.add_parser("telegram", help="Connect and manage Telegram bots")
    telegram_sub = telegram_parser.add_subparsers(dest="telegram_command", required=True)
    telegram_connect_parser = telegram_sub.add_parser("connect", help="Connect a BotFather token to a Spark Telegram profile")
    telegram_connect_parser.add_argument(
        "profile",
        nargs="?",
        help="Telegram profile to connect (default: the primary profile, usually spark-agi)",
    )
    telegram_connect_parser.add_argument(
        "--token",
        "--bot-token",
        dest="token",
        help="BotFather token. Omit this flag to paste it securely when Spark asks.",
    )
    telegram_connect_parser.add_argument("--admin-telegram-ids", help="Comma-separated Telegram admin IDs")
    telegram_connect_parser.add_argument("--telegram-relay-port", type=int, help="Local Telegram mission relay port")
    telegram_connect_parser.add_argument(
        "--skip-telegram-token-check",
        action="store_true",
        help="Skip live Telegram getMe token validation before saving a new bot token (offline/dev only)",
    )
    telegram_connect_parser.add_argument("--no-restart", action="store_true", help="Save the token without restarting the bot")
    telegram_connect_parser.set_defaults(func=cmd_telegram_connect)

    update_parser = subparsers.add_parser("update", help="Refresh installed modules from their current source paths")
    update_parser.add_argument("target", nargs="?")
    update_parser.add_argument("--skip-install-commands", action="store_true", help="Skip post-update install commands (pip install, npm install) for faster refresh")
    update_parser.add_argument("--skip-dirty", action="store_true", help="Skip modules with local git changes and continue updating clean modules")
    update_parser.add_argument("--stash-local-runtime", action="store_true", help="Stash dirty installed-runtime module edits before updating")
    update_parser.add_argument("--continue", dest="continue_update", action="store_true", help="Resume after fixing a previous update preflight stop")
    update_parser.add_argument("--no-live-restart", action="store_true", help="Do not restart Spark Live after updating stopped runtime services")
    update_parser.set_defaults(func=cmd_update)

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove installed modules from Spark state and generated config")
    uninstall_parser.add_argument("target", nargs="?")
    uninstall_parser.add_argument("--all", action="store_true", help="Uninstall all installed Spark modules")
    uninstall_parser.add_argument("--force", action="store_true")
    uninstall_parser.add_argument("--remove-autostart", action="store_true", help="Remove OS login autostart hooks")
    uninstall_parser.add_argument("--remove-user-path", action="store_true", help="Remove Spark bin from the Windows user PATH after uninstall")
    uninstall_parser.add_argument("--purge-home", action="store_true", help="Delete SPARK_HOME after uninstall cleanup")
    uninstall_parser.add_argument("--yes", action="store_true", help="Confirm destructive cleanup such as --purge-home")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    start_parser = subparsers.add_parser("start", help="Start startable modules")
    start_parser.add_argument("--allow-boot-warnings", action="store_true", help=argparse.SUPPRESS)
    start_parser.add_argument("--allow-dirty-runtime", action="store_true", help="Start even when installed runtime code has local edits or is off the registry pin")
    start_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Named Telegram bot profile to start")
    start_parser.add_argument("target", nargs="?")
    start_parser.set_defaults(func=cmd_start)

    stop_parser = subparsers.add_parser("stop", help="Stop tracked Spark processes")
    stop_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Named Telegram bot profile to stop")
    stop_parser.add_argument("--cascade", action="store_true", help="Also stop running modules that depend on the target")
    stop_parser.add_argument("target", nargs="?")
    stop_parser.set_defaults(func=cmd_stop)

    restart_parser = subparsers.add_parser("restart", help="Restart startable modules")
    restart_parser.add_argument("--allow-dirty-runtime", action="store_true", help="Restart even when installed runtime code has local edits or is off the registry pin")
    restart_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Named Telegram bot profile to restart")
    restart_parser.add_argument("--cascade", action="store_true", help="Also restart running modules that depend on the target")
    restart_parser.add_argument("target", nargs="?")
    restart_parser.set_defaults(func=cmd_restart)

    live_parser = subparsers.add_parser("live", help="Control Spark Live, the friendly always-on agent surface")
    live_subparsers = live_parser.add_subparsers(dest="live_command")
    live_status_parser = live_subparsers.add_parser("status", help="Show Spark Live readiness")
    live_status_parser.add_argument("--json", action="store_true")
    live_status_parser.set_defaults(func=cmd_live)
    live_start_parser = live_subparsers.add_parser("start", help="Start Spark Live")
    live_start_parser.add_argument("--allow-dirty-runtime", action="store_true", help="Start even when installed runtime code has local edits or is off the registry pin")
    live_start_parser.set_defaults(func=cmd_live)
    live_run_parser = live_subparsers.add_parser("run", help="Start Spark Live and keep one combined log console open")
    live_run_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=80,
        help="Lines of history to show before following (0 = new lines only)",
    )
    live_run_parser.add_argument("--allow-dirty-runtime", action="store_true", help="Start even when installed runtime code has local edits or is off the registry pin")
    live_run_parser.set_defaults(func=cmd_live)
    live_restart_parser = live_subparsers.add_parser("restart", help="Restart Spark Live")
    live_restart_parser.add_argument("--allow-dirty-runtime", action="store_true", help="Restart even when installed runtime code has local edits or is off the registry pin")
    live_restart_parser.set_defaults(func=cmd_live)
    live_stop_parser = live_subparsers.add_parser("stop", help="Stop Spark Live")
    live_stop_parser.set_defaults(func=cmd_live)
    live_logs_parser = live_subparsers.add_parser("logs", help="Show Spark Live logs")
    live_logs_parser.add_argument("-n", "--lines", type=int, default=80)
    live_logs_parser.add_argument("-f", "--follow", action="store_true", help="Keep watching combined Spark Live logs")
    live_logs_parser.set_defaults(func=cmd_live)
    live_verify_parser = live_subparsers.add_parser("verify", help="Run the hosted Spark Live release gate")
    live_verify_parser.add_argument("--json", action="store_true")
    live_verify_parser.add_argument("--quick", action="store_true", help="Skip the deep hosted mission smoke")
    live_verify_parser.set_defaults(func=cmd_live)
    live_parser.set_defaults(func=cmd_live, live_command="status")

    autostart_parser = subparsers.add_parser("autostart", help="Start Spark automatically when this computer logs in")
    autostart_subparsers = autostart_parser.add_subparsers(dest="autostart_command", required=True)
    autostart_install_parser = autostart_subparsers.add_parser("install", help="Install OS login autostart")
    autostart_install_parser.add_argument("target", nargs="?", default="telegram-starter")
    autostart_install_parser.add_argument("--now", action="store_true", help="Start Spark immediately after installing autostart")
    autostart_install_parser.set_defaults(func=cmd_autostart_install)
    autostart_on_parser = autostart_subparsers.add_parser("on", help="Install OS login autostart")
    autostart_on_parser.add_argument("target", nargs="?", default="telegram-starter")
    autostart_on_parser.add_argument("--now", action="store_true", help="Start Spark immediately after installing autostart")
    autostart_on_parser.set_defaults(func=cmd_autostart_install)
    autostart_uninstall_parser = autostart_subparsers.add_parser("uninstall", help="Remove OS login autostart")
    autostart_uninstall_parser.set_defaults(func=cmd_autostart_uninstall)
    autostart_off_parser = autostart_subparsers.add_parser("off", help="Remove OS login autostart")
    autostart_off_parser.set_defaults(func=cmd_autostart_uninstall)
    autostart_profile_parser = autostart_subparsers.add_parser(
        "profile",
        help="Turn login startup on or off for one Telegram profile",
    )
    autostart_profile_parser.add_argument("profile", help="Telegram profile name, for example spark-agi or qa-bot")
    autostart_profile_parser.add_argument("state", choices=["on", "off"], help="Whether this profile should start with Spark Live")
    autostart_profile_parser.set_defaults(func=cmd_autostart_profile)
    autostart_status_parser = autostart_subparsers.add_parser("status", help="Show OS login autostart status")
    autostart_status_parser.set_defaults(func=cmd_autostart_status)

    guide_parser = subparsers.add_parser("guide", help="Show first-run BotFather, LLM, module, and Telegram command guide")
    guide_parser.add_argument("topic", nargs="?", help="Optional topic hint (install, setup, telegram, providers, voice, security, update); currently shows the full guide")
    guide_parser.add_argument("--json", action="store_true", help="Emit the guide as structured JSON")
    guide_parser.add_argument("--advanced", action="store_true", help="Show provider splits, multiple bots, allowed actions, modules, and support commands")
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
    logs_parser.add_argument("--profile", default=DEFAULT_TELEGRAM_PROFILE, help="Named Telegram bot profile logs to read")
    logs_parser.add_argument("target")
    logs_parser.add_argument("-n", "--lines", type=int, default=200, help="Lines of history to show before following (default: 200, 0 = all)")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Tail the log and stream new lines")
    logs_parser.set_defaults(func=cmd_logs)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_state_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    approval_exit = enforce_cli_approval(args, command_argv_for_approval(argv))
    if approval_exit is not None:
        return approval_exit
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
