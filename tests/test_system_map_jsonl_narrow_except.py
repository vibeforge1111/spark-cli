"""Test: narrow except to json.JSONDecodeError."""
import json

def test_jsonl_parse_error_with_narrow_except():
    invalid_lines = ["not json", "{invalid}", ""]
    errors = 0
    for line in invalid_lines:
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            errors += 1
    assert errors == 2

def test_jsonl_parse_valid_json():
    valid_lines = ['{"a": 1}', '{"b": 2}', '{"c": 3}']
    parsed = 0
    for line in valid_lines:
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                parsed += 1
        except json.JSONDecodeError:
            pass
    assert parsed == 3
