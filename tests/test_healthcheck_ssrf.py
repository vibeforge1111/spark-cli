"""Tests for healthcheck URL SSRF protection."""
import urllib.parse
import pytest
from spark_cli.cli import _is_allowed_healthcheck_host


class TestHealthcheckUrlAllowlist:
    """Verify healthcheck HTTP probes are restricted to local/safe hosts."""

    def test_localhost_allowed(self):
        """127.0.0.1, localhost, and ::1 pass the allowlist."""
        for host in ["127.0.0.1", "localhost", "::1"]:
            assert _is_allowed_healthcheck_host(host), f"{host} should be allowed"

    def test_dot_local_allowed(self):
        """Hostnames ending in .local pass the allowlist."""
        for host in ["spawner.local", "myapp.local", "x.local"]:
            assert _is_allowed_healthcheck_host(host), f"{host} should be allowed"

    def test_dot_internal_allowed(self):
        """Hostnames ending in .internal pass the allowlist."""
        for host in ["spawner.internal", "svc.internal"]:
            assert _is_allowed_healthcheck_host(host), f"{host} should be allowed"

    def test_external_hosts_blocked(self):
        """Public and external hostnames are blocked."""
        blocked = ["example.com", "api.openai.com", "192.168.1.1",
                    "10.0.0.1", "spawner.home", "google.com"]
        for host in blocked:
            assert not _is_allowed_healthcheck_host(host), f"{host} should be blocked"

    def test_empty_hostname_blocked(self):
        """Missing or empty hostname is blocked."""
        for host in [None, ""]:
            assert not _is_allowed_healthcheck_host(host), f"hostname={host!r} should be blocked"
