from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from .output import redact_sandbox_text
from .paths import sandbox_log_dir, validate_target_name


AUDIT_SCHEMA_VERSION = 1


def sandbox_audit_path(backend: str, target: str, *, home: Path | None = None) -> Path:
    safe_backend = validate_target_name(backend)
    safe_target = validate_target_name(target)
    return sandbox_log_dir(home) / safe_backend / f"{safe_target}.jsonl"


def sandbox_audit_ref(backend: str, target: str) -> dict[str, object]:
    safe_backend = validate_target_name(backend)
    safe_target = validate_target_name(target)
    return {
        "written": True,
        "log": f"logs/remote/{safe_backend}/{safe_target}.jsonl",
    }


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sandbox_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    return value


def write_audit_event(
    backend: str,
    target: str,
    event: dict[str, Any],
    *,
    home: Path | None = None,
) -> Path:
    path = sandbox_audit_path(backend, target, home=home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": validate_target_name(backend),
        "target": validate_target_name(target),
        **_redact_value(event),
    }
    # Atomically open with restrictive permissions (owner-only read/write).
    # Use os.open for low-level permission control; fall back to pathlib if needed.
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        # Fallback if os.open fails (e.g. Windows); set restrictive perms after creation
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        try:
            path.chmod(0o600)
        except OSError as exc:
            logging.getLogger(__name__).warning(
                "audit log chmod failed for %s: %s", path, exc
            )
    return path
