"""Regression coverage for the real ``spark secrets list`` surface."""

from argparse import Namespace
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import cmd_secrets_list


def render_secret_list(index: dict[str, str]) -> str:
    with patch("spark_cli.cli.list_stored_secrets", return_value=index), patch(
        "sys.stdout", new_callable=StringIO
    ) as output:
        assert cmd_secrets_list(Namespace()) == 0
    return output.getvalue()


def test_singular_secret_header() -> None:
    assert render_secret_list({"one": "file"}).splitlines()[0] == "1 secret stored:"


def test_plural_secret_header() -> None:
    assert render_secret_list({"one": "file", "two": "keychain"}).splitlines()[0] == "2 secrets stored:"


def test_zero_secrets_shows_no_header() -> None:
    assert render_secret_list({}) == "No stored secrets.\n"
