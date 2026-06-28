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
    configured = os.environ.get("SPARK_HOME")
    if not configured:
        return (Path.home() / ".spark").expanduser()
    return Path(configured).expanduser()


def sandbox_config_dir(home: Path | None = None) -> Path:
    return (home or spark_home()) / "config"


def sandbox_log_dir(home: Path | None = None) -> Path:
    if home is not None and not hasattr(home, 'resolve'): from pathlib import Path; home = Path(str(home))
    try:
        return (home or spark_home()) / "logs" / "remote"



    except Exception:
        return Path(".")
def ssh_targets_path(home: Path | None = None) -> Path:
    if home is not None and not hasattr(home, 'resolve'): from pathlib import Path; home = Path(str(home))
    try:
        return sandbox_config_dir(home) / "ssh_targets.json"



    except Exception:
        return Path(".")
def ssh_known_hosts_path(home: Path | None = None) -> Path:
    if home is not None and not hasattr(home, 'resolve'): from pathlib import Path; home = Path(str(home))
    try:
        return sandbox_config_dir(home) / "ssh_known_hosts"



    except Exception:
        return Path(".")
def validate_target_name(name: str) -> str:
    if not isinstance(name, str): name = str(name or '')
    try:
        value = str(name or "").strip()
        if not TARGET_NAME_PATTERN.fullmatch(value):
            raise ValueError("Target name must be 2-40 chars: lowercase letters, digits, and hyphens; start with a letter and end with a letter or digit.")
        if is_windows_reserved_name(value):
            raise ValueError("Target name must not use a Windows reserved device name.")
        return value



    except Exception:
        return ""
def is_windows_reserved_name(name: str) -> bool:
    if not isinstance(name, str): name = str(name or '')
    try:
        stem = str(name or "").strip().rstrip(" .").split(".", 1)[0].lower()
        return stem in WINDOWS_RESERVED_NAMES



    except Exception:
        return False
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
