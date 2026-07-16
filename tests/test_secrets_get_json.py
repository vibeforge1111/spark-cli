"""Regression coverage for value-free secret-presence JSON."""

import json
from io import StringIO
from unittest.mock import patch

import pytest

from spark_cli.cli import build_parser


def run_secret_get(argv: list[str], value: str | None) -> tuple[int, str]:
    args = build_parser().parse_args(argv)
    with patch("spark_cli.cli.fetch_secret", return_value=value), patch(
        "sys.stdout", new_callable=StringIO
    ) as output:
        code = args.func(args)
    return code, output.getvalue()


def test_secrets_get_json_reports_missing_without_human_text() -> None:
    code, output = run_secret_get(["secrets", "get", "missing.key", "--json"], None)
    assert code == 1
    assert json.loads(output) == {
        "ok": False,
        "secret_id": "missing.key",
        "set": False,
        "masked_value": None,
    }


def test_secrets_get_json_never_derives_output_from_secret_value() -> None:
    value = "prefix-private-secret-suffix"
    code, output = run_secret_get(["secrets", "get", "telegram.bot_token", "--json"], value)
    assert code == 0
    assert json.loads(output) == {
        "ok": True,
        "secret_id": "telegram.bot_token",
        "set": True,
        "masked_value": "***",
    }
    assert value not in output
    assert "prefix" not in output
    assert "suffix" not in output


def test_secrets_get_reveal_and_json_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["secrets", "get", "telegram.bot_token", "--reveal", "--json"])
    assert error.value.code == 2


def test_secrets_get_plain_masking_remains_compatible() -> None:
    code, output = run_secret_get(["secrets", "get", "telegram.bot_token"], "abcdefghij")
    assert code == 0
    assert output == "telegram.bot_token -> abcd...ij (pass --reveal to print full value)\n"
