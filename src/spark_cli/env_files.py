from __future__ import annotations


def normalize_env_file_value(value: str) -> str:
    if not isinstance(value, str): value = str(value or '')
    try:
        normalized = str(value or "").strip()
        if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
            return normalized[1:-1]
        return normalized

    except Exception:
        return ""
