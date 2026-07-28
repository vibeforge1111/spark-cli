from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from spark_cli.cli import build_parser, collect_telegram_fix_payload


class TelegramFixHealthTruthTests(TestCase):
    def _payload(self, *, secret_keys: list[str], detail: str, running: bool = True) -> dict:
        status = {
            "ok": False,
            "modules": [{"name": "spark-telegram-bot", "healthy": False, "detail": detail}],
            "tracked_pids": {"spark-telegram-bot": {"pid": 123}},
            "llm": {
                "provider": "zai",
                "roles": {
                    role: {"provider": "zai", "auth_mode": "api_key"}
                    for role in ("chat", "builder", "memory", "mission")
                },
            },
            "repair_hints": [],
        }

        def generated_env(path: Path) -> dict[str, str]:
            if path.name == "spark-telegram-bot.env":
                return {
                    "SPARK_BUILDER_BRIDGE_MODE": "required",
                    "SPARK_BUILDER_HOME": "/safe/builder",
                }
            return {
                "SPARK_INTELLIGENCE_HOME": "/safe/home",
                "SPARK_DOMAIN_CHIP_MEMORY_ROOT": "/safe/memory",
                "SPARK_RESEARCHER_ROOT": "/safe/researcher",
            }

        with patch("spark_cli.cli.collect_status_payload", return_value=status), \
             patch(
                 "spark_cli.cli.load_json",
                 return_value={"bundle": "telegram-starter", "secret_keys": secret_keys},
             ), \
             patch("spark_cli.cli.read_generated_env", side_effect=generated_env), \
             patch("spark_cli.cli.tail_log_lines", return_value=[]), \
             patch("spark_cli.cli.pid_is_running", return_value=running):
            return collect_telegram_fix_payload()

    def test_secret_session_decline_is_unverified_not_healthy(self) -> None:
        payload = self._payload(
            secret_keys=["telegram.bot_token", "telegram.admin_ids"],
            detail=(
                "Could not load telegram.profiles.primary.bot_token from /Users/private/config. "
                "Run this from an approved Spark secret session."
            ),
        )
        check = next(item for item in payload["checks"] if item["name"] == "telegram_module_health")

        self.assertFalse(payload["ok"])
        self.assertFalse(check["ok"])
        self.assertEqual(check["level"], "warning")
        self.assertIn("could not be verified", check["detail"])
        self.assertIn("do not prove Telegram delivery", check["detail"])
        self.assertNotIn("/Users/private", check["detail"])
        self.assertEqual(payload["route_context"]["health_evidence"], "fresh_unverified")

    def test_profile_token_is_recognized_without_claiming_delivery(self) -> None:
        payload = self._payload(
            secret_keys=["telegram.profiles.primary.bot_token", "telegram.admin_ids"],
            detail=(
                "Could not load telegram.profiles.primary.bot_token. "
                "Run this from an approved Spark secret session."
            ),
        )
        checks = {item["name"]: item for item in payload["checks"]}

        self.assertTrue(checks["bot_token"]["ok"])
        self.assertFalse(checks["telegram_module_health"]["ok"])
        self.assertEqual(checks["telegram_module_health"]["level"], "warning")

    def test_real_health_failure_remains_actionable(self) -> None:
        payload = self._payload(
            secret_keys=["telegram.profiles.primary.bot_token", "telegram.admin_ids"],
            detail="Telegram Bot API getMe timed out.",
        )
        check = next(item for item in payload["checks"] if item["name"] == "telegram_module_health")

        self.assertFalse(check["ok"])
        self.assertEqual(check["level"], "error")
        self.assertEqual(check["detail"], "Telegram Bot API getMe timed out.")
        self.assertEqual(payload["route_context"]["health_evidence"], "fresh_degraded")

    def test_human_surface_marks_unverified_health_as_warning(self) -> None:
        payload = self._payload(
            secret_keys=["telegram.profiles.primary.bot_token", "telegram.admin_ids"],
            detail=(
                "Could not load telegram.profiles.primary.bot_token. "
                "Run this from an approved Spark secret session."
            ),
        )
        args = build_parser().parse_args(["fix", "telegram"])

        with patch("spark_cli.cli.collect_telegram_fix_payload", return_value=payload), \
             redirect_stdout(StringIO()) as stdout:
            code = args.func(args)

        self.assertEqual(code, 1)
        self.assertIn("[WARN] telegram_module_health: Live Telegram health could not be verified", stdout.getvalue())
        self.assertNotIn("[OK] telegram_module_health", stdout.getvalue())
