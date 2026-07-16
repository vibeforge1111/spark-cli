from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import delete_secret, fetch_secret, keychain_available


class ReadOnlyProbeKeyring:
    def __init__(self) -> None:
        self.reads: list[tuple[str, str]] = []

    def get_password(self, service: str, account: str) -> str | None:
        self.reads.append((service, account))
        return None

    def set_password(self, *_: object) -> None:
        raise AssertionError("availability probes must not write")

    def delete_password(self, *_: object) -> None:
        raise AssertionError("availability probes must not delete")


def test_keychain_availability_probe_remains_read_only() -> None:
    keyring = ReadOnlyProbeKeyring()

    with patch("spark_cli.cli.HAS_KEYRING", True), patch("spark_cli.cli._keyring", keyring):
        assert keychain_available()

    assert keyring.reads == [("spark-cli", "__spark_probe__")]


def test_keychain_availability_failure_reports_only_error_type() -> None:
    class FailingKeyring:
        def get_password(self, *_: object) -> str | None:
            raise RuntimeError("private-value /Users/example/Library/Keychains/login.keychain-db")

    stderr = StringIO()
    with patch("spark_cli.cli.HAS_KEYRING", True), patch("spark_cli.cli._keyring", FailingKeyring()), redirect_stderr(stderr):
        assert not keychain_available()

    warning = stderr.getvalue()
    assert "system store availability check failed" in warning
    assert "RuntimeError" in warning
    assert "private-value" not in warning
    assert "/Users/example" not in warning
    assert "Traceback" not in warning


def test_fetch_secret_uses_the_target_read_without_an_availability_probe() -> None:
    class FetchKeyring:
        def get_password(self, _service: str, _account: str) -> str:
            return "stored-secret"

    with (
        patch("spark_cli.cli.HAS_KEYRING", True),
        patch("spark_cli.cli._keyring", FetchKeyring()),
        patch("spark_cli.cli.load_secrets_index", return_value={"example": "keychain"}),
        patch("spark_cli.cli.keychain_available", side_effect=AssertionError("unexpected availability probe")),
    ):
        assert fetch_secret("example") == "stored-secret"


def test_delete_secret_uses_the_target_delete_without_an_availability_probe() -> None:
    class DeleteKeyring:
        def __init__(self) -> None:
            self.deleted = False

        def delete_password(self, _service: str, _account: str) -> None:
            self.deleted = True

    keyring = DeleteKeyring()
    with (
        patch("spark_cli.cli.HAS_KEYRING", True),
        patch("spark_cli.cli._keyring", keyring),
        patch("spark_cli.cli.load_secrets_index", return_value={"example": "keychain"}),
        patch("spark_cli.cli.save_secrets_index") as save_index,
        patch("spark_cli.cli.default_home_uses_legacy_keychain", return_value=False),
        patch("spark_cli.cli.keychain_available", side_effect=AssertionError("unexpected availability probe")),
    ):
        assert delete_secret("example")

    assert keyring.deleted
    save_index.assert_called_once_with({})
