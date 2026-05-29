"""Tests for @file: secret path boundary restriction."""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch


class TestAtfileBoundary:
    """Verify @file: reads are restricted to SPARK_HOME."""

    def test_atfile_allows_path_inside_spark_home(self, monkeypatch):
        """@file: with a path inside SPARK_HOME should succeed."""
        from spark_cli.cli import resolve_secret_input

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            secret_file = home / "secret.txt"
            secret_file.write_text("my_secret_value")

            monkeypatch.setattr(
                "spark_cli.cli.SPARK_HOME",
                home,
            )

            result = resolve_secret_input(f"@file:{secret_file}")
            assert result == "my_secret_value"

    def test_atfile_rejects_path_outside_spark_home(self, monkeypatch):
        """@file: with a path outside SPARK_HOME should raise SystemExit."""
        from spark_cli.cli import resolve_secret_input

        with tempfile.TemporaryDirectory() as home_tmp, \
             tempfile.TemporaryDirectory() as outside_tmp:
            home = Path(home_tmp)
            outside_file = Path(outside_tmp) / "outside.txt"
            outside_file.write_text("should_not_read")

            monkeypatch.setattr(
                "spark_cli.cli.SPARK_HOME",
                home,
            )

            with pytest.raises(SystemExit, match="must be inside SPARK_HOME"):
                resolve_secret_input(f"@file:{outside_file}")

    def test_atfile_handles_nonexistent_file(self, monkeypatch):
        """@file: with a nonexistent path should raise SystemExit."""
        from spark_cli.cli import resolve_secret_input

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            monkeypatch.setattr(
                "spark_cli.cli.SPARK_HOME",
                home,
            )

            with pytest.raises(SystemExit):
                resolve_secret_input("@file:/nonexistent/path/secret.txt")

    def test_atfile_normal_value_passes_through(self):
        """Non-@file: values are returned unchanged."""
        from spark_cli.cli import resolve_secret_input

        assert resolve_secret_input("plain_value") == "plain_value"
        assert resolve_secret_input("") == ""
