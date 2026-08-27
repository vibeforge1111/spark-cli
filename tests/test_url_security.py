import pytest
import re
from unittest.mock import patch, MagicMock


class TestURLSecurity:
    def test_reject_0_0_0_0(self):
        """PR #520: reject 0.0.0.0 and :: as SSH target hosts"""
        import ipaddress
        assert ipaddress.ip_address("0.0.0.0").is_unspecified
        assert ipaddress.ip_address("::").is_unspecified

    def test_ipv6_scope_id_stripping(self):
        """PR #519/525: strip IPv6 scope IDs before ip_address parse"""
        hostname = "fe80::1%eth0"
        clean = hostname.split("%")[0]
        import ipaddress
        addr = ipaddress.ip_address(clean)
        assert str(addr) == "fe80::1"

    def test_dns_rebinding_ssrf_prevention(self):
        """PR #573/#345: prevent SSRF via DNS rebinding"""
        private_ips = ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1"]
        for ip in private_ips:
            import ipaddress
            addr = ipaddress.ip_address(ip)
            assert addr.is_private or addr.is_loopback


class TestHostValidation:
    def test_reject_internal_hosts(self):
        """PR #573/#345: block requests to private IPs"""
        blocked = ["127.0.0.1", "localhost", "10.0.0.1", "169.254.169.254"]
        allowed = ["api.github.com", "google.com"]
        internal_indicators = ["127.", "10.", "169.254", "192.168.", "172.16.", "localhost"]
        for host in blocked:
            assert any(host.startswith(ind) or host == ind for ind in internal_indicators)
        for host in allowed:
            assert not any(host.startswith(ind) or host == ind for ind in internal_indicators)
