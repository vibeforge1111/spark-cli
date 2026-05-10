from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from spark_cli.cli import build_parser
from spark_cli.system_map import count_safe_jsonl, summarize_pids, summarize_setup


class SparkSystemMapTests(unittest.TestCase):
    def test_setup_summary_redacts_secret_names_and_profile_details(self) -> None:
        summary = summarize_setup(
            {
                "bundle": "telegram-starter",
                "modules": ["spark-telegram-bot"],
                "secret_keys": ["telegram.bot_token", "llm.zai.api_key"],
                "telegram_profiles": {
                    "main": {
                        "bot_token_secret": "telegram.bot_token",
                        "webhook_url": "http://127.0.0.1:9999/spawner-events",
                    }
                },
                "llm": {"roles": {"builder": {"provider": "zai", "auth_mode": "api_key"}}},
            }
        )

        encoded = json.dumps(summary)
        self.assertEqual(summary["secret_key_count"], 2)
        self.assertEqual(summary["telegram_profile_count"], 1)
        self.assertIn("key_based", encoded)
        self.assertNotIn("telegram.bot_token", encoded)
        self.assertNotIn("api_key", encoded)
        self.assertNotIn("webhook_url", encoded)

    def test_jsonl_counter_only_keeps_allowlisted_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"event_type": "route_selected", "summary": "private text"}),
                        json.dumps({"event_type": "route_selected", "token": "secret"}),
                        "{not-json",
                    ]
                ),
                encoding="utf-8",
            )
            summary = count_safe_jsonl(path)

        encoded = json.dumps(summary)
        self.assertEqual(summary["line_count"], 3)
        self.assertEqual(summary["parsed_count"], 2)
        self.assertEqual(summary["parse_errors"], 1)
        self.assertEqual(summary["safe_value_counts"]["event_type"]["route_selected"], 2)
        self.assertIn("summary", summary["top_keys"])
        self.assertNotIn("private text", encoded)
        self.assertNotIn("secret", encoded)

    def test_process_summary_omits_raw_command_args(self) -> None:
        summary = summarize_pids(
            {
                "spark-example": {
                    "module": "spark-example",
                    "pid": 123,
                    "command": ["python", "server.py", "--token", "secret-value"],
                }
            }
        )

        encoded = json.dumps(summary)
        self.assertEqual(summary[0]["command_arg_count"], 4)
        self.assertTrue(summary[0]["command_configured"])
        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("--token", encoded)

    def test_os_compile_command_writes_redacted_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            spark_home = root / ".spark"
            state = spark_home / "state"
            repo = desktop / "spark-example"
            out = root / "out"
            desktop.mkdir()
            state.mkdir(parents=True)
            repo.mkdir()

            registry = root / "registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "modules": {
                            "spark-example": {
                                "source": "https://example.test/spark-example",
                                "summary": "Example module",
                                "blessed": True,
                            }
                        },
                        "bundles": {"starter": {"modules": ["spark-example"]}},
                    }
                ),
                encoding="utf-8",
            )
            (state / "installed.json").write_text(
                json.dumps({"spark-example": {"path": str(repo), "kind": "runtime", "plane": "runtime"}}),
                encoding="utf-8",
            )
            (state / "setup.json").write_text(
                json.dumps(
                    {
                        "bundle": "starter",
                        "modules": ["spark-example"],
                        "secret_keys": ["telegram.bot_token"],
                        "telegram_profiles": {"main": {"webhook_url": "http://127.0.0.1/hook"}},
                    }
                ),
                encoding="utf-8",
            )
            (state / "pids.json").write_text("{}", encoding="utf-8")
            (repo / "spark.toml").write_text(
                """
[module]
name = "spark-example"
version = "0.1.0"
kind = "runtime"
plane = "runtime"
description = "Example module"

[provides]
capabilities = ["spark.example"]

[needs]
modules = []
capabilities = []
secrets = ["example.secret"]

[claims]
secrets = []
ports = []
routes = []
""".strip(),
                encoding="utf-8",
            )

            args = build_parser().parse_args(
                [
                    "os",
                    "compile",
                    "--desktop",
                    str(desktop),
                    "--spark-home",
                    str(spark_home),
                    "--registry",
                    str(registry),
                    "--out",
                    str(out),
                    "--json",
                ]
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = args.func(args)

            summary = json.loads(stdout.getvalue())
            system_map = json.loads((out / "system-map.json").read_text(encoding="utf-8"))
            output_text = "\n".join(path.read_text(encoding="utf-8") for path in out.glob("*") if path.is_file())

            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["modules"], 1)
            self.assertEqual(system_map["setup"]["secret_key_count"], 1)
            self.assertTrue((out / "authority-view.json").exists())
            self.assertTrue((out / "capability-catalog.json").exists())
            self.assertTrue((out / "trace-index.json").exists())
            self.assertNotIn("telegram.bot_token", output_text)
            self.assertNotIn("webhook_url", output_text)


if __name__ == "__main__":
    unittest.main()
