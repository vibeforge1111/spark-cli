from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from spark_cli.cli import build_parser, provider_status_payload, provider_test_payload


class ProviderStatusScopeTests(TestCase):
    def _kimi_setup(self) -> dict:
        return {
            "secret_keys": ["llm.kimi.api_key"],
            "llm": {
                "provider": "kimi",
                "roles": {
                    role: {
                        "provider": "kimi",
                        "model": "kimi-k2.6",
                        "auth_mode": "api_key",
                        "bot_provider": "kimi",
                    }
                    for role in ("chat", "builder", "memory", "mission")
                },
            },
        }

    def test_status_declares_configuration_scope_without_live_claim(self) -> None:
        with patch("spark_cli.cli.load_json", return_value=self._kimi_setup()):
            payload = provider_status_payload()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["roles"]["chat"]["ready"])
        self.assertEqual(payload["readiness_scope"], "configuration")
        self.assertEqual(
            payload["live_probe"],
            {
                "performed": False,
                "verified": False,
                "command": "spark providers test --role chat",
            },
        )

    def test_human_status_says_ready_not_ok_and_points_to_live_probe(self) -> None:
        args = build_parser().parse_args(["providers", "status"])
        with patch("spark_cli.cli.load_json", return_value=self._kimi_setup()), \
             redirect_stdout(StringIO()) as stdout:
            code = args.func(args)

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("[READY] chat", output)
        self.assertNotIn("[OK] chat", output)
        self.assertIn("Configuration only; no live provider request was sent.", output)
        self.assertIn("spark providers test --role chat", output)

    def test_http_400_live_probe_remains_failed_and_nonsecret(self) -> None:
        target = {
            "provider": "kimi",
            "model": "kimi-k2.6",
            "auth_mode": "api_key",
            "api_key": "secret-value",
        }
        with patch("spark_cli.cli.resolve_provider_test_target", return_value=target), \
             patch(
                 "spark_cli.cli.call_llm_doctor",
                 side_effect=SystemExit("LLM provider returned HTTP 400: api_key=[REDACTED]"),
             ):
            payload = provider_test_payload(role="chat")

        self.assertFalse(payload["ok"])
        self.assertIn("HTTP 400", payload["detail"])
        self.assertNotIn("secret-value", str(payload))
