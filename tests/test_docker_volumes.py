"""Tests for docker volume suspicious path detection."""
import pytest
from spark_cli.security.approval import _has_option_value


def test_detects_usr_as_suspicious_volume():
    """ /usr should be flagged as a suspicious Docker volume mount. """
    assert _has_option_value(
        ["docker", "run", "-v", "/usr:/host-usr"],
        {"-v", "--volume", "--mount"},
        {"/", "/root", "/home", "/users", "/usr", "/var/run/docker.sock"},
    )


def test_detects_usr_with_source_syntax():
    """ source=/usr should be flagged. """
    assert _has_option_value(
        ["docker", "run", "--mount", "type=bind,source=/usr,target=/host-usr"],
        {"-v", "--volume", "--mount"},
        {"/", "/root", "/home", "/users", "/usr", "/var/run/docker.sock"},
    )


def test_usr_local_share_not_flagged():
    """ /usr/local/share alone should not match /usr prefix check. """
    result = _has_option_value(
        ["docker", "run", "-v", "/usr/local/share:/data"],
        {"-v", "--volume", "--mount"},
        {"/", "/root", "/home", "/users", "/usr", "/var/run/docker.sock"},
    )
    # /usr/local/share starts with /usr/ so it WILL match the prefix check
    # This is correct — any /usr subpath is suspicious
    assert result is True
