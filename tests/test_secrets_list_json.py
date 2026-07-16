"""Regression coverage for machine-readable secret metadata."""

import json
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import build_parser


def test_secrets_list_json_is_structured_and_value_free() -> None:
    args = build_parser().parse_args(["secrets", "list", "--json"])
    with patch(
        "spark_cli.cli.list_stored_secrets",
        return_value={"telegram.bot_token": "keychain", "llm.api_key": "file"},
    ), patch("sys.stdout", new_callable=StringIO) as output:
        assert args.func(args) == 0

    payload = json.loads(output.getvalue())
    assert payload == {
        "ok": True,
        "count": 2,
        "secrets": [
            {"id": "llm.api_key", "backend": "file"},
            {"id": "telegram.bot_token", "backend": "keychain"},
        ],
    }
    assert "value" not in output.getvalue().lower()


def test_secrets_list_json_empty_state_is_success() -> None:
    args = build_parser().parse_args(["secrets", "list", "--json"])
    with patch("spark_cli.cli.list_stored_secrets", return_value={}), patch(
        "sys.stdout", new_callable=StringIO
    ) as output:
        assert args.func(args) == 0
    assert json.loads(output.getvalue()) == {"ok": True, "count": 0, "secrets": []}


def test_secrets_list_json_flag_does_not_change_plain_output_contract() -> None:
    args = build_parser().parse_args(["secrets", "list"])
    with patch(
        "spark_cli.cli.list_stored_secrets",
        return_value={"telegram.bot_token": "keychain"},
    ), patch("sys.stdout", new_callable=StringIO) as output:
        assert args.func(args) == 0

    assert output.getvalue() == "1 secret stored:\n  telegram.bot_token\t[keychain]\n"
