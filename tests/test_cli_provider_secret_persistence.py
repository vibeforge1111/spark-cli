from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import Module, module_runtime_env, persist_keychain_secrets, read_generated_env, write_setup_runtime_config


def gateway_module(root: Path) -> Module:
    return Module(
        name="spark-telegram-bot",
        path=root / "spark-telegram-bot",
        manifest={
            "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
            "needs": {"secrets": ["telegram.bot_token"]},
            "secrets": {
                "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
            },
        },
    )


class CliProviderSecretPersistenceTests(unittest.TestCase):
    def test_setup_persists_provider_secret_without_requiring_module_manifest_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            gateway = gateway_module(Path(tmp_dir))
            with patch("spark_cli.cli.store_secret", return_value="keychain") as store:
                report = persist_keychain_secrets([gateway], {"llm.kimi.api_key": "kimi-secret"})

        self.assertEqual(report, {"llm.kimi.api_key": "keychain"})
        store.assert_called_once_with("llm.kimi.api_key", "kimi-secret", preferred="keychain")

    def test_setup_rewrite_removes_provider_secret_from_generated_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "modules"
            gateway = gateway_module(root)
            generated = {
                gateway.name: {
                    "LLM_PROVIDER": "kimi",
                    "SPARK_CHAT_LLM_PROVIDER": "kimi",
                    "KIMI_MODEL": "kimi-k2.6",
                    "KIMI_API_KEY": "plaintext-key",
                }
            }
            with patch.multiple("spark_cli.cli", SPARK_HOME=root, MODULE_CONFIG_DIR=config_dir), \
                 patch("spark_cli.cli.initialize_builder_runtime_home", return_value=[]), \
                 patch("spark_cli.cli.persist_keychain_secrets", return_value={"llm.kimi.api_key": "keychain"}), \
                 patch("spark_cli.cli.persist_governor_hmac_secret"), \
                 patch("spark_cli.cli.build_module_envs", return_value=generated), \
                 patch("spark_cli.cli.preserve_level5_guardrails", side_effect=lambda _name, env: env), \
                 patch("spark_cli.cli.refresh_telegram_profile_envs"):
                write_setup_runtime_config(Namespace(), {gateway.name: gateway}, [gateway], {}, {})

            persisted = read_generated_env(config_dir / "spark-telegram-bot.env")

        self.assertNotIn("KIMI_API_KEY", persisted)
        self.assertEqual(persisted["SPARK_CHAT_LLM_PROVIDER"], "kimi")
        self.assertEqual(persisted["KIMI_MODEL"], "kimi-k2.6")

    def test_gateway_runtime_resolves_only_selected_provider_secret_from_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config" / "modules"
            config_dir.mkdir(parents=True)
            (config_dir / "spark-telegram-bot.env").write_text(
                "SPARK_CHAT_LLM_PROVIDER=kimi\nKIMI_API_KEY=stale-plaintext\nKIMI_MODEL=kimi-k2.6\n",
                encoding="utf-8",
            )
            gateway = gateway_module(root)

            def fetch(secret_id: str) -> str | None:
                return {
                    "llm.kimi.api_key": "stored-kimi-key",
                    "llm.openai.api_key": "unselected-openai-key",
                }.get(secret_id)

            with patch("spark_cli.cli.MODULE_CONFIG_DIR", config_dir), \
                 patch("spark_cli.cli.shell_command_env", return_value={}), \
                 patch("spark_cli.cli.keychain_env_for_module", return_value={}), \
                 patch("spark_cli.cli.keychain_env_for_telegram_profile", return_value={}), \
                 patch("spark_cli.cli.fetch_secret", side_effect=fetch):
                runtime = module_runtime_env(gateway)

        self.assertEqual(runtime["KIMI_API_KEY"], "stored-kimi-key")
        self.assertNotIn("OPENAI_API_KEY", runtime)
        self.assertNotEqual(runtime["KIMI_API_KEY"], "stale-plaintext")


if __name__ == "__main__":
    unittest.main()
