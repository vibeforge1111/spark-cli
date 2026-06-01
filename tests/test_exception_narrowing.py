"""Tests for exception narrowing in secret store and git tools."""
import subprocess
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestKeyringExceptionNarrowing:
    """Verify keyring functions catch KeyringError instead of blanket Exception."""

    def test_keychain_available_handles_keyring_error(self):
        """keychain_available returns False on KeyringError, not blanket Exception."""
        from spark_cli.cli import keychain_available
        import keyring.errors

        with patch("spark_cli.cli._keyring") as mock_keyring:
            mock_keyring.get_password.side_effect = keyring.errors.KeyringError("test")
            result = keychain_available()
            assert result is False

    def test_fetch_secret_handles_keyring_error(self):
        """fetch_secret returns None on KeyringError."""
        from spark_cli.cli import fetch_secret
        import keyring.errors

        with patch("spark_cli.cli._keyring") as mock_kr, \
             patch("spark_cli.cli.load_json") as mock_load, \
             patch("spark_cli.cli.load_secrets_index") as mock_idx:
            mock_idx.return_value = {"test_key": "keychain"}
            mock_kr.get_password.side_effect = keyring.errors.KeyringError("test")
            mock_load.return_value = {}
            result = fetch_secret("test_key")
            assert result is None

    def test_store_secret_handles_keyring_failure(self):
        """store_secret catches KeyringError without crashing."""
        from spark_cli.cli import store_secret
        import keyring.errors

        with patch.dict(os.environ, {"SPARK_ALLOW_INSECURE_FILE_SECRETS": "1"}), \
             patch("spark_cli.cli.ensure_state_dirs"), \
             patch("spark_cli.cli.load_secrets_index") as mock_idx, \
             patch("spark_cli.cli.save_secrets_index"), \
             patch("spark_cli.cli.load_json") as mock_load, \
             patch("spark_cli.cli.save_json"), \
             patch("spark_cli.cli.keychain_available") as mock_ka, \
             patch("spark_cli.cli._keyring") as mock_kr:
            mock_ka.return_value = True
            mock_idx.return_value = {}
            mock_load.return_value = {}
            mock_kr.set_password.side_effect = keyring.errors.KeyringError("test")

            result = store_secret("narrow_test_key", "test_value")
            assert result in ("keychain", "file")


class TestGitExceptionNarrowing:
    """Verify git_summary catches specific subprocess/OS errors."""

    def test_git_summary_handles_subprocess_error(self):
        """git_summary handles SubprocessError gracefully."""
        from spark_cli.system_map import git_summary

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir()
            with patch("spark_cli.system_map.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.SubprocessError("git not found")
                result = git_summary(repo)
                assert result["available"] is True
                assert result["head_short"] is None

    def test_git_summary_handles_os_error(self):
        """git_summary handles OSError gracefully."""
        from spark_cli.system_map import git_summary

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir()
            with patch("spark_cli.system_map.subprocess.run") as mock_run:
                mock_run.side_effect = OSError("permission denied")
                result = git_summary(repo)
                assert result["available"] is True
                assert result["head_short"] is None

    def test_git_summary_no_git_dir(self):
        """git_summary returns unavailable when .git directory is missing."""
        from spark_cli.system_map import git_summary

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = git_summary(repo)
            assert result["available"] is False
