import unittest
from unittest.mock import patch

from spark_cli.cli import store_secret


class SecretStoreTests(unittest.TestCase):
    def test_unchanged_keychain_secret_is_not_rewritten(self) -> None:
        with (
            patch("spark_cli.cli.ensure_state_dirs"),
            patch("spark_cli.cli.load_secrets_index", return_value={"telegram.bot_token": "keychain"}),
            patch("spark_cli.cli.fetch_secret", return_value="same-secret"),
            patch("spark_cli.cli.keychain_available") as keychain_available,
            patch("spark_cli.cli.save_secrets_index") as save_index,
        ):
            backend = store_secret("telegram.bot_token", "same-secret", preferred="keychain")

        self.assertEqual(backend, "keychain")
        keychain_available.assert_not_called()
        save_index.assert_not_called()


if __name__ == "__main__":
    unittest.main()
