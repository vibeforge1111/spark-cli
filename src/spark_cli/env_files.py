from __future__ import annotations

import re
from typing import Any


ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_KEY_ERROR = (
    "Environment file keys must use letters, numbers, and underscores and cannot start with a number. "
    "Nothing was written."
)
ENV_VALUE_ERROR = "Environment file values must be single-line text. Nothing was written."


def normalize_env_file_value(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        return normalized[1:-1]
    return normalized


def serialize_env_assignment(key: Any, value: Any) -> str:
    if not isinstance(key, str) or not ENV_KEY_PATTERN.fullmatch(key):
        raise SystemExit(ENV_KEY_ERROR)
    if not isinstance(value, str) or any(character in value for character in ("\r", "\n", "\x00")):
        raise SystemExit(ENV_VALUE_ERROR)
    return f"{key}={value}"


def serialize_env_file(values: Any) -> str:
    if not isinstance(values, dict):
        raise SystemExit(ENV_VALUE_ERROR)
    return "\n".join(serialize_env_assignment(key, value) for key, value in values.items()) + "\n"


def decode_env_file_bytes(payload: bytes) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return payload.decode("cp1252")


def parse_env_file_bytes(payload: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in decode_env_file_bytes(payload).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip().lstrip("\ufeff")] = normalize_env_file_value(value)
    return values
