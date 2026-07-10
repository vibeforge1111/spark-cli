"""Tests for relay secret configured marker."""
from unittest.mock import patch


def test_relay_marker_written_when_keychain_has_secret():
    """SPARK_RELAY_SECRET_CONFIGURED=1 written when TELEGRAM_RELAY_SECRET is keychain-backed."""
    from spark_cli.cli import strip_keychain_env_vars
    
    env_values = {"TELEGRAM_RELAY_SECRET": "test-secret-value"}
    
    with patch('spark_cli.cli.split_secret_bindings') as mock_split:
        mock_split.return_value = (
            [],
            [{"env_var": "TELEGRAM_RELAY_SECRET", "secret_id": "relay-secret"}]
        )
        result = strip_keychain_env_vars(env_values, {})
    
    assert "SPARK_RELAY_SECRET_CONFIGURED" in result
    assert result["SPARK_RELAY_SECRET_CONFIGURED"] == "1"
    assert "TELEGRAM_RELAY_SECRET" not in result


def test_relay_marker_not_written_when_no_secret():
    """SPARK_RELAY_SECRET_CONFIGURED not written when TELEGRAM_RELAY_SECRET is absent."""
    from spark_cli.cli import strip_keychain_env_vars
    
    env_values = {"OTHER_VAR": "value"}
    
    with patch('spark_cli.cli.split_secret_bindings') as mock_split:
        mock_split.return_value = ([], [])
        result = strip_keychain_env_vars(env_values, {})
    
    assert "SPARK_RELAY_SECRET_CONFIGURED" not in result
    assert result == env_values


def test_relay_marker_not_written_when_secret_is_empty():
    """SPARK_RELAY_SECRET_CONFIGURED not written when TELEGRAM_RELAY_SECRET value is empty."""
    from spark_cli.cli import strip_keychain_env_vars
    
    env_values = {"TELEGRAM_RELAY_SECRET": ""}
    
    with patch('spark_cli.cli.split_secret_bindings') as mock_split:
        mock_split.return_value = (
            [],
            [{"env_var": "TELEGRAM_RELAY_SECRET", "secret_id": "relay-secret"}]
        )
        result = strip_keychain_env_vars(env_values, {})
    
    assert "SPARK_RELAY_SECRET_CONFIGURED" not in result
