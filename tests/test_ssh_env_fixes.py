from __future__ import annotations

import unittest

from spark_cli.env_files import normalize_env_file_value
from spark_cli.sandbox.ssh import (
    SSH_REMOTE_WORKSPACE_PATTERN,
    validate_remote_workspace,
)


class SshRemoteWorkspacePatternTests(unittest.TestCase):
    """Verify the SSH remote workspace pattern rejects dangerous characters."""

    def test_allows_valid_paths(self) -> None:
        valid = [
            "~/spark-live",
            "/home/user/project",
            "/opt/apps/my-app",
            "~/.config/spark",
            "/data/my_project/sub",
        ]
        for path in valid:
            self.assertIsNotNone(
                SSH_REMOTE_WORKSPACE_PATTERN.fullmatch(path),
                f"Expected valid path to match: {path}",
            )

    def test_rejects_percent_sign(self) -> None:
        path = "~/project%injection"
        self.assertIsNone(
            SSH_REMOTE_WORKSPACE_PATTERN.fullmatch(path),
            "Path with % should not match.",
        )

    def test_rejects_equals_sign(self) -> None:
        path = "/home/user=evil"
        self.assertIsNone(
            SSH_REMOTE_WORKSPACE_PATTERN.fullmatch(path),
            "Path with = should not match.",
        )

    def test_validate_rejects_percent_path(self) -> None:
        with self.assertRaises(ValueError):
            validate_remote_workspace("~/bad%path")

    def test_validate_rejects_equals_path(self) -> None:
        with self.assertRaises(ValueError):
            validate_remote_workspace("/home/user=escalate")


class NormalizeEnvFileValueTests(unittest.TestCase):
    """Verify normalize_env_file_value handles escaped quotes."""

    def test_plain_value(self) -> None:
        self.assertEqual(normalize_env_file_value("hello"), "hello")

    def test_strips_whitespace(self) -> None:
        self.assertEqual(normalize_env_file_value("  hello  "), "hello")

    def test_double_quoted_value(self) -> None:
        self.assertEqual(normalize_env_file_value('"hello"'), "hello")

    def test_single_quoted_value(self) -> None:
        self.assertEqual(normalize_env_file_value("'hello'"), "hello")

    def test_escaped_double_quote_inside_double_quotes(self) -> None:
        self.assertEqual(
            normalize_env_file_value(r'"say \"hello\""'), 'say "hello"'
        )

    def test_escaped_single_quote_inside_single_quotes(self) -> None:
        self.assertEqual(
            normalize_env_file_value(r"'it\'s fine'"), "it's fine"
        )

    def test_escaped_opposite_quote_not_unescaped(self) -> None:
        # An escaped single-quote inside double quotes is left as-is
        self.assertEqual(
            normalize_env_file_value(r'"hello \'world\'"'), r"hello \'world\'"
        )

    def test_unbalanced_quote_treated_as_literal(self) -> None:
        self.assertEqual(normalize_env_file_value('"hello'), '"hello')

    def test_single_char_not_stripped(self) -> None:
        self.assertEqual(normalize_env_file_value('"'), '"')


if __name__ == "__main__":
    unittest.main()
