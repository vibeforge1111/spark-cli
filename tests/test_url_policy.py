from __future__ import annotations

import unittest

from spark_cli.security.url_policy import UrlPolicy, validate_url_safety


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


if __name__ == "__main__":
    unittest.main()
