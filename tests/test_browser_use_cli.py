from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from spark_cli import cli


class _FakeBrowserUseKernel:
    def __init__(self, *, outcome: str = "execute") -> None:
        self.outcome = outcome

    def record_tool_call(
        self,
        *,
        envelope: dict[str, object],
        action: dict[str, object],
        authorization: dict[str, object],
        tool_name: str,
        status: str,
        output_path: str,
        summary: str,
    ) -> dict[str, object]:
        return {
            "schema_version": "tool-call-ledger-v1",
            "ledger_id": "tool-ledger-test",
            "tool_name": tool_name,
            "result": {
                "status": status,
                "output_path": output_path,
                "summary": summary,
            },
        }

    def governor_decision(
        self,
        envelope: dict[str, object],
        *,
        authorizations: list[dict[str, object]],
        tool_ledgers: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": "governor-decision-v1",
            "decision_id": "governor-test",
            "outcome": self.outcome,
            "execution_boundary": {
                "action_authorized": self.outcome == "execute",
                "authorized_action_count": 1 if self.outcome == "execute" else 0,
            },
            "tool_ledgers": tool_ledgers or [],
        }


class BrowserUseCliTests(unittest.TestCase):
    def browser_use_authority(
        self,
        *,
        risk_tier: str = "read",
        requires_confirmation: bool = False,
        outcome: str = "execute",
    ) -> dict[str, object]:
        kernel = _FakeBrowserUseKernel(outcome=outcome)
        envelope = {"turn_id": "turn-browser-use-test"}
        action = {"action_id": "action-browser-use-test"}
        authorization = {
            "decision_id": "auth-browser-use-test",
            "verdict": "allow",
            "risk_tier": risk_tier,
            "approval": {
                "required": bool(requires_confirmation),
                "status": "approved" if requires_confirmation else "not_required",
            },
            "restrictions": {
                "network_allowed": True,
                "write_allowed": risk_tier == "high",
            },
        }
        return {
            "kernel": kernel,
            "envelope": envelope,
            "action": action,
            "authorization": authorization,
            "governor_decision": kernel.governor_decision(envelope, authorizations=[authorization]),
        }

    def test_cli_path_discovers_installed_spark_venv_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            entrypoint = Path(tmp_dir) / "tools" / "spark-cli-venv" / "bin" / "browser-use"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            with patch("spark_cli.cli.shutil.which", return_value=None), \
                 patch.dict(os.environ, {"SPARK_HOME": tmp_dir}, clear=False):
                self.assertEqual(cli.browser_use_cli_path(), str(entrypoint))

    def test_cli_path_discovers_installed_windows_spark_venv_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            entrypoint = Path(tmp_dir) / "tools" / "spark-cli-venv" / "Scripts" / "browser-use.exe"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_text("", encoding="utf-8")
            with patch("spark_cli.cli.shutil.which", return_value=None), \
                 patch.dict(os.environ, {"SPARK_HOME": tmp_dir}, clear=False):
                self.assertEqual(cli.browser_use_cli_path(), str(entrypoint))

    def test_status_reports_missing_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value=None), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=False):
                payload = cli.browser_use_status_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["next_action"], "Run `spark browser-use install`, then `spark browser-use probe`.")

    def test_status_marks_old_ready_receipt_unproven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            screenshot = Path(tmp_dir) / "probe-screenshot.png"
            status_path.parent.mkdir(parents=True)
            screenshot.write_bytes(b"png")
            status_path.write_text(
                cli.json.dumps(
                    {
                        "status": "ready",
                        "last_success_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                        "proofs": ["doctor", "public_page_open", "screenshot_capture", "state_read"],
                        "screenshot_path": str(screenshot),
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True):
                payload = cli.browser_use_status_payload()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "installed_unproven")
        self.assertFalse(payload["proof_fresh"])
        self.assertIn("stale", payload["last_failure_reason"])

    def test_status_accepts_builder_screenshot_proof_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            screenshot = Path(tmp_dir) / "smoke-screenshot.png"
            status_path.parent.mkdir(parents=True)
            screenshot.write_bytes(b"png")
            status_path.write_text(
                cli.json.dumps(
                    {
                        "status": "ready",
                        "last_success_at": datetime.now(timezone.utc).isoformat(),
                        "proofs": {
                            "doctor": {"status": "success"},
                            "public_page_open": {"status": "success"},
                            "state_read": {"status": "success"},
                            "screenshot_capture": {"status": "success", "path": str(screenshot)},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True):
                payload = cli.browser_use_status_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")

    def test_status_surfaces_latest_browser_action_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            screenshot = status_path.parent / "probe-screenshot.png"
            action_dir = status_path.parent / "actions"
            action_receipt = action_dir / "spark-browser-timeout.json"
            status_path.parent.mkdir(parents=True)
            action_dir.mkdir(parents=True)
            screenshot.write_bytes(b"png")
            status_path.write_text(
                cli.json.dumps(
                    {
                        "status": "ready",
                        "last_success_at": datetime.now(timezone.utc).isoformat(),
                        "proofs": ["doctor", "public_page_open", "screenshot_capture", "state_read"],
                        "screenshot_path": str(screenshot),
                    }
                ),
                encoding="utf-8",
            )
            action_receipt.write_text(
                cli.json.dumps(
                    {
                        "action": "open",
                        "url": "https://compete.sparkswarm.ai/#agent-playbook",
                        "status": "failed",
                        "ok": False,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "last_failure_at": datetime.now(timezone.utc).isoformat(),
                        "last_failure_reason": "Page.navigate() timed out after 20.0s",
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True):
                payload = cli.browser_use_status_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["latest_action"]["action"], "open")
        self.assertEqual(payload["latest_action"]["status"], "failed")
        self.assertIn("Page.navigate", payload["latest_action"]["last_failure_reason"])

    def test_probe_writes_ready_receipt_for_public_page_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            completed = subprocess.CompletedProcess(["browser-use"], 0, stdout="ok", stderr="")
            screenshot_path = status_path.parent / "probe-screenshot.png"

            def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if "screenshot" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout=cli.json.dumps({"success": True, "data": {"screenshot": "cG5n"}}),
                        stderr="",
                    )
                return completed

            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.subprocess.run", side_effect=fake_run) as run:
                probe = cli.browser_use_probe_payload()
                status = cli.browser_use_status_payload()

        self.assertEqual(probe["status"], "ready")
        self.assertTrue(status["ok"])
        self.assertEqual(
            status["proven_scope"],
            ["browser-use doctor", "public page open", "page state read", "screenshot capture"],
        )
        self.assertEqual(
            [call.args[0][:4] for call in run.call_args_list[:4]],
            [
                ["browser-use", "doctor"],
                ["browser-use", "--session", "spark-probe", "open"],
                ["browser-use", "--session", "spark-probe", "state"],
                ["browser-use", "--json", "--session", "spark-probe"],
            ],
        )

    def test_install_dry_run_is_non_mutating(self) -> None:
        with patch("spark_cli.cli.subprocess.run") as run, \
             patch("builtins.print") as printed:
            exit_code = cli.cmd_browser_use(Namespace(browser_use_command="install", dry_run=True))

        self.assertEqual(exit_code, 0)
        run.assert_not_called()
        lines = [str(call.args[0]) for call in printed.call_args_list if call.args]
        self.assertTrue(any("pip install -e" in line for line in lines))

    def test_task_rejects_non_positive_max_steps(self) -> None:
        parser = cli.build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args(["browser-use", "task", "--max-steps", "0", "review page"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["browser-use", "task", "--max-steps", "-1", "review page"])

        args = parser.parse_args(["browser-use", "task", "--max-steps", "1", "review page"])
        self.assertEqual(args.max_steps, 1)

    def test_discovers_checkout_root_from_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "spark-cli"
            nested = root / "nested"
            (root / "scripts").mkdir(parents=True)
            nested.mkdir()
            (root / "pyproject.toml").write_text("[project]\nname='spark-cli'\n", encoding="utf-8")
            (root / "scripts" / "install.sh").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            with patch("spark_cli.cli.Path.cwd", return_value=nested):
                self.assertEqual(cli.discover_repo_root(), root)

    def test_open_returns_page_summary_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"

            def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if "state" in argv:
                    return subprocess.CompletedProcess(argv, 0, stdout="Example Domain\nLearn more", stderr="")
                if "eval" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout='result: {"title":"Example Domain","url":"https://example.com/","text":"Example Domain\\n\\nLearn more"}',
                        stderr="",
                    )
                return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.browser_use_harness_authorize", return_value=self.browser_use_authority()), \
                 patch("spark_cli.cli.subprocess.run", side_effect=fake_run) as run:
                payload = cli.browser_use_action_payload("https://example.com")
                ledger_exists = Path(payload["harness_authority"]["ledger_path"]).exists()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "open")
        self.assertEqual(payload["title"], "Example Domain")
        self.assertIn("Learn more", payload["text_excerpt"])
        self.assertIn("public URL open", payload["proven_scope"])
        self.assertEqual(payload["harness_authority"]["verdict"], "allow")
        self.assertEqual(payload["harness_authority"]["governor_outcome"], "execute")
        self.assertTrue(payload["harness_authority"]["governor_action_authorized"])
        self.assertEqual(payload["harness_authority"]["risk_tier"], "read")
        self.assertTrue(payload["harness_authority"]["governor_decision_id"])
        self.assertTrue(payload["harness_authority"]["tool_ledger_id"])
        self.assertTrue(ledger_exists)
        called_commands = [call.args[0] for call in run.call_args_list]
        self.assertIn("open", called_commands[0])
        self.assertIn("https://example.com", called_commands[0])
        self.assertIn("state", called_commands[1])
        self.assertIn("eval", called_commands[2])

    def test_action_blocks_when_governor_does_not_execute(self) -> None:
        authority = {
            "envelope": {"turn_id": "turn-test"},
            "action": {"action_id": "action-test"},
            "authorization": {"decision_id": "auth-test", "verdict": "allow", "risk_tier": "read"},
            "governor_decision": {
                "decision_id": "governor-test",
                "outcome": "deny",
                "execution_boundary": {"action_authorized": False},
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.browser_use_harness_authorize", return_value=authority), \
                 patch("spark_cli.cli.subprocess.run") as run:
                payload = cli.browser_use_action_payload("https://example.com")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["harness_authority"]["verdict"], "allow")
        self.assertEqual(payload["harness_authority"]["governor_outcome"], "deny")
        self.assertFalse(payload["harness_authority"]["governor_action_authorized"])
        run.assert_not_called()

    def test_page_summary_marks_truncated_text(self) -> None:
        long_text = "x" * 2001
        calls: list[list[str]] = []

        def fake_run(*argv: str, **_: object) -> subprocess.CompletedProcess[str]:
            command = list(argv)
            calls.append(command)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="result: "
                + cli.json.dumps(
                    {
                        "title": "Long",
                        "url": "https://example.com/",
                        "text": long_text,
                        "textLength": 2500,
                    }
                ),
                stderr="",
            )

        with patch("spark_cli.cli.run_browser_use_command", side_effect=fake_run):
            payload = cli.browser_use_page_summary("browser-use", "spark-browser-long")

        self.assertEqual(payload["title"], "Long")
        self.assertEqual(payload["text"], ("x" * 2000) + "\n[truncated]")
        self.assertIn("slice(0,2001)", calls[0][-1])

    def test_page_summary_leaves_exact_limit_unmarked(self) -> None:
        exact_text = "x" * 2000

        with patch(
            "spark_cli.cli.run_browser_use_command",
            return_value=subprocess.CompletedProcess(
                ["browser-use"],
                0,
                stdout="result: "
                + cli.json.dumps(
                    {
                        "title": "Exact",
                        "url": "https://example.com/",
                        "text": exact_text,
                        "textLength": len(exact_text),
                    }
                ),
                stderr="",
            ),
        ):
            payload = cli.browser_use_page_summary("browser-use", "spark-browser-exact")

        self.assertEqual(payload["text"], exact_text)
        self.assertNotIn("[truncated]", payload["text"])

    def test_screenshot_writes_screenshot_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"

            def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if "screenshot" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout=cli.json.dumps({"success": True, "data": {"screenshot": "cG5n"}}),
                        stderr="",
                    )
                if "eval" in argv:
                    return subprocess.CompletedProcess(argv, 0, stdout='result: {"title":"Example Domain","url":"https://example.com/","text":"Example"}', stderr="")
                return subprocess.CompletedProcess(argv, 0, stdout="Example", stderr="")

            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.browser_use_harness_authorize", return_value=self.browser_use_authority()), \
                 patch("spark_cli.cli.subprocess.run", side_effect=fake_run):
                payload = cli.browser_use_action_payload("https://example.com", screenshot=True)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["action"], "screenshot")
            self.assertTrue(Path(payload["screenshot_path"]).exists())
            self.assertIn("screenshot capture", payload["proven_scope"])

    def test_open_allows_local_urls_for_operator_browser_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"

            def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                if "eval" in argv:
                    return subprocess.CompletedProcess(argv, 0, stdout='result: {"title":"Mission Control","url":"http://127.0.0.1:3333/","text":"Kanban"}', stderr="")
                return subprocess.CompletedProcess(argv, 0, stdout="Kanban", stderr="")

            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.browser_use_harness_authorize", return_value=self.browser_use_authority()), \
                 patch("spark_cli.cli.subprocess.run", side_effect=fake_run):
                payload = cli.browser_use_action_payload("http://127.0.0.1:3333")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["final_url"], "http://127.0.0.1:3333/")

    def test_open_still_blocks_metadata_urls(self) -> None:
        payload = cli.browser_use_action_payload("http://169.254.169.254")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("metadata service", payload["last_failure_reason"])

    def test_task_runs_browser_use_agent_and_writes_receipt(self) -> None:
        async def fake_agent(
            goal: str,
            *,
            start_url: str = "",
            max_steps: int = 25,
            history_path: Path | None = None,
            start_page: dict[str, object] | None = None,
        ) -> dict[str, object]:
            if history_path is not None:
                history_path.write_text("{}", encoding="utf-8")
            return {
                "final_result": "The page looks good after checking the primary flow.",
                "urls": [start_url],
                "action_names": ["open", "extract"],
                "number_of_steps": 2,
                "total_duration_seconds": 1.2,
                "is_done": True,
                "is_successful": True,
                "is_validated": False,
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch(
                     "spark_cli.cli.browser_use_harness_authorize",
                     return_value=self.browser_use_authority(risk_tier="high", requires_confirmation=True),
                 ), \
                 patch("spark_cli.cli.browser_use_task_start_page", return_value={"ok": True, "final_url": "http://127.0.0.1:3333", "title": "Local", "text_excerpt": "Kanban"}), \
                 patch("spark_cli.cli.run_browser_use_agent_task", side_effect=fake_agent):
                payload = cli.browser_use_task_payload("review the page", start_url="http://127.0.0.1:3333", max_steps=4)
                receipt_exists = Path(payload["receipt_path"]).exists()
                history_exists = Path(payload["history_path"]).exists()
                ledger_exists = Path(payload["harness_authority"]["ledger_path"]).exists()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "task")
        self.assertEqual(payload["number_of_steps"], 2)
        self.assertIn("multi-step browser task", payload["proven_scope"])
        self.assertEqual(payload["start_page"]["title"], "Local")
        self.assertEqual(payload["harness_authority"]["verdict"], "allow")
        self.assertEqual(payload["harness_authority"]["governor_outcome"], "execute")
        self.assertTrue(payload["harness_authority"]["governor_action_authorized"])
        self.assertEqual(payload["harness_authority"]["risk_tier"], "high")
        self.assertTrue(payload["harness_authority"]["approval"]["required"])
        self.assertEqual(payload["harness_authority"]["approval"]["status"], "approved")
        self.assertTrue(payload["harness_authority"]["restrictions"]["network_allowed"])
        self.assertTrue(payload["harness_authority"]["restrictions"]["write_allowed"])
        self.assertTrue(payload["harness_authority"]["governor_decision_id"])
        self.assertTrue(payload["harness_authority"]["tool_ledger_id"])
        self.assertTrue(ledger_exists)
        self.assertTrue(receipt_exists)
        self.assertTrue(history_exists)

    def test_task_requires_goal(self) -> None:
        payload = cli.browser_use_task_payload("")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("task is required", payload["last_failure_reason"])

    def test_task_parser_accepts_options_after_goal_text(self) -> None:
        args = cli.build_parser().parse_args([
            "browser-use",
            "task",
            "review",
            "the",
            "page",
            "--url",
            "https://example.com",
            "--max-steps",
            "3",
            "--json",
        ])

        self.assertEqual(args.browser_use_command, "task")
        self.assertEqual(args.goal, ["review", "the", "page"])
        self.assertEqual(args.url, "https://example.com")
        self.assertEqual(args.max_steps, 3)
        self.assertTrue(args.json)

    def test_task_parser_keeps_option_like_goal_text_after_separator(self) -> None:
        args = cli.build_parser().parse_args([
            "browser-use",
            "task",
            "explain",
            "--",
            "--json",
        ])

        self.assertEqual(args.goal, ["explain", "--json"])
        self.assertFalse(args.json)

    def test_task_parser_keeps_json_missing_goal_on_command_path(self) -> None:
        args = cli.build_parser().parse_args(["browser-use", "task", "--json"])

        self.assertEqual(args.goal, [])
        self.assertTrue(args.json)

    def test_task_receipt_fails_when_agent_does_not_finish(self) -> None:
        async def fake_agent(
            goal: str,
            *,
            start_url: str = "",
            max_steps: int = 25,
            history_path: Path | None = None,
            start_page: dict[str, object] | None = None,
        ) -> dict[str, object]:
            return {
                "final_result": "",
                "errors": ["Failed to complete task in maximum steps"],
                "number_of_steps": 3,
                "is_done": False,
                "is_successful": False,
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch(
                     "spark_cli.cli.browser_use_harness_authorize",
                     return_value=self.browser_use_authority(risk_tier="high", requires_confirmation=True),
                 ), \
                 patch("spark_cli.cli.browser_use_task_start_page", return_value={"ok": True, "final_url": "https://example.com", "title": "Example", "text_excerpt": "Example Domain"}), \
                 patch("spark_cli.cli.run_browser_use_agent_task", side_effect=fake_agent):
                payload = cli.browser_use_task_payload("review the page", start_url="https://example.com", max_steps=3)
                ledger_exists = Path(payload["harness_authority"]["ledger_path"]).exists()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "failed")
        self.assertIn("maximum steps", payload["last_failure_reason"])
        self.assertEqual(payload["harness_authority"]["verdict"], "allow")
        self.assertTrue(ledger_exists)

    def test_task_blocks_when_harness_core_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status_path = Path(tmp_dir) / "state" / "browser-use" / "status.json"
            with patch.object(cli, "BROWSER_USE_STATUS_DIR", status_path.parent), \
                 patch.object(cli, "BROWSER_USE_STATUS_PATH", status_path), \
                 patch("spark_cli.cli.browser_use_cli_path", return_value="browser-use"), \
                 patch("spark_cli.cli.browser_use_package_available", return_value=True), \
                 patch("spark_cli.cli.load_harness_core_symbols", side_effect=RuntimeError("missing harness")):
                payload = cli.browser_use_task_payload("review the page", start_url="https://example.com", max_steps=3)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["harness_authority"]["verdict"], "unavailable")
        self.assertIn("missing harness", payload["last_failure_reason"])

    def test_task_receipt_fails_when_agent_reports_unsuccessful_result(self) -> None:
        payload = {
            "final_result": "I reached the page but could not complete the requested workflow.",
            "is_done": True,
            "is_successful": False,
        }

        self.assertFalse(cli.browser_use_task_completed(payload))

    def test_task_receipt_fails_when_judge_rejects_result(self) -> None:
        payload = {
            "final_result": "Looks done.",
            "is_done": True,
            "is_successful": True,
            "is_judged": True,
            "is_validated": False,
            "judgement": "Judge Verdict: FAIL - fabricated page text.",
        }

        self.assertFalse(cli.browser_use_task_completed(payload))
        self.assertIn("fabricated", cli.browser_use_task_failure_reason(payload))

    def test_normalizes_fenced_browser_use_agent_json(self) -> None:
        normalized = cli.browser_use_normalize_structured_agent_json(
            '```json\n{"memory":"ready","action":[{"done":{"answer":"Visible","success":true}}]}\n```'
        )
        payload = cli.json.loads(normalized)

        self.assertEqual(payload["action"][0]["done"]["text"], "Visible")
        self.assertNotIn("answer", payload["action"][0]["done"])

    def test_normalizes_root_done_agent_json(self) -> None:
        normalized = cli.browser_use_normalize_structured_agent_json(
            '{"done":{"answer":"Visible","success":true}}'
        )
        payload = cli.json.loads(normalized)

        self.assertEqual(payload["memory"], "Task result ready.")
        self.assertEqual(payload["action"][0]["done"]["text"], "Visible")

    def test_normalize_agent_json_returns_raw_text_for_invalid_json(self) -> None:
        raw = "The task completed, but this is not JSON."

        self.assertEqual(cli.browser_use_normalize_structured_agent_json(raw), raw)

    def test_agent_task_uses_spark_stability_defaults(self) -> None:
        captured: dict[str, object] = {}

        class FakeBrowser:
            def __init__(self, **kwargs: object) -> None:
                captured["browser_kwargs"] = kwargs
                captured["browser"] = self
                self.closed = False

            async def close(self) -> None:
                self.closed = True

        class FakeHistory:
            def save_to_file(self, path: Path) -> None:
                path.write_text("{}", encoding="utf-8")

            def final_result(self) -> str:
                return "Visible"

            def extracted_content(self) -> list[str]:
                return []

            def errors(self) -> list[str]:
                return []

            def urls(self) -> list[str]:
                return ["http://127.0.0.1:3333/canvas"]

            def screenshot_paths(self) -> list[str]:
                return []

            def action_names(self) -> list[str]:
                return ["navigate", "done"]

            def number_of_steps(self) -> int:
                return 2

            def total_duration_seconds(self) -> float:
                return 1.0

            def is_done(self) -> bool:
                return True

            def is_successful(self) -> bool:
                return True

            def is_judged(self) -> bool:
                return False

            def is_validated(self) -> bool:
                return False

        class FakeAgent:
            def __init__(self, **kwargs: object) -> None:
                captured["agent_kwargs"] = kwargs

            async def run(self, *, max_steps: int) -> FakeHistory:
                captured["run_max_steps"] = max_steps
                return FakeHistory()

        fake_browser_use = types.SimpleNamespace(Agent=FakeAgent, Browser=FakeBrowser)
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.dict(sys.modules, {"browser_use": fake_browser_use}), \
             patch("spark_cli.cli.browser_use_agent_llm", return_value=("test-llm", "test-provider")):
            history_path = Path(tmp_dir) / "history.json"
            result = asyncio.run(
                cli.run_browser_use_agent_task(
                    "review the page",
                    start_url="http://127.0.0.1:3333/canvas",
                    max_steps=3,
                    history_path=history_path,
                )
            )

        agent_kwargs = captured["agent_kwargs"]
        self.assertEqual(result["llm"], "test-provider")
        self.assertEqual(captured["run_max_steps"], 3)
        self.assertEqual(agent_kwargs["llm"], "test-llm")
        self.assertEqual(agent_kwargs["max_actions_per_step"], 5)
        self.assertTrue(agent_kwargs["flash_mode"])
        self.assertFalse(agent_kwargs["include_tool_call_examples"])
        self.assertFalse(agent_kwargs["use_thinking"])
        self.assertFalse(agent_kwargs["use_judge"])
        self.assertEqual(agent_kwargs["llm_screenshot_size"], cli.BROWSER_USE_AGENT_LLM_SCREENSHOT_SIZE)
        self.assertFalse(agent_kwargs["enable_planning"])
        self.assertIn("action schema", str(agent_kwargs["extend_system_message"]))
        self.assertTrue(captured["browser"].closed)

    def test_structured_llm_exposes_browser_use_model_attributes(self) -> None:
        inner = types.SimpleNamespace(provider="openai", name="glm", model="openai/glm-5.1")
        wrapper = cli.SparkBrowserUseStructuredLLM(inner)

        self.assertEqual(wrapper.provider, "openai")
        self.assertEqual(wrapper.name, "glm")
        self.assertEqual(wrapper.model, "openai/glm-5.1")
        self.assertEqual(wrapper.model_name, "openai/glm-5.1")


if __name__ == "__main__":
    unittest.main()
