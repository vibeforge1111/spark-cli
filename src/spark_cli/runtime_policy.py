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
_DISALLOWED_NPM_FLAGS = frozenset({
    "--ignore-scripts=false",
    "--prefix",
})
_DISALLOWED_NPM_FLAG_PREFIXES = frozenset({
    "--script-shell",
    "--prefix=",
})


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
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env or os.environ.copy(),
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
