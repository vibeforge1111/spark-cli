from __future__ import annotations

from unittest.mock import patch

from spark_cli.cli import delete_secret


class DeleteKeyring:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.accounts: list[str] = []

    def delete_password(self, _service: str, account: str) -> None:
        self.accounts.append(account)
        if account in self.failures:
            raise RuntimeError("private backend detail")


def test_keychain_delete_failure_preserves_index_for_retry() -> None:
    keyring = DeleteKeyring({"example"})
    with patch("spark_cli.cli.HAS_KEYRING", True), patch("spark_cli.cli._keyring", keyring), patch(
        "spark_cli.cli.load_secrets_index", return_value={"example": "keychain"}
    ), patch("spark_cli.cli.keychain_account", return_value="example"), patch(
        "spark_cli.cli.default_home_uses_legacy_keychain", return_value=False
    ), patch("spark_cli.cli.save_secrets_index") as save_index:
        assert not delete_secret("example")

    assert keyring.accounts == ["example"]
    save_index.assert_not_called()


def test_partial_legacy_keychain_delete_preserves_index_for_retry() -> None:
    keyring = DeleteKeyring({"example"})
    with patch("spark_cli.cli.HAS_KEYRING", True), patch("spark_cli.cli._keyring", keyring), patch(
        "spark_cli.cli.load_secrets_index", return_value={"example": "keychain"}
    ), patch("spark_cli.cli.keychain_account", return_value="current-example"), patch(
        "spark_cli.cli.default_home_uses_legacy_keychain", return_value=True
    ), patch("spark_cli.cli.save_secrets_index") as save_index:
        assert not delete_secret("example")

    assert keyring.accounts == ["current-example", "example"]
    save_index.assert_not_called()


def test_all_required_keychain_deletes_remove_index_once() -> None:
    keyring = DeleteKeyring()
    with patch("spark_cli.cli.HAS_KEYRING", True), patch("spark_cli.cli._keyring", keyring), patch(
        "spark_cli.cli.load_secrets_index", return_value={"example": "keychain", "other": "file"}
    ), patch("spark_cli.cli.keychain_account", return_value="current-example"), patch(
        "spark_cli.cli.default_home_uses_legacy_keychain", return_value=True
    ), patch("spark_cli.cli.save_secrets_index") as save_index:
        assert delete_secret("example")

    assert keyring.accounts == ["current-example", "example"]
    save_index.assert_called_once_with({"other": "file"})


def test_missing_file_backend_value_preserves_index_for_retry() -> None:
    with patch("spark_cli.cli.load_secrets_index", return_value={"example": "file"}), patch(
        "spark_cli.cli.load_json", return_value={}
    ), patch("spark_cli.cli.save_secrets_index") as save_index:
        assert not delete_secret("example")

    save_index.assert_not_called()
