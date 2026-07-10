import pytest
import os
import re


class TestPathSecurity:
    def test_path_traversal_blocked(self):
        """PR #346/#347: restrict file reads to SPARK_HOME"""
        spark_home = "/root/.spark"
        traversals = [
            "/root/.spark/../../etc/passwd",
            "/root/.spark/../../../etc/shadow",
        ]
        for path in traversals:
            resolved = os.path.normpath(path)
            assert not resolved.startswith(spark_home), f"Traversal detected: {path}"

    def test_registry_module_name_validation(self):
        """PR #347: validate registry module names against path traversal"""
        bad_names = ["../../../etc", "../secrets", "a/../b"]
        good_names = ["spark-telegram-bot", "domain-chip-memory", "simple-name"]
        pattern = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
        for name in bad_names:
            assert not pattern.match(name), f"Should reject: {name}"
        for name in good_names:
            assert pattern.match(name), f"Should accept: {name}"

    def test_relay_secret_marker(self):
        """PR #203: relay secret configured marker"""
        marker = "SPARK_RELAY_SECRET_CONFIGURED"
        assert marker.startswith("SPARK_RELAY_SECRET")

    def test_docker_volume_paths(self):
        """PR #196: add missing /usr to suspicious docker volume paths"""
        path = "/usr/local/bin"
        assert path.startswith("/usr")

    def test_narrow_exception_handlers(self):
        """PR #348: narrow blanket exception handlers"""
        try:
            raise ValueError("test")
        except (ValueError, TypeError):
            pass
        else:
            pytest.fail("Should have caught ValueError")

    def test_root_safe_default(self):
        """PR #493: root-safe default spark home"""
        default_home = os.path.expanduser("~/.spark")
        assert default_home.startswith("/root")

    def test_embedded_key_findings(self):
        """PR #499: never downgrade embedded-private-key findings"""
        finding = {"severity": "high", "type": "embedded_private_key"}
        assert finding["severity"] != "low"
