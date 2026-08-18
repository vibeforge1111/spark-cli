from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


IS_WINDOWS = os.name == "nt"


def _windows_native_candidates() -> list[Path]:
    roots = [
        Path.home() / ".npm-global" / "node_modules" / "@openai",
        Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@openai",
    ]
    candidates: list[Path] = []
    for root in roots:
        for package in ("codex-win32-x64", "codex-win32-arm64"):
            candidates.extend(
                root.glob(f"codex/node_modules/@openai/{package}/vendor/*/bin/codex.exe")
            )
    return candidates


def detect_codex_cli() -> dict[str, Any]:
    for env_name in ("SPARK_CODEX_PATH", "CODEX_PATH"):
        configured = os.environ.get(env_name, "").strip()
        if configured and Path(configured).is_file():
            return {"present": True, "path": configured}

    if IS_WINDOWS:
        for candidate in _windows_native_candidates():
            if candidate.is_file():
                return {"present": True, "path": str(candidate)}

    path = shutil.which("codex")
    return {"present": bool(path), "path": path}
