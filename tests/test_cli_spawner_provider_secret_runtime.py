from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import Module, module_runtime_env, read_generated_env, write_setup_runtime_config


def module(name: str, root: Path) -> Module:
    return Module(
        name=name,
        path=root / name,
        manifest={
            "module": {"name": name, "version": "1.0.0", "kind": "service", "plane": "execution"},
            "config": {},
        },
    )


class CliSpawnerProviderSecretRuntimeTests(unittest.TestCase):
    def test_spawner_runtime_resolves_only_the_selected_mission_provider_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "modules"
            config_dir.mkdir(parents=True)
            spawner = module("spawner-ui", root)
            (config_dir / "spawner-ui.env").write_text(
                "DEFAULT_MISSION_PROVIDER=openrouter\n"
                "SPARK_MISSION_LLM_PROVIDER=openrouter\n"
                "SPARK_CHAT_LLM_PROVIDER=zai\n",
                encoding="utf-8",
            )

            def fetch(secret_id: str) -> str | None:
                return {
                    "llm.openrouter.api_key": "mission-openrouter-key",
                    "llm.zai.api_key": "unselected-chat-key",
                }.get(secret_id)

            with patch("spark_cli.cli.MODULE_CONFIG_DIR", config_dir), \
                 patch("spark_cli.cli.shell_command_env", return_value={}), \
                 patch("spark_cli.cli.keychain_env_for_module", return_value={}), \
                 patch("spark_cli.cli.keychain_env_for_telegram_profile", side_effect=AssertionError("Telegram profile secret requested for Spawner")), \
                 patch("spark_cli.cli.fetch_secret", side_effect=fetch):
                runtime = module_runtime_env(spawner)

        self.assertEqual(runtime["OPENROUTER_API_KEY"], "mission-openrouter-key")
        self.assertNotIn("ZAI_API_KEY", runtime)
        self.assertNotIn("BOT_TOKEN", runtime)

    def test_generated_spawner_config_remains_provider_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "modules"
            gateway = module("spark-telegram-bot", root)
            spawner = module("spawner-ui", root)
            builder = module("spark-intelligence-builder", root)
            modules = {item.name: item for item in (gateway, spawner, builder)}
            generated = {
                gateway.name: {},
                spawner.name: {
                    "DEFAULT_MISSION_PROVIDER": "openrouter",
                    "SPARK_MISSION_LLM_PROVIDER": "openrouter",
                    "OPENROUTER_API_KEY": "plaintext-key",
                },
                builder.name: {},
            }
            with patch.multiple("spark_cli.cli", SPARK_HOME=root, MODULE_CONFIG_DIR=config_dir), \
                 patch("spark_cli.cli.initialize_builder_runtime_home", return_value=[]), \
                 patch("spark_cli.cli.persist_keychain_secrets", return_value={"llm.openrouter.api_key": "keychain"}), \
                 patch("spark_cli.cli.persist_governor_hmac_secret"), \
                 patch("spark_cli.cli.build_module_envs", return_value=generated), \
                 patch("spark_cli.cli.preserve_level5_guardrails", side_effect=lambda _name, env: env), \
                 patch("spark_cli.cli.refresh_telegram_profile_envs"):
                write_setup_runtime_config(
                    Namespace(),
                    modules,
                    [gateway, spawner, builder],
                    {"llm.openrouter.api_key": "plaintext-key"},
                    {},
                )

            persisted = read_generated_env(config_dir / "spawner-ui.env")

        self.assertEqual(persisted["SPARK_MISSION_LLM_PROVIDER"], "openrouter")
        self.assertNotIn("OPENROUTER_API_KEY", persisted)


if __name__ == "__main__":
    unittest.main()
