from __future__ import annotations

from spark_cli.env_files import normalize_env_file_value


def test_normalize_env_file_value_strips_surrounding_whitespace() -> None:
    assert normalize_env_file_value("  hello  ") == "hello"


def test_normalize_env_file_value_strips_matching_single_quotes() -> None:
    assert normalize_env_file_value("'wrapped'") == "wrapped"
    assert normalize_env_file_value("  'spaced'  ") == "spaced"


def test_normalize_env_file_value_strips_matching_double_quotes() -> None:
    assert normalize_env_file_value('"wrapped"') == "wrapped"


def test_normalize_env_file_value_preserves_mismatched_quotes() -> None:
    assert normalize_env_file_value("'mismatch\"") == "'mismatch\""
    assert normalize_env_file_value("\"only-left") == "\"only-left"


def test_normalize_env_file_value_handles_empty_quoted_value() -> None:
    assert normalize_env_file_value("''") == ""
    assert normalize_env_file_value('""') == ""


def test_normalize_env_file_value_leaves_inner_quotes_alone() -> None:
    assert normalize_env_file_value('"hello \'world\'"') == "hello 'world'"
