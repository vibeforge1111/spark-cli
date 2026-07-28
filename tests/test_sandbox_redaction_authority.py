from __future__ import annotations

import pytest

from spark_cli.sandbox.output import redact_sandbox_text


@pytest.mark.parametrize(
    ("rendered", "secret"),
    (
        ("aws_secret_access_key: synthetic-secret-access-value", "synthetic-secret-access-value"),
        ("password: synthetic-password-value", "synthetic-password-value"),
        ("api-key: synthetic-api-key-value", "synthetic-api-key-value"),
        ("Authorization: Token custom-token-secret-value", "custom-token-secret-value"),
        ("Authorization: ApiKey custom-apikey-secret-value", "custom-apikey-secret-value"),
        ("Authorization: Api-Key custom-api-key-secret-value", "custom-api-key-secret-value"),
        ("Authorization: OAuth custom-oauth-secret-value", "custom-oauth-secret-value"),
        ('{"api_key": "synthetic-json-api-key-value"}', "synthetic-json-api-key-value"),
        ('{"access_token": "synthetic-json-access-token-value"}', "synthetic-json-access-token-value"),
        ('{"refresh-token": "synthetic-json-refresh-token-value"}', "synthetic-json-refresh-token-value"),
        ('{"clientSecret": "synthetic-json-client-secret-value"}', "synthetic-json-client-secret-value"),
        ("{'api_key': 'synthetic-repr-api-key-value'}", "synthetic-repr-api-key-value"),
        ("{'access_token': 'synthetic-repr-access-token-value'}", "synthetic-repr-access-token-value"),
        ("{'client_secret': 'synthetic-repr-client-secret-value'}", "synthetic-repr-client-secret-value"),
    ),
)
def test_sandbox_redaction_covers_structured_secret_reports(rendered: str, secret: str) -> None:
    redacted = redact_sandbox_text(rendered)

    assert secret not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.parametrize(
    "ordinary",
    (
        "monkey: banana",
        "author: alice",
        "tokenizer: wordpiece",
        "Authorization: Digest username=guest",
    ),
)
def test_sandbox_redaction_does_not_treat_ordinary_suffixes_or_authors_as_secrets(ordinary: str) -> None:
    assert redact_sandbox_text(ordinary) == ordinary
