from __future__ import annotations

import os
import re
from pathlib import Path


TARGET_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$")


def spark_home() -> Path:
    return Path(os.environ.get("SPARK_HOME", Path.home() / ".spark")).expanduser()


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
    return value


def resolve_safe_output_path(path: str | Path, *, root: Path) -> Path:
    root_path = root.expanduser()
    root_resolved = root_path.resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path must stay inside {root_resolved}.")
    return candidate
