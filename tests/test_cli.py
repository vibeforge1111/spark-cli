from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from spark_cli.cli import Module, detect_ingress_owner, expand_targets, summarize_command_output, update_env_file


def make_module(name: str, capabilities: list[str]) -> Module:
    return Module(
        name=name,
        path=Path(f"C:/tmp/{name}"),
        manifest={
            "module": {
                "name": name,
                "version": "0.1.0",
                "kind": "service",
                "plane": "ingress",
            },
            "provides": {
                "capabilities": capabilities,
            },
        },
    )


class SparkCliTests(unittest.TestCase):
    def test_detect_ingress_owner_returns_single_owner(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        runtime = make_module("spark-intelligence-builder", ["spark.runtime"])
        owner = detect_ingress_owner([gateway, runtime])
        self.assertEqual(owner.name, "spark-telegram-bot")

    def test_expand_targets_expands_bundle_name(self) -> None:
        modules = {
            "spark-telegram-bot": object(),
            "spark-intelligence-builder": object(),
            "spawner-ui": object(),
        }
        self.assertEqual(
            expand_targets("telegram-starter", modules, include_all=False),
            ["spark-telegram-bot", "spark-intelligence-builder", "spawner-ui"],
        )

    def test_summarize_command_output_skips_npm_prefix_lines(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout="> spawner-ui@0.0.1 health:spark\n> node scripts/health-spark.mjs\nSpawner UI unhealthy: cannot reach http://127.0.0.1:5173/api/providers\n",
            stderr="",
        )
        self.assertEqual(
            summarize_command_output(result),
            "Spawner UI unhealthy: cannot reach http://127.0.0.1:5173/api/providers",
        )

    def test_update_env_file_replaces_managed_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("EXISTING=1\n# --- spark-cli managed start ---\nOLD=1\n# --- spark-cli managed end ---\n", encoding="utf-8")

            update_env_file(env_path, {"BOT_TOKEN": "abc", "ADMIN_TELEGRAM_IDS": "123"})
            contents = env_path.read_text(encoding="utf-8")

            self.assertIn("EXISTING=1", contents)
            self.assertIn("BOT_TOKEN=abc", contents)
            self.assertIn("ADMIN_TELEGRAM_IDS=123", contents)
            self.assertNotIn("OLD=1", contents)


if __name__ == "__main__":
    unittest.main()
