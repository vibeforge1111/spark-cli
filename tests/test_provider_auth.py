from __future__ import annotations

import unittest
from unittest.mock import patch

from spark_cli.cli import provider_status_payload, provider_test_payload
from spark_cli.provider_auth import effective_provider_auth_mode


class ProviderAuthTruthTests(unittest.TestCase):
    def test_openai_default_base_does_not_inherit_codex_cli_presence(self) -> None:
        self.assertEqual(
            effective_provider_auth_mode(
                "openai",
                base_url_kind="default",
                codex_cli_present=True,
            ),
            "not_configured",
        )

    def test_provider_status_ready_matches_test_for_openai_default_base_no_key(self) -> None:
        setup_state = {
            "llm": {
                "provider": "openai",
                "roles": {
                    role: {
                        "provider": "openai",
                        "model": "gpt-5.5",
                        "auth_mode": "not_configured",
                        "base_url": "",
                    }
                    for role in ("chat", "builder", "mission", "memory")
                },
            }
        }
        with patch("spark_cli.cli.load_json", return_value=setup_state), \
             patch("spark_cli.cli.detect_codex_cli", return_value={"present": True, "path": "codex"}), \
             patch("spark_cli.cli.codex_cli_auth_payload", return_value={"ok": True}):
            status_payload = provider_status_payload()
            test_payload = provider_test_payload(role="chat")

        status_ready = status_payload["roles"]["chat"]["ready"]
        self.assertEqual(status_ready, test_payload["ok"])
        self.assertFalse(status_ready)
        self.assertFalse(test_payload["ok"])
        self.assertTrue(status_payload["repair_hints"])

    def test_status_prefers_codex_client_model_for_explicit_oauth_roles(self) -> None:
        setup = {
            "llm": {
                "provider": "openai",
                "roles": {
                    role: {
                        "provider": "openai",
                        "model": "gpt-5.3-codex-spark",
                        "auth_mode": "codex_oauth",
                        "bot_provider": "codex",
                    }
                    for role in ("chat", "builder", "memory", "mission")
                },
            },
            "secret_keys": [],
        }
        codex_payload = {
            "ok": True,
            "values": {"model": "gpt-5.5", "model_reasoning_effort": "high"},
        }
        with patch("spark_cli.cli.load_json", return_value=setup), \
             patch("spark_cli.cli.codex_cli_auth_payload", return_value={"ok": True}), \
             patch("spark_cli.cli.codex_client_config_payload", return_value=codex_payload):
            payload = provider_status_payload()

        for role in ("chat", "builder", "memory", "mission"):
            self.assertEqual(payload["roles"][role]["model"], "gpt-5.5")
            self.assertEqual(payload["roles"][role]["codex_client"], codex_payload)


if __name__ == "__main__":
    unittest.main()
