from __future__ import annotations

import unittest

import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from spark_cli.security.url_policy import (
    UrlPolicy,
    resolve_host_addresses,
    validate_local_health_url,
    validate_url_resolution,
    validate_url_safety,
)


class UrlPolicyTests(unittest.TestCase):
    def test_legacy_ipv4_loopback_forms_cannot_bypass_hosted_policy(self) -> None:
        for host in ("0177.0.0.1", "0x7f000001", "127.1", "2130706433"):
            with self.subTest(host=host):
                errors = validate_url_safety(
                    f"http://{host}/",
                    label="health check",
                    policy=UrlPolicy(allow_local=False, require_https_for_remote=False),
                )
                self.assertTrue(any("local-only" in error for error in errors), errors)

    def test_legacy_ipv4_private_forms_cannot_bypass_remote_policy(self) -> None:
        for host in ("012.0.0.1", "0x0a000001", "10.1"):
            with self.subTest(host=host):
                errors = validate_url_safety(
                    f"https://{host}/",
                    label="provider endpoint",
                    policy=UrlPolicy(allow_local=False),
                )
                self.assertTrue(any("private network" in error for error in errors), errors)

    def test_aws_ipv6_metadata_address_is_explicitly_blocked(self) -> None:
        errors = validate_url_safety(
            "http://[fd00:ec2::254]/latest/meta-data/",
            label="provider endpoint",
            policy=UrlPolicy(allow_local=False, require_https_for_remote=False),
        )
        self.assertTrue(any("cloud metadata" in error for error in errors), errors)

    def test_dns_validation_checks_every_resolved_address(self) -> None:
        def mixed_resolver(*_args: object) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
            ]

        errors = validate_url_resolution(
            "https://mixed.example/path",
            label="provider endpoint",
            policy=UrlPolicy(allow_local=False),
            resolver=mixed_resolver,
        )
        self.assertTrue(any("local-only" in error for error in errors), errors)

    def test_ipv4_mapped_ipv6_resolution_is_normalized_before_policy(self) -> None:
        def mapped_resolver(*_args: object) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 0, 0, 0))]

        addresses = resolve_host_addresses("mapped.example", resolver=mapped_resolver)
        self.assertEqual([str(address) for address in addresses], ["127.0.0.1"])
        errors = validate_url_resolution(
            "https://mapped.example/",
            policy=UrlPolicy(allow_local=False),
            resolver=mapped_resolver,
        )
        self.assertTrue(any("local-only" in error for error in errors), errors)

    def test_unresolved_environment_placeholder_is_not_treated_as_safe(self) -> None:
        errors = validate_url_safety("${ATTACKER_URL}", label="module endpoint")
        self.assertTrue(errors)

    def test_local_health_policy_accepts_only_explicit_loopback_targets(self) -> None:
        for url in (
            "http://127.0.0.1:3333/api/health/live",
            "http://localhost:8080/health",
            "https://[::1]:8443/health",
        ):
            with self.subTest(url=url):
                self.assertEqual(validate_local_health_url(url), [])

    def test_local_health_policy_rejects_remote_private_and_alias_targets(self) -> None:
        for url in (
            "https://example.com:443/health",
            "http://10.0.0.8:8080/health",
            "http://169.254.169.254:80/latest/meta-data",
            "http://service.internal:8080/health",
            "http://0177.0.0.1:8080/health",
            "http://127.0.0.1/health",
        ):
            with self.subTest(url=url):
                self.assertTrue(validate_local_health_url(url))

    def test_local_health_policy_rejects_credentials_and_malformed_ports(self) -> None:
        self.assertTrue(validate_local_health_url("http://user:secret@127.0.0.1:8080/health"))
        self.assertTrue(validate_local_health_url("http://127.0.0.1:99999/health"))

    def test_local_health_fetch_does_not_follow_redirects(self) -> None:
        from spark_cli.cli import local_health_urlopen

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/redirect")
            with self.assertRaises(urllib.error.HTTPError) as raised:
                local_health_urlopen(request, timeout=2)
            self.assertEqual(raised.exception.code, 302)
            raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_local_health_fetch_rejects_remote_target_before_opening(self) -> None:
        from spark_cli.cli import local_health_urlopen

        request = urllib.request.Request("http://169.254.169.254:80/latest/meta-data/")
        with patch("spark_cli.cli.urllib.request.build_opener") as build_opener:
            with self.assertRaises(urllib.error.URLError):
                local_health_urlopen(request, timeout=2)
        build_opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
