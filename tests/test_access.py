from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import build_parser, cmd_access
from spark_cli.cli import cmd_sandbox
from spark_cli.sandbox.docker import collect_docker_doctor_payload


DOCKER_NOT_READY = {
    "ok": False,
    "backend": "docker",
    "command": "doctor",
    "checks": [{"name": "docker_cli", "ok": False}],
    "capabilities": {},
    "next": "Install Docker Desktop, then rerun `spark sandbox docker doctor`.",
}

DOCKER_READY = {
    "ok": True,
    "backend": "docker",
    "command": "doctor",
    "checks": [
        {"name": "docker_cli", "ok": True},
        {"name": "docker_daemon", "ok": True},
    ],
    "capabilities": {},
    "next": "Run `spark access setup --with docker` for Docker-backed Level 4 tasks.",
}


class AccessSetupTests(unittest.TestCase):
    def run_access(self, *argv: str, spark_home: Path) -> tuple[int, dict[str, object]]:
        args = build_parser().parse_args(["access", *argv, "--json"])
        stdout = StringIO()
        with patch.dict(os.environ, {
            "SPARK_HOME": str(spark_home),
            "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "",
            "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "",
            "SPARK_CODEX_SANDBOX": "",
        }, clear=False), \
             patch("spark_cli.sandbox.access.collect_docker_doctor_payload", return_value=DOCKER_NOT_READY), \
             patch("spark_cli.sandbox.access.modal_sdk_available", return_value=False), \
             redirect_stdout(stdout):
            exit_code = cmd_access(args)
        return exit_code, json.loads(stdout.getvalue())

    def test_access_setup_creates_level4_workspace_without_docker_or_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            exit_code, payload = self.run_access("setup", spark_home=spark_home)

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["access_level"], 4)
            self.assertEqual(payload["recommended"]["id"], "spark_workspace")
            self.assertEqual(payload["recommended"]["setup_mode"], "automatic")
            self.assertTrue(payload["workspace_preflight"]["writable"])
            self.assertTrue(Path(str(payload["workspace_path"])).exists())

    def test_access_status_keeps_level5_blocked_without_high_agency_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"SPARK_ALLOW_HIGH_AGENCY_WORKERS": ""}, clear=False):
            exit_code, payload = self.run_access("status", "--level", "5", spark_home=Path(tmpdir) / "spark-home")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["recommended"]["id"], "spark_workspace")
        self.assertEqual(payload["lanes"][0]["id"], "level5_operator")
        self.assertEqual(payload["lanes"][0]["setup_mode"], "blocked")

    def test_access_setup_level5_requires_explicit_high_agency_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, payload = self.run_access("setup", "--level", "5", spark_home=Path(tmpdir) / "spark-home")

        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["level5"]["configured"])
        self.assertEqual(payload["next"], "spark access setup --level 5 --enable-high-agency")

    def test_access_setup_level5_writes_guardrail_env_and_requires_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            exit_code, payload = self.run_access("setup", "--level", "5", "--enable-high-agency", spark_home=spark_home)
            spawner_env = (spark_home / "config" / "modules" / "spawner-ui.env").read_text(encoding="utf-8")
            telegram_env = (spark_home / "config" / "modules" / "spark-telegram-bot.env").read_text(encoding="utf-8")
            audit_written = (spark_home / "logs" / "remote" / "access" / "level5.jsonl").exists()

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["level5"]["configured"])
        self.assertTrue(payload["level5"]["restart_required"])
        self.assertEqual(payload["next"], "spark restart")
        self.assertIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1", spawner_env)
        self.assertIn("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=1", spawner_env)
        self.assertIn("SPARK_CODEX_SANDBOX=danger-full-access", spawner_env)
        self.assertIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1", telegram_env)
        self.assertTrue(audit_written)

    def test_access_disable_level5_removes_guardrail_env_and_requires_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            self.run_access("setup", "--level", "5", "--enable-high-agency", spark_home=spark_home)
            exit_code, payload = self.run_access("disable-level5", spark_home=spark_home)
            spawner_env = (spark_home / "config" / "modules" / "spawner-ui.env").read_text(encoding="utf-8")
            telegram_env = (spark_home / "config" / "modules" / "spark-telegram-bot.env").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "disable-level5")
        self.assertEqual(payload["next"], "spark restart")
        self.assertNotIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS", spawner_env)
        self.assertNotIn("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS", spawner_env)
        self.assertNotIn("SPARK_CODEX_SANDBOX", spawner_env)
        self.assertNotIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS", telegram_env)

    def test_access_setup_can_recommend_docker_when_requested_and_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = build_parser().parse_args(["access", "setup", "--with", "docker", "--json"])
            stdout = StringIO()
            with patch.dict(os.environ, {"SPARK_HOME": str(Path(tmpdir) / "spark-home")}, clear=False), \
                 patch("spark_cli.sandbox.access.collect_docker_doctor_payload", return_value=DOCKER_READY), \
                 patch("spark_cli.sandbox.access.modal_sdk_available", return_value=False), \
                 redirect_stdout(stdout):
                exit_code = cmd_access(args)
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["recommended"]["id"], "docker")
        self.assertEqual(payload["recommended"]["setup_mode"], "automatic")

    def test_docker_doctor_reports_missing_cli_without_installing_anything(self) -> None:
        with patch("spark_cli.sandbox.docker.shutil.which", return_value=None):
            payload = collect_docker_doctor_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["backend"], "docker")
        self.assertEqual(payload["checks"][0]["name"], "docker_cli")
        self.assertIn("Install Docker", payload["next"])

    def test_sandbox_docker_doctor_cli_json_runs_payload(self) -> None:
        args = build_parser().parse_args(["sandbox", "docker", "doctor", "--json"])
        stdout = StringIO()
        with patch("spark_cli.sandbox.docker.collect_docker_doctor_payload", return_value={
            "ok": True,
            "backend": "docker",
            "command": "doctor",
            "checks": [],
            "capabilities": {},
            "next": "done",
        }) as collect, redirect_stdout(stdout):
            exit_code = cmd_sandbox(args)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["backend"], "docker")
        collect.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
