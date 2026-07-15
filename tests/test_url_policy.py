from __future__ import annotations

import unittest

import socket

from spark_cli.security.url_policy import UrlPolicy, resolve_host_addresses, validate_url_resolution, validate_url_safety


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


if __name__ == "__main__":
    unittest.main()
