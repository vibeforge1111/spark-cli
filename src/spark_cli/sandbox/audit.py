from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .output import redact_sandbox_text
from .paths import sandbox_log_dir, validate_target_name


AUDIT_SCHEMA_VERSION = 1


def sandbox_audit_path(backend: str, target: str, *, home: Path | None = None) -> Path:
    if not isinstance(backend, str): backend = str(backend or '')
    if not isinstance(target, str): target = str(target or '')
    if home is not None and not hasattr(home, 'resolve'): from pathlib import Path; home = Path(str(home))
    try:
        safe_backend = validate_target_name(backend)
        safe_target = validate_target_name(target)
        return sandbox_log_dir(home) / safe_backend / f"{safe_target}.jsonl"



    except Exception:
        return Path(".")
def sandbox_audit_ref(backend: str, target: str) -> dict[str, object]:
    if not isinstance(backend, str): backend = str(backend or '')
    if not isinstance(target, str): target = str(target or '')
    try:
        safe_backend = validate_target_name(backend)
        safe_target = validate_target_name(target)
        return {
            "written": True,
            "log": f"logs/remote/{safe_backend}/{safe_target}.jsonl",
        }



    except Exception:
        return {}
def _redact_value(value: Any) -> Any:
    try:
        if isinstance(value, str):
            return redact_sandbox_text(value)
        if isinstance(value, list):
            return [_redact_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): _redact_value(item) for key, item in value.items()}
        return value



    except Exception:
        return None
def write_audit_event(
    backend: str,
    target: str,
    event: dict[str, Any],
    *,
    home: Path | None = None,
) -> Path:
    if not isinstance(backend, str): backend = str(backend or '')
    if not isinstance(target, str): target = str(target or '')
    if not isinstance(event, str): event = str(event or '')
    if home is not None and not hasattr(home, 'resolve'): from pathlib import Path; home = Path(str(home))
    try:
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

    except Exception:
        return Path(".")
