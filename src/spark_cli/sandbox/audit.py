from __future__ import annotations

import json
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
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
