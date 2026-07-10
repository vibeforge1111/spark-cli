"""Tests for registry module name validation against path traversal."""
import pytest
from pathlib import Path
from unittest.mock import patch
from spark_cli.cli import MODULE_NAME_RE, clone_target_for_module


class TestModuleNameValidation:
    """Verify registry module names are validated against path traversal."""

    def test_valid_module_names_pass(self):
        """Valid lowercase alphanumeric + hyphen names are accepted."""
        valid = ["spark", "spark-telegram-bot", "a", "ab", "a-b",
                  "my-module", "x1", "test-123", "foo-bar-baz"]
        for name in valid:
            assert MODULE_NAME_RE.fullmatch(name), f"'{name}' should be valid"

    def test_path_traversal_patterns_rejected(self):
        """Names with path traversal characters are rejected."""
        invalid = ["../etc", "a/../b", "..", "./hidden",
                    "/etc/passwd", "a\\b", "a;rm -rf", "../../root"]
        for name in invalid:
            assert not MODULE_NAME_RE.fullmatch(name), f"'{name}' should be rejected"

    def test_uppercase_and_special_chars_rejected(self):
        """Uppercase, spaces, and special characters are rejected."""
        invalid = ["Module", "SPARK", "my module", "mod@ule",
                    "mod!", "mod#", "mod$", "", "-mod", "mod-"]
        for name in invalid:
            assert not MODULE_NAME_RE.fullmatch(name), f"'{name}' should be rejected"

    def test_clone_target_validates_before_returning_path(self):
        """clone_target_for_module rejects invalid names with SystemExit."""
        with pytest.raises(SystemExit, match="Invalid module name"):
            clone_target_for_module("../traversal")

    def test_clone_target_returns_correct_path(self):
        """clone_target_for_module returns SPARK_HOME/modules/<name>/source."""
        result = clone_target_for_module("my-module")
        assert result.name == "source"
        assert "my-module" in str(result)
        assert "modules" in str(result)
