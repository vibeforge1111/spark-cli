from __future__ import annotations

import unittest

from spark_cli.env_files import normalize_env_file_value


class NormalizeEnvFileValueTests(unittest.TestCase):
    def test_strips_surrounding_whitespace(self) -> None:
        self.assertEqual(normalize_env_file_value("  hello  "), "hello")
        self.assertEqual(normalize_env_file_value("\tindented\n"), "indented")

    def test_strips_matching_double_quotes(self) -> None:
        self.assertEqual(normalize_env_file_value('"quoted"'), "quoted")
        self.assertEqual(normalize_env_file_value('  "padded"  '), "padded")

    def test_strips_matching_single_quotes(self) -> None:
        self.assertEqual(normalize_env_file_value("'single'"), "single")
        self.assertEqual(normalize_env_file_value(" 'spaced' "), "spaced")

    def test_preserves_unmatched_quotes(self) -> None:
        # Leading-only quote: must NOT be stripped.
        self.assertEqual(normalize_env_file_value('"leading-only'), '"leading-only')
        # Trailing-only quote: must NOT be stripped.
        self.assertEqual(normalize_env_file_value("trailing-only'"), "trailing-only'")
        # Mixed quotes: outer chars differ, leave as-is.
        self.assertEqual(normalize_env_file_value("'mixed\""), "'mixed\"")

    def test_handles_empty_and_quote_only_inputs(self) -> None:
        self.assertEqual(normalize_env_file_value(""), "")
        # Whitespace-only collapses to "".
        self.assertEqual(normalize_env_file_value("   "), "")
        # A single quote character has length 1 -- no stripping.
        self.assertEqual(normalize_env_file_value('"'), '"')
        self.assertEqual(normalize_env_file_value("'"), "'")
        # Two matching quotes -> empty payload between them.
        self.assertEqual(normalize_env_file_value('""'), "")
        self.assertEqual(normalize_env_file_value("''"), "")

    def test_only_strips_one_outer_quote_pair(self) -> None:
        # Nested quotes: outer pair removed, inner pair preserved.
        self.assertEqual(normalize_env_file_value('"\'inner\'"'), "'inner'")
        self.assertEqual(normalize_env_file_value("'\"inner\"'"), '"inner"')

    def test_preserves_embedded_whitespace_and_special_chars(self) -> None:
        self.assertEqual(
            normalize_env_file_value('"value with spaces"'),
            "value with spaces",
        )
        self.assertEqual(
            normalize_env_file_value("'a=b;c=d'"),
            "a=b;c=d",
        )


if __name__ == "__main__":
    unittest.main()
