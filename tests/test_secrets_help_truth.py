from __future__ import annotations

from spark_cli.cli import build_parser


def test_secrets_set_help_explains_id_and_backend_without_false_encryption_claim() -> None:
    parser = build_parser()
    secrets = parser._subparsers._group_actions[0].choices["secrets"]
    set_parser = secrets._subparsers._group_actions[0].choices["set"]
    help_text = set_parser.format_help()

    assert "telegram.bot_token" in help_text
    assert "OS keychain" in help_text
    assert "DPAPI-protected on Windows" in help_text
    assert "insecure opt-in elsewhere" in help_text
    assert "encrypted file fallback" not in help_text
