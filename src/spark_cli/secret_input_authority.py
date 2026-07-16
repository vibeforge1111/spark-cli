from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def validated_secrets_index(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SystemExit("Secrets index must be a JSON object. Nothing was changed.")
    if any(
        not isinstance(secret_id, str)
        or not isinstance(backend, str)
        or backend not in {"file", "keychain"}
        for secret_id, backend in value.items()
    ):
        raise SystemExit("Secrets index contains an invalid secret-storage entry. Nothing was changed.")
    return value


def normalized_secret_file_path(value: Any) -> Path:
    if isinstance(value, bool) or not isinstance(value, (str, os.PathLike)):
        raise SystemExit("Secret file hardening requires a valid filesystem path.")
    try:
        path = Path(value)
    except (TypeError, ValueError):
        raise SystemExit("Secret file hardening requires a valid filesystem path.") from None
    if not os.fspath(value) or path == Path("."):
        raise SystemExit("Secret file hardening requires a valid filesystem path.")
    return path


def is_telegram_secret_id(value: Any) -> bool:
    return isinstance(value, str) and (
        value == "telegram.bot_token"
        or (value.startswith("telegram.profiles.") and value.endswith(".bot_token"))
    )


def require_telegram_token_text(value: Any) -> str:
    if not isinstance(value, str):
        raise SystemExit("Telegram bot token input must be text. Nothing was changed.")
    return value


def validated_telegram_response(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit("Telegram returned an unexpected token-validation response. Nothing was changed.")
    return value


def require_module_manifest(module: Any) -> None:
    if module is None or not isinstance(getattr(module, "manifest", None), dict):
        raise SystemExit("Secret binding resolution requires a valid module manifest.")
