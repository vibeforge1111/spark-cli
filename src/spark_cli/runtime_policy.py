from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


SHELL_CHAIN_TOKENS = {"&&", "||", ";", "|", ">", ">>", "<"}

# Module install commands may only run package-manifest install paths.
# Anything that lets the caller execute arbitrary scripts / relocate the
# install / re-enable lifecycle script execution is blocked.
_ALLOWED_NPM_SUBCOMMANDS = frozenset({"install", "ci"})
# Exact-match flags that are never allowed (the "safe" form of the same flag,
# e.g. --ignore-scripts=true or --global=false, is intentionally NOT blocked).
_DISALLOWED_NPM_FLAGS = frozenset({
    "--ignore-scripts=false",   # re-enables lifecycle scripts
    "-g",                       # global install escapes the module sandbox dir
    "--global",
    "--global=true",
    "--location=global",        # equivalent to --global
    "--install-links",          # installs local deps as real installs (can run scripts)
    "--install-links=true",
    "--unsafe-perm",            # runs scripts as root
    "--unsafe-perm=true",
})
# Prefix-match: blocks the flag and any =value / space-separated value form,
# because ANY value of these flags is dangerous.
_DISALLOWED_NPM_FLAG_PREFIXES = frozenset({
    "--script-shell",   # custom shell for lifecycle scripts
    "--prefix",         # relocate the install target
    "--userconfig",     # point npm at an attacker-controlled .npmrc...
    "--globalconfig",   # ...which can itself set ignore-scripts=false, script-shell, registry
    "--registry",       # redirect the package source (supply-chain / script delivery)
    "--cache",          # relocate the cache dir
})

# npm also honours npm_config_* / NPM_CONFIG_* environment variables and
# NODE_OPTIONS, any of which can re-enable lifecycle scripts, point npm at an
# attacker-controlled config/registry, or inject `--require <module>` into the
# Node process — bypassing the argv policy above. Strip these for module-install
# npm invocations so the environment cannot override the policy.
_DISALLOWED_NPM_ENV_CONFIG_KEYS = frozenset({
    "ignore_scripts", "foreground_scripts", "script_shell", "unsafe_perm",
    "userconfig", "globalconfig", "registry", "prefix", "global",
    "cache", "install_links", "location", "node_options",
})


def sanitize_npm_env(env: dict[str, str]) -> dict[str, str]:
    """Drop env vars that could re-enable scripts or redirect npm's config."""
    cleaned: dict[str, str] = {}
    for key, value in env.items():
        lower_key = key.lower()
        if lower_key == "node_options":
            continue
        if lower_key.startswith("npm_config_") and \
                lower_key[len("npm_config_"):] in _DISALLOWED_NPM_ENV_CONFIG_KEYS:
            continue
        cleaned[key] = value
    return cleaned


def _is_npm_invocation(command: str) -> bool:
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return False
    return bool(parts) and parts[0].lower() == "npm"


def split_single_argv_command(command: str, subject: str) -> list[str]:
    parts = shlex.split(command, posix=True)
    if not parts:
        raise SystemExit(f"{subject} cannot be empty.")
    if any(part in SHELL_CHAIN_TOKENS for part in parts):
        raise SystemExit(f"{subject} must be a single argv command, not a shell command chain.")
    return parts


def resolve_runtime_executable(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    if os.name == "nt" and not name.lower().endswith((".exe", ".cmd", ".bat", ".ps1")):
        for suffix in (".cmd", ".exe", ".bat"):
            path = shutil.which(name + suffix)
            if path:
                return path
    raise SystemExit(
        f"Missing required runtime tool `{name}`. Install it, reopen the terminal, then rerun the command. "
        "For Node modules, install Node.js 22+ or rerun Spark's installer with managed Node enabled."
    )


def npm_runtime_command_argv(args: list[str]) -> list[str]:
    npm_path = resolve_runtime_executable("npm")
    if os.name == "nt" and os.path.splitext(npm_path)[1].lower() in {".cmd", ".bat"}:
        npm_dir = os.path.dirname(npm_path)
        node_path = shutil.which("node") or os.path.join(npm_dir, "node.exe")
        npm_cli = os.path.join(npm_dir, "node_modules", "npm", "bin", "npm-cli.js")
        if node_path and os.path.exists(npm_cli):
            return [node_path, npm_cli, *args]
    return [npm_path, *args]


def runtime_command_argv(command: str) -> list[str]:
    parts = split_single_argv_command(command, "Runtime command")
    executable = parts[0].lower()
    if executable in {"python", "python3"}:
        return [str(Path(sys.executable)), *parts[1:]]
    if executable == "node":
        return [resolve_runtime_executable("node"), *parts[1:]]
    if executable == "npm":
        if len(parts) < 2:
            raise SystemExit(
                "npm with no subcommand is not permitted in module install commands. "
                "Use 'npm install' or 'npm ci'."
            )
        subcommand = parts[1].lower()
        if subcommand not in _ALLOWED_NPM_SUBCOMMANDS:
            raise SystemExit(
                f"npm subcommand {subcommand!r} is not permitted in module install commands. "
                f"Allowed: {sorted(_ALLOWED_NPM_SUBCOMMANDS)}. "
                "Remove 'npm run', 'npm exec', 'npx', and similar from the module's install commands."
            )
        # Block flags that re-enable script execution or relocate the install path.
        # npm install itself runs lifecycle scripts unless --ignore-scripts is set;
        # users can explicitly re-enable script execution with --ignore-scripts=false,
        # and --script-shell / --prefix open further-reaching post-install paths.
        for arg in parts[2:]:
            if arg in _DISALLOWED_NPM_FLAGS:
                raise SystemExit(
                    f"npm flag {arg!r} is not permitted in module install commands. "
                    f"Blocked flags: {sorted(_DISALLOWED_NPM_FLAGS)}."
                )
            for prefix in _DISALLOWED_NPM_FLAG_PREFIXES:
                if arg.startswith(prefix):
                    raise SystemExit(
                        f"npm flag prefix {prefix!r} is not permitted in module install commands "
                        f"(saw {arg!r})."
                    )
        return npm_runtime_command_argv(parts[1:])
    if executable == "uv" and len(parts) >= 2 and parts[1] == "run":
        return [resolve_runtime_executable("uv"), *parts[1:]]
    raise SystemExit(
        "Unsupported runtime command executable. Allowed runtime commands must start with "
        "python, python3, node, npm, or uv run."
    )


def run_runtime_command(
    command: str,
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = runtime_command_argv(command)
    run_env = env if env is not None else os.environ.copy()
    # For npm installs, strip env vars that could re-enable scripts or redirect
    # config, so the argv policy in runtime_command_argv() cannot be bypassed
    # through the environment.
    if _is_npm_invocation(command):
        run_env = sanitize_npm_env(run_env)
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr = (stderr + "\n" if stderr else "") + f"command timed out after {timeout}s"
        return subprocess.CompletedProcess(command, 124, stdout=stdout, stderr=stderr)
    except OSError as error:
        return subprocess.CompletedProcess(
            command,
            127,
            stdout="",
            stderr=f"Could not start runtime command `{command}`: {error.__class__.__name__}. Check that the required tool is installed and on PATH.",
        )
