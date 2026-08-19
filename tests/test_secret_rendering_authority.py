from __future__ import annotations

import pytest

from spark_cli.cli import extract_telegram_bot_token
from spark_cli.sandbox.output import redact_sandbox_text
from spark_cli.system_map import safe_short_string


TELEGRAM_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


@pytest.mark.parametrize(
    "value",
    (
        TELEGRAM_TOKEN,
        f"bot{TELEGRAM_TOKEN}",
        f"bot{TELEGRAM_TOKEN}-",
    ),
)
def test_telegram_tokens_are_fully_redacted_without_identifier_fragments(value: str) -> None:
    rendered = redact_sandbox_text(value)

    assert rendered == "[REDACTED]"
    assert "1234" not in rendered
    assert "fghi" not in rendered


def test_telegram_token_is_fully_redacted_before_named_value_masking() -> None:
    rendered = redact_sandbox_text(f"BOT_TOKEN=bot{TELEGRAM_TOKEN}")

    assert rendered == "BOT_TOKEN=[REDACTED]"
    assert "1234" not in rendered
    assert "fghi" not in rendered


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("password=supersecret", "password=[redacted]"),
        ("private_key: abcdef", "private_key: [redacted]"),
        ("credential value", "credential [redacted]"),
        ('{"auth_code": "two word code"}', '{"auth_code": [redacted]}'),
        ("access-key='cloud secret'", "access-key=[redacted]"),
        ("AUTHOR: alice", "AUTHOR: alice"),
    ),
)
def test_safe_short_string_redacts_named_secret_values_without_broad_auth_matches(
    value: str,
    expected: str,
) -> None:
    assert safe_short_string(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "not-a-token",
        "https://example.invalid/no-token",
        "arbitrary\nmultiline text",
        "$(touch should-never-be-a-token)",
    ),
)
def test_extract_telegram_bot_token_rejects_nonmatching_input_without_reflection(value: str) -> None:
    with pytest.raises(SystemExit) as caught:
        extract_telegram_bot_token(value)

    message = str(caught.value)
    assert value not in message
    assert "Telegram bot token" in message


def test_extract_telegram_bot_token_preserves_single_botfather_token() -> None:
    copied = f"Done! Use this token to access the HTTP API:\n{TELEGRAM_TOKEN}"

    assert extract_telegram_bot_token(copied) == TELEGRAM_TOKEN
