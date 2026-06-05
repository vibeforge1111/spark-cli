from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from spark_cli.cli import build_parser, cmd_access, print_access_payload
from spark_cli.cli import cmd_sandbox
from spark_cli.sandbox.access import _parse_utc_timestamp, disable_level5_guardrails, persist_level5_guardrails, read_env_file
from spark_cli.sandbox.docker import collect_docker_doctor_payload, collect_docker_smoke_payload


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


def _fake_level5_evidence_ref(
    kind: str,
    source: str,
    summary: str,
    *,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "source": source,
        "summary": summary,
        "confidence": confidence,
    }


class _FakeLevel5HarnessKernel:
    def __init__(self, *, surface: str) -> None:
        self.surface = surface

    def proposed_action(
        self,
        *,
        capability_id: str,
        action_type: str,
        risk_tier: str,
        summary: str,
        args_path: str,
        requires_confirmation: bool,
    ) -> dict[str, Any]:
        return {
            "action_id": "action:test-level5-access",
            "capability_id": capability_id,
            "action_type": action_type,
            "risk_tier": risk_tier,
            "summary": summary,
            "args_ref": {"uri": args_path},
            "requires_confirmation": requires_confirmation,
        }

    def create_envelope(
        self,
        *,
        selected_move: str,
        intent_summary: str,
        raw_turn_summary: str,
        evidence: list[dict[str, Any]],
        proposed_actions: list[dict[str, Any]],
        authority_state: str,
        risk_tier: str,
        confidence: float,
        requires_human_confirmation: bool = True,
    ) -> dict[str, Any]:
        return {
            "turn_id": "turn:test-level5-access",
            "surface": self.surface,
            "selected_move": selected_move,
            "intent_summary": intent_summary,
            "raw_turn_summary": raw_turn_summary,
            "evidence": evidence,
            "proposed_actions": proposed_actions,
            "action_authority": {"state": authority_state},
            "risk_tier": risk_tier,
            "confidence": confidence,
            "requires_human_confirmation": requires_human_confirmation,
        }

    def authorize(
        self,
        envelope: dict[str, Any],
        action: dict[str, Any],
        *,
        approval_ref: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "decision_id": "decision:test-level5-access",
            "turn_id": envelope["turn_id"],
            "action_id": action["action_id"],
            "capability_id": action["capability_id"],
            "verdict": "allow",
            "approval": {"required": True, "status": "approved", "approval_ref": approval_ref},
        }

    def record_tool_call(
        self,
        *,
        envelope: dict[str, Any],
        action: dict[str, Any],
        authorization: dict[str, Any],
        tool_name: str,
        status: str,
        output_path: str,
        summary: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "tool-call-ledger-v1",
            "ledger_id": "ledger:test-level5-access",
            "turn_id": envelope["turn_id"],
            "action_id": action["action_id"],
            "capability_id": action["capability_id"],
            "tool_name": tool_name,
            "authorization": authorization,
            "result": {"status": status, "summary": summary, "sanitized_output_ref": {"uri": output_path}},
        }

    def governor_decision(
        self,
        envelope: dict[str, Any],
        *,
        authorizations: list[dict[str, Any]],
        tool_ledgers: list[dict[str, Any]],
        **_: Any,
    ) -> dict[str, Any]:
        return {
            "schema_version": "governor-decision-v1",
            "decision_id": "governor:test-level5-access",
            "outcome": "execute",
            "envelope": envelope,
            "authorizations": authorizations,
            "tool_ledgers": tool_ledgers,
        }


def _fake_level5_verify_governor_tool_authority(
    governor_decision: dict[str, Any] | None,
    *,
    tool_name: str,
    owner_system: str,
    mutation_class: str,
    require_pre_execution_ledger: bool = True,
) -> dict[str, Any]:
    if not isinstance(governor_decision, dict):
        return {"allowed": False, "reason_codes": ["missing_governor_decision"]}
    reason_codes: list[str] = []
    if governor_decision.get("outcome") != "execute":
        reason_codes.append(f"governor_outcome_{governor_decision.get('outcome') or 'missing'}")
    envelope = governor_decision.get("envelope") if isinstance(governor_decision.get("envelope"), dict) else {}
    action = {}
    proposed_actions = envelope.get("proposed_actions")
    if isinstance(proposed_actions, list) and proposed_actions and isinstance(proposed_actions[0], dict):
        action = proposed_actions[0]
    if not str(action.get("capability_id") or "").startswith(f"capability:{owner_system}:"):
        reason_codes.append("owner_system_mismatch")
    if mutation_class != "writes_files" or action.get("action_type") != "edit_file":
        reason_codes.append("mutation_class_mismatch")
    authorizations = governor_decision.get("authorizations")
    authorization = authorizations[0] if isinstance(authorizations, list) and authorizations else {}
    if not isinstance(authorization, dict) or authorization.get("verdict") != "allow":
        reason_codes.append("governor_missing_matching_authorization")
    elif authorization.get("action_id") != action.get("action_id"):
        reason_codes.append("authorization_action_mismatch")
    ledgers = governor_decision.get("tool_ledgers")
    ledger = ledgers[0] if isinstance(ledgers, list) and ledgers else {}
    if require_pre_execution_ledger and (not isinstance(ledger, dict) or ledger.get("tool_name") != tool_name):
        reason_codes.append("governor_missing_pre_execution_tool_ledger")
    elif isinstance(ledger, dict) and ledger.get("action_id") != action.get("action_id"):
        reason_codes.append("tool_ledger_action_mismatch")
    return {"allowed": not reason_codes, "reason_codes": reason_codes}


class AccessSetupTests(unittest.TestCase):
    def test_read_env_file_trims_values_and_matching_outer_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "module.env"
            env_path.write_text(
                "\ufeffSPARK_CODEX_SANDBOX = \"danger-full-access\" \n"
                "SPARK_ALLOW_HIGH_AGENCY_WORKERS='1'\n"
                "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS= 1 \n"
                "MISMATCHED=\"leave-alone'\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_env_file(env_path),
                {
                    "SPARK_CODEX_SANDBOX": "danger-full-access",
                    "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "1",
                    "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "1",
                    "MISMATCHED": "\"leave-alone'",
                },
            )

    def run_access(
        self,
        *argv: str,
        spark_home: Path,
        env_overrides: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        args = build_parser().parse_args(["access", *argv, "--json"])
        stdout = StringIO()
        env_values = {
            "SPARK_HOME": str(spark_home),
            "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "",
            "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "",
            "SPARK_CODEX_SANDBOX": "",
        }
        env_values.update(env_overrides or {})
        with patch.dict(os.environ, env_values, clear=False), \
             patch("spark_cli.sandbox.access.collect_docker_doctor_payload", return_value=DOCKER_NOT_READY), \
             patch("spark_cli.sandbox.access.modal_sdk_available", return_value=False), \
             patch(
                 "spark_cli.cli.load_harness_core_symbols",
                 return_value=(_FakeLevel5HarnessKernel, _fake_level5_evidence_ref),
             ), \
             patch(
                 "spark_cli.sandbox.access._load_verify_governor_tool_authority",
                 return_value=_fake_level5_verify_governor_tool_authority,
             ), \
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
            self.assertEqual(payload["guide"]["default"]["access_level"], 4)
            self.assertFalse(payload["guide"]["default"]["whole_computer_access"])
            self.assertEqual(payload["guide"]["stronger_sandbox_order"], ["docker", "modal", "ssh"])
            self.assertIn("not a hardened container", payload["guide"]["security_note"])
            self.assertTrue(payload["automation"]["no_terminal_required"])
            actions = {action["id"]: action for action in payload["automation"]["actions"]}
            self.assertEqual(actions["workspace_setup"]["run_policy"], "auto_safe")
            self.assertEqual(actions["docker_doctor"]["run_policy"], "auto_read_only")
            self.assertEqual(actions["docker_smoke"]["run_policy"], "confirm_once")
            self.assertEqual(actions["level5_enable"]["run_policy"], "explicit_opt_in")
            self.assertEqual(payload["automation"]["deletion_safety"]["default"], "do_not_delete")
            self.assertEqual(
                payload["automation"]["level5_runtime_policy"]["destructive_actions_after_activation"],
                "still_approval_required",
            )

    def test_access_guide_is_plain_language_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            exit_code, payload = self.run_access("guide", spark_home=spark_home)

            self.assertEqual(exit_code, 0)
            self.assertFalse(Path(str(payload["workspace_path"])).exists())
            self.assertEqual(payload["guide"]["default"]["lane"], "spark_workspace")
            self.assertIn("safe default", payload["guide"]["plain_default"])
            self.assertFalse(payload["guide"]["default"]["whole_computer_access"])

    def test_access_guide_reports_os_specific_hints(self) -> None:
        cases = [
            ("darwin", "macos", "macOS default"),
            ("win32", "windows", "Windows default"),
            ("linux", "linux", "Linux default"),
        ]
        for platform, family, hint in cases:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as tmpdir, \
                 patch("spark_cli.sandbox.access.sys.platform", platform):
                exit_code, payload = self.run_access("guide", spark_home=Path(tmpdir) / "spark-home")

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["os_family"], family)
            self.assertIn(hint, payload["guide"]["os_note"])

    def test_access_status_reports_lower_levels_without_sandbox_setup(self) -> None:
        cases = [
            ("1", "chat_memory", "chat"),
            ("2", "requested_missions", "missions"),
            ("3", "public_research", "research"),
        ]
        for level, lane_id, activation_state in cases:
            with self.subTest(level=level), tempfile.TemporaryDirectory() as tmpdir:
                exit_code, payload = self.run_access("status", "--level", level, spark_home=Path(tmpdir) / "spark-home")

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["access_level"], int(level))
            self.assertEqual(payload["effective_access_level"], int(level))
            self.assertEqual(payload["recommended"]["id"], lane_id)
            self.assertEqual(payload["state_machine"]["activation_state"], activation_state)
            self.assertFalse(payload["state_machine"]["can_operate_whole_computer"])
            self.assertEqual(payload["guide"]["default"]["codex_sandbox"], "none")
            self.assertIn("do not need sandbox setup", payload["guide"]["plain_default"])

    def test_access_status_keeps_level5_blocked_without_high_agency_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {"SPARK_ALLOW_HIGH_AGENCY_WORKERS": ""}, clear=False):
            exit_code, payload = self.run_access("status", "--level", "5", spark_home=Path(tmpdir) / "spark-home")

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["recommended"]["id"], "spark_workspace")
        self.assertEqual(payload["lanes"][0]["id"], "level5_operator")
        self.assertEqual(payload["lanes"][0]["setup_mode"], "blocked")

    def test_print_access_payload_names_level5_setup_command_when_blocked(self) -> None:
        stdout = StringIO()
        payload = {
            "access_level": 5,
            "os_family": "linux",
            "workspace_path": "/tmp/spark",
            "recommended": {"id": "spark_workspace", "label": "Spark Workspace Sandbox"},
            "workspace_preflight": {"writable": True},
            "level5": {"enabled": False, "restart_required": False},
            "lanes": [],
            "next": "spark access setup --level 5 --enable-high-agency",
            "guide": {},
        }

        with redirect_stdout(stdout):
            print_access_payload(payload)

        self.assertIn(
            "Level 5 guardrails: blocked until explicitly enabled with "
            "`spark access setup --level 5 --enable-high-agency`",
            stdout.getvalue(),
        )

    def test_parse_utc_timestamp_treats_naive_timestamp_as_utc(self) -> None:
        expected = datetime(2026, 6, 1, 12, 0, tzinfo=UTC).timestamp()

        self.assertEqual(_parse_utc_timestamp("2026-06-01T12:00:00"), expected)
        self.assertEqual(_parse_utc_timestamp("2026-06-01T12:00:00Z"), expected)

    def test_access_setup_level5_requires_explicit_high_agency_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, payload = self.run_access("setup", "--level", "5", spark_home=Path(tmpdir) / "spark-home")

        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["level5"]["configured"])
        self.assertEqual(payload["next"], "spark access setup --level 5 --enable-high-agency")

    def test_level5_guardrail_leaf_requires_governor_before_env_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            with self.assertRaisesRegex(RuntimeError, "missing_governor_decision"):
                persist_level5_guardrails(home=spark_home)

            module_env = spark_home / "config" / "modules"
            self.assertFalse((module_env / "spawner-ui.env").exists())
            self.assertFalse((module_env / "spark-telegram-bot.env").exists())
            self.assertFalse((spark_home / "logs" / "remote" / "access" / "level5.jsonl").exists())

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
        self.assertEqual(payload["level5"]["activation_state"], "restart_required")
        self.assertEqual(payload["effective_access_level"], 4)
        self.assertFalse(payload["state_machine"]["can_operate_whole_computer"])
        self.assertEqual(payload["next"], "spark restart")
        self.assertEqual(payload["automation"]["recommended_action"], "spark restart")
        actions = {action["id"]: action for action in payload["automation"]["actions"]}
        self.assertEqual(actions["level5_enable"]["confirmation"], "Enable whole-computer operator mode")
        self.assertEqual(actions["level5_enable"]["rollback"], "spark access disable-level5")
        self.assertIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1", spawner_env)
        self.assertIn("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=1", spawner_env)
        self.assertIn("SPARK_CODEX_SANDBOX=danger-full-access", spawner_env)
        self.assertIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1", telegram_env)
        self.assertIn("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=1", telegram_env)
        self.assertIn("SPARK_CODEX_SANDBOX=danger-full-access", telegram_env)
        self.assertTrue(audit_written)

    def test_access_setup_level5_overwrites_stale_telegram_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            module_env = spark_home / "config" / "modules"
            module_env.mkdir(parents=True)
            (module_env / "spark-telegram-bot.env").write_text(
                "SPARK_ALLOW_HIGH_AGENCY_WORKERS=0\n"
                "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=0\n"
                "SPARK_CODEX_SANDBOX=workspace-write\n",
                encoding="utf-8",
            )

            exit_code, payload = self.run_access("setup", "--level", "5", "--enable-high-agency", spark_home=spark_home)
            telegram_env = (module_env / "spark-telegram-bot.env").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["level5"]["configured"])
        self.assertEqual(payload["level5"]["activation_state"], "restart_required")
        self.assertIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1", telegram_env)
        self.assertIn("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=1", telegram_env)
        self.assertIn("SPARK_CODEX_SANDBOX=danger-full-access", telegram_env)

    def test_access_status_level5_active_after_restart_env_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            self.run_access("setup", "--level", "5", "--enable-high-agency", spark_home=spark_home)
            exit_code, payload = self.run_access(
                "status",
                "--level",
                "5",
                spark_home=spark_home,
                env_overrides={
                    "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "1",
                    "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "1",
                    "SPARK_CODEX_SANDBOX": "danger-full-access",
                },
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["level5"]["enabled"])
        self.assertTrue(payload["level5"]["configured"])
        self.assertFalse(payload["level5"]["restart_required"])
        self.assertEqual(payload["level5"]["activation_state"], "active")
        self.assertEqual(payload["effective_access_level"], 5)
        self.assertTrue(payload["state_machine"]["can_operate_whole_computer"])
        self.assertTrue(payload["state_machine"]["persistent"])
        self.assertEqual(payload["recommended"]["id"], "level5_operator")

    def test_access_status_level5_active_when_services_restarted_after_guardrail_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            self.run_access("setup", "--level", "5", "--enable-high-agency", spark_home=spark_home)
            state_dir = spark_home / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "pids.json").write_text(
                json.dumps(
                    {
                        "spawner-ui": {
                            "pid": 111,
                            "module": "spawner-ui",
                            "started_at": "2999-01-01T00:00:00Z",
                        },
                        "spark-telegram-bot:spark-agi": {
                            "pid": 222,
                            "module": "spark-telegram-bot",
                            "started_at": "2999-01-01T00:00:00Z",
                        },
                    }
                ),
                encoding="utf-8",
            )

            exit_code, payload = self.run_access("status", "--level", "5", spark_home=spark_home)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["level5"]["enabled"])
        self.assertTrue(payload["level5"]["configured"])
        self.assertFalse(payload["level5"]["current_process_enabled"])
        self.assertTrue(payload["level5"]["service_enabled"])
        self.assertFalse(payload["level5"]["restart_required"])
        self.assertEqual(payload["level5"]["activation_state"], "active_for_services")
        self.assertEqual(payload["effective_access_level"], 5)
        self.assertTrue(payload["state_machine"]["can_operate_whole_computer"])
        self.assertFalse(payload["state_machine"]["current_process_can_operate_whole_computer"])
        self.assertTrue(payload["state_machine"]["service_can_operate_whole_computer"])
        self.assertEqual(payload["next"], "spark access status --level 5")
        self.assertEqual(payload["recommended"]["id"], "level5_operator")

    def test_access_status_level5_session_only_needs_persistent_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code, payload = self.run_access(
                "status",
                "--level",
                "5",
                spark_home=Path(tmpdir) / "spark-home",
                env_overrides={
                    "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "1",
                    "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "1",
                    "SPARK_CODEX_SANDBOX": "danger-full-access",
                },
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["level5"]["enabled"])
        self.assertFalse(payload["level5"]["configured"])
        self.assertEqual(payload["level5"]["activation_state"], "session_only")
        self.assertEqual(payload["next"], "spark access setup --level 5 --enable-high-agency")
        self.assertFalse(payload["state_machine"]["persistent"])

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
        self.assertNotIn("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS", telegram_env)
        self.assertNotIn("SPARK_CODEX_SANDBOX", telegram_env)

    def test_disable_level5_leaf_requires_governor_before_env_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spark_home = Path(tmpdir) / "spark-home"
            module_env = spark_home / "config" / "modules"
            module_env.mkdir(parents=True)
            spawner_env_path = module_env / "spawner-ui.env"
            spawner_env_path.write_text("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "missing_governor_decision"):
                disable_level5_guardrails(home=spark_home)

            self.assertIn("SPARK_ALLOW_HIGH_AGENCY_WORKERS=1", spawner_env_path.read_text(encoding="utf-8"))
            self.assertFalse((spark_home / "logs" / "remote" / "access" / "level5.jsonl").exists())

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
        self.assertEqual(payload["automation"]["recommended_lane"], "docker")
        actions = {action["id"]: action for action in payload["automation"]["actions"]}
        self.assertTrue(actions["docker_doctor"]["available"])
        self.assertIn("no-secret Docker smoke", actions["docker_smoke"]["user_message"])

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

    def test_docker_smoke_builds_and_runs_with_safe_container_flags(self) -> None:
        completed = subprocess.CompletedProcess(["docker"], 0, stdout="28.5.1\n", stderr="")
        with patch("spark_cli.sandbox.docker.shutil.which", return_value="docker"), \
             patch("spark_cli.sandbox.docker.subprocess.run", side_effect=[completed, completed, completed]) as run:
            payload = collect_docker_smoke_payload(image="spark-test:local")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "smoke")
        self.assertEqual(payload["network"], "none")
        build_args = run.call_args_list[1].args[0]
        run_args = run.call_args_list[2].args[0]
        self.assertEqual(build_args[:3], ["docker", "build", "-f"])
        self.assertIn("spark-test:local", build_args)
        self.assertIn("--network", run_args)
        self.assertIn("none", run_args)
        self.assertIn("--read-only", run_args)
        self.assertIn("--cap-drop", run_args)
        self.assertIn("ALL", run_args)
        self.assertIn("no-new-privileges", run_args)
        self.assertIn("/sandbox:rw,nosuid,uid=1000,gid=1000,size=512m", run_args)
        self.assertNotIn("/var/run/docker.sock", " ".join(run_args))
        self.assertEqual(payload["checks"][0]["repair"], "")

    def test_sandbox_docker_smoke_cli_json_runs_payload(self) -> None:
        args = build_parser().parse_args(["sandbox", "docker", "smoke", "--image", "spark-test:local", "--no-build", "--json"])
        stdout = StringIO()
        with patch("spark_cli.sandbox.docker.collect_docker_smoke_payload", return_value={
            "ok": True,
            "backend": "docker",
            "command": "smoke",
            "checks": [],
            "capabilities": {},
            "next": "done",
        }) as collect, redirect_stdout(stdout):
            exit_code = cmd_sandbox(args)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "smoke")
        collect.assert_called_once_with(build=False, image="spark-test:local", network=False)

    def test_docker_sandbox_wrappers_pass_args_and_create_writable_sandbox_tmpfs(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        ps1 = (repo / "scripts" / "docker-sandbox-run.ps1").read_text(encoding="utf-8")
        sh = (repo / "scripts" / "docker-sandbox-run.sh").read_text(encoding="utf-8")
        workflow = (repo / ".github" / "workflows" / "docker-optional.yml").read_text(encoding="utf-8")

        self.assertIn("PositionalBinding=$false", ps1)
        self.assertIn("ValueFromRemainingArguments", ps1)
        self.assertIn("/sandbox:rw,nosuid,uid=1000,gid=1000,size=512m", ps1)
        self.assertIn("/sandbox:rw,nosuid,uid=1000,gid=1000,size=512m", sh)
        self.assertIn("/sandbox:rw,nosuid,uid=1000,gid=1000,size=512m", workflow)
        self.assertIn("--network \"${network}\"", sh)
        for script in (ps1, sh):
            self.assertNotIn("/var/run/docker.sock", script)
            self.assertNotIn("--mount", script)
            self.assertNotIn("--volume", script)
            self.assertNotIn(" -v ", script)

    def test_dev_docker_smoke_uses_bounded_docker_checks(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        dockerfile = (repo / "docker" / "dev" / "Dockerfile").read_text(encoding="utf-8")
        ps1 = (repo / "scripts" / "docker-dev-smoke.ps1").read_text(encoding="utf-8")
        sh = (repo / "scripts" / "docker-dev-smoke.sh").read_text(encoding="utf-8")

        for source in (dockerfile, ps1, sh):
            self.assertIn("tests/test_docker_entrypoint.py", source)
            self.assertIn("spark --help", source)
            self.assertNotIn("tests/test_cli.py -q", source)
        self.assertIn("COPY docker ./docker", dockerfile)


if __name__ == "__main__":
    unittest.main()
