from __future__ import annotations


def normalize_env_file_value(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        inner = normalized[1:-1]
        # Unescape escaped quotes that match the outer delimiter
        inner = inner.replace("\\" + normalized[0], normalized[0])
        return inner
    return normalized
