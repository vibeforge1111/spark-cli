from __future__ import annotations

import os
import re
from pathlib import Path


TARGET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$")
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{idx}" for idx in range(1, 10)),
    *(f"lpt{idx}" for idx in range(1, 10)),
}
WINDOWS_UNSAFE_NAME_PATTERN = re.compile(r'[<>:"\\|?*]')


def spark_home() -> Path:
    # Honor missing-vs-explicit-empty: only fall back to the default when
    # SPARK_HOME is unset, not when the operator set it to an empty string.
    # os.environ.get("SPARK_HOME", default) returns "" (not the default)
    # when SPARK_HOME == '', and Path("").expanduser() resolves to the
    # current working directory, which is surprising and unsafe.
    configured = os.environ.get("SPARK_HOME")
    if not configured:
        return (Path.home() / ".spark").expanduser()
    return Path(configured).expanduser()


def sandbox_config_dir(home: Path | None = None) -> Path:
    return (home or spark_home()) / "config"


def sandbox_log_dir(home: Path | None = None) -> Path:
    return (home or spark_home()) / "logs" / "remote"


def ssh_targets_path(home: Path | None = None) -> Path:
    return sandbox_config_dir(home) / "ssh_targets.json"


def ssh_known_hosts_path(home: Path | None = None) -> Path:
    return sandbox_config_dir(home) / "ssh_known_hosts"


def validate_target_name(name: str) -> str:
    value = str(name or "").strip()
    if not TARGET_NAME_PATTERN.fullmatch(value):
        raise ValueError("Target name must be 2-40 chars: lowercase letters, digits, and hyphens; start with a letter and end with a letter or digit.")
    if is_windows_reserved_name(value):
        raise ValueError("Target name must not use a Windows reserved device name.")
    return value


def is_windows_reserved_name(name: str) -> bool:
    stem = str(name or "").strip().rstrip(" .").split(".", 1)[0].lower()
    return stem in WINDOWS_RESERVED_NAMES


def resolve_safe_output_path(path: str | Path, *, root: Path) -> Path:
    root_resolved = root.expanduser().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    resolved = candidate.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path must stay inside {root_resolved}.")
    relative = resolved.relative_to(root_resolved) if resolved != root_resolved else Path()
    if any(is_windows_reserved_name(part) for part in relative.parts):
        raise ValueError("Path must not use a Windows reserved device name.")
    if any(WINDOWS_UNSAFE_NAME_PATTERN.search(part) for part in relative.parts):
        raise ValueError("Path must not use Windows-unsafe characters.")
    return resolved
