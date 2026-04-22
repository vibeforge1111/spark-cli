from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import (
    build_module_repair_hints,
    build_status_repair_hints,
    build_module_envs,
    collect_secret_requirements,
    collect_secret_values,
    CONFIG_PATH,
    install_module_record,
    load_json,
    Module,
    MODULE_CONFIG_DIR,
    REGISTRY_PATH,
    detect_uninstall_blockers,
    detect_capability_conflicts,
    detect_ingress_owner,
    execute_install_commands,
    expand_targets,
    generated_module_env_path,
    remove_managed_env_block,
    pid_is_running,
    print_install_summary,
    ready_timeout_seconds,
    wait_for_ready_check,
    resolve_bundle_names,
    resolve_install_target,
    resolve_start_modules,
    resolve_stop_module_names,
    summarize_command_output,
    update_setup_state_after_uninstall,
    update_env_file,
)


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

    def test_resolve_install_target_prefers_registry_module_name(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        resolved = resolve_install_target("spark-telegram-bot", {"spark-telegram-bot": gateway})
        self.assertEqual(resolved.name, "spark-telegram-bot")

    def test_resolve_install_target_accepts_local_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir) / "module"
            repo_path.mkdir()
            (repo_path / "spark.toml").write_text(
                '[module]\nname = "test-module"\nversion = "0.1.0"\nkind = "service"\nplane = "execution"\n',
                encoding="utf-8",
            )
            resolved = resolve_install_target(str(repo_path), {})
            self.assertEqual(resolved.name, "test-module")

    def test_resolve_bundle_names_reads_registry_bundle(self) -> None:
        self.assertEqual(
            resolve_bundle_names("telegram-starter"),
            ["spark-telegram-bot", "spark-intelligence-builder", "spawner-ui"],
        )

    def test_print_install_summary_mentions_ingress_owner(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        runtime = make_module("spark-intelligence-builder", ["spark.runtime"])
        with patch("sys.stdout", new_callable=StringIO) as stdout:
            print_install_summary([gateway, runtime])
            output = stdout.getvalue()
        self.assertIn("Install plan:", output)
        self.assertIn("Telegram ingress owner: spark-telegram-bot", output)

    def test_detect_capability_conflicts_allows_single_ingress_owner(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        runtime = make_module("spark-intelligence-builder", ["spark.runtime"])
        self.assertEqual(detect_capability_conflicts([gateway, runtime], {}), [])

    def test_detect_capability_conflicts_rejects_multiple_ingress_owners(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        other_gateway = make_module("other-telegram-gateway", ["telegram.ingress"])
        conflicts = detect_capability_conflicts([gateway, other_gateway], {})
        self.assertEqual(
            conflicts,
            ["multiple telegram ingress owners declared: other-telegram-gateway, spark-telegram-bot"],
        )

    def test_detect_uninstall_blockers_respects_needs_modules(self) -> None:
        builder = Module(
            name="spark-intelligence-builder",
            path=Path("C:/tmp/spark-intelligence-builder"),
            manifest={"module": {"name": "spark-intelligence-builder", "version": "0.1.0", "kind": "runtime", "plane": "runtime"}},
        )
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"modules": ["spark-intelligence-builder"]},
            },
        )
        blockers = detect_uninstall_blockers([builder], {builder.name: builder, gateway.name: gateway})
        self.assertEqual(blockers, ["spark-telegram-bot depends on spark-intelligence-builder"])

    def test_resolve_start_modules_orders_dependencies_before_gateway(self) -> None:
        builder = Module(
            name="spark-intelligence-builder",
            path=Path("C:/tmp/spark-intelligence-builder"),
            manifest={"module": {"name": "spark-intelligence-builder", "version": "0.1.0", "kind": "runtime", "plane": "runtime"}},
        )
        spawner = Module(
            name="spawner-ui",
            path=Path("C:/tmp/spawner-ui"),
            manifest={"module": {"name": "spawner-ui", "version": "0.0.1", "kind": "app", "plane": "execution"}},
        )
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"modules": ["spark-intelligence-builder", "spawner-ui"]},
            },
        )
        ordered = resolve_start_modules(
            "spark-telegram-bot",
            {
                gateway.name: gateway,
                builder.name: builder,
                spawner.name: spawner,
            },
        )
        self.assertEqual(
            [module.name for module in ordered],
            ["spark-intelligence-builder", "spawner-ui", "spark-telegram-bot"],
        )

    def test_resolve_start_modules_fails_when_dependency_not_installed(self) -> None:
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"modules": ["spark-intelligence-builder"]},
            },
        )
        with self.assertRaises(SystemExit) as error:
            resolve_start_modules("spark-telegram-bot", {gateway.name: gateway})
        self.assertIn("required modules are not installed", str(error.exception))

    def test_resolve_stop_module_names_stops_dependents_before_dependency(self) -> None:
        builder = Module(
            name="spark-intelligence-builder",
            path=Path("C:/tmp/spark-intelligence-builder"),
            manifest={"module": {"name": "spark-intelligence-builder", "version": "0.1.0", "kind": "runtime", "plane": "runtime"}},
        )
        spawner = Module(
            name="spawner-ui",
            path=Path("C:/tmp/spawner-ui"),
            manifest={"module": {"name": "spawner-ui", "version": "0.0.1", "kind": "app", "plane": "execution"}},
        )
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"modules": ["spark-intelligence-builder", "spawner-ui"]},
            },
        )
        order = resolve_stop_module_names(
            "spark-intelligence-builder",
            {
                gateway.name: gateway,
                builder.name: builder,
                spawner.name: spawner,
            },
            {
                gateway.name: {"pid": 100},
                builder.name: {"pid": 200},
            },
        )
        self.assertEqual(order, ["spark-telegram-bot", "spark-intelligence-builder"])

    def test_collect_secret_requirements_maps_manifest_secret_blocks(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token", "telegram.admin_ids"]},
                "secrets": {
                    "telegram_bot_token": {"prompt": "Bot token", "required": True, "env_var": "BOT_TOKEN"},
                    "telegram_admin_ids": {"prompt": "Admin ids", "required": True, "env_var": "ADMIN_TELEGRAM_IDS"},
                },
            },
        )
        requirements = collect_secret_requirements([module])
        self.assertEqual(requirements["telegram.bot_token"]["env_var"], "BOT_TOKEN")
        self.assertEqual(requirements["telegram.admin_ids"]["env_var"], "ADMIN_TELEGRAM_IDS")

    def test_collect_secret_values_accepts_generic_secret_flags(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token"]},
                "secrets": {
                    "telegram_bot_token": {"prompt": "Bot token", "required": True, "env_var": "BOT_TOKEN"},
                },
            },
        )

        class Args:
            secret = ["telegram.bot_token=abc"]
            bot_token = None
            admin_telegram_ids = None
            telegram_webhook_secret = None

        values = collect_secret_values(Args(), [module])
        self.assertEqual(values["telegram.bot_token"], "abc")

    def test_generated_module_env_path_uses_canonical_module_config_dir(self) -> None:
        module = make_module("spawner-ui", ["mission.execution"])
        self.assertEqual(generated_module_env_path(module), MODULE_CONFIG_DIR / "spawner-ui.env")

    def test_build_module_envs_routes_telegram_secret_only_to_gateway(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])

        class Args:
            spawner_ui_url = "http://127.0.0.1:5173"
            telegram_gateway_mode = "auto"
            telegram_webhook_url = None

        envs = build_module_envs(
            Args(),
            {
                gateway.name: gateway,
                builder.name: builder,
                spawner.name: spawner,
            },
            {
                "telegram.bot_token": "abc",
                "telegram.admin_ids": "123",
                "telegram.webhook_secret": "secret",
            },
        )
        self.assertEqual(envs["spark-telegram-bot"]["BOT_TOKEN"], "abc")
        self.assertNotIn("BOT_TOKEN", envs["spawner-ui"])

    def test_pid_is_running_detects_current_process(self) -> None:
        self.assertTrue(pid_is_running(os.getpid()))

    def test_ready_timeout_seconds_reads_healthcheck_timeout(self) -> None:
        module = Module(
            name="timeout-target",
            path=Path("C:/tmp/timeout-target"),
            manifest={
                "module": {"name": "timeout-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "healthcheck": {"timeout_seconds": 17},
            },
        )
        self.assertEqual(ready_timeout_seconds(module), 17)

    def test_wait_for_ready_check_runs_shell_ready_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = Module(
                name="ready-target",
                path=Path(tmp_dir),
                manifest={
                    "module": {"name": "ready-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                    "run": {"default": {"ready_check": 'python -c "print(\'ready\')"' }},
                    "healthcheck": {"timeout_seconds": 2},
                },
            )
            ready, detail = wait_for_ready_check(module)
            self.assertTrue(ready)
            self.assertEqual(detail, "ready")

    def test_remove_managed_env_block_strips_only_managed_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "KEEP=1\n# --- spark-cli managed start ---\nBOT_TOKEN=abc\n# --- spark-cli managed end ---\n",
                encoding="utf-8",
            )
            remove_managed_env_block(env_path)
            self.assertEqual(env_path.read_text(encoding="utf-8"), "KEEP=1\n")

    def test_execute_install_commands_runs_manifest_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module_path = Path(tmp_dir)
            marker_path = module_path / "installed.txt"
            module = Module(
                name="test-module",
                path=module_path,
                manifest={
                    "module": {"name": "test-module", "version": "0.1.0", "kind": "service", "plane": "execution"},
                    "install": {
                        "dev": {
                            "commands": [
                                f'python -c "from pathlib import Path; Path(r\'{marker_path}\').write_text(\'ok\', encoding=\'utf-8\')"'
                            ]
                        }
                    },
                },
            )
            execute_install_commands(module)
            self.assertEqual(marker_path.read_text(encoding="utf-8"), "ok")

    def test_install_module_record_writes_provenance_metadata(self) -> None:
        original = REGISTRY_PATH.read_text(encoding="utf-8") if REGISTRY_PATH.exists() else None
        try:
            module = Module(
                name="spark-telegram-bot",
                path=Path("C:/tmp/spark-telegram-bot"),
                manifest={
                    "module": {
                        "name": "spark-telegram-bot",
                        "version": "1.0.0",
                        "kind": "service",
                        "plane": "ingress",
                        "description": "Telegram gateway",
                    }
                },
            )
            install_module_record(
                module,
                operation="install",
                source_kind="bundle",
                source_target="telegram-starter",
                bundle_name="telegram-starter",
                skip_install_commands=True,
            )
            install_module_record(
                module,
                operation="update",
                source_kind="bundle",
                source_target="telegram-starter",
                bundle_name="telegram-starter",
                skip_install_commands=False,
            )
            payload = load_json(REGISTRY_PATH, {})
            record = payload["spark-telegram-bot"]
            self.assertEqual(record["installed_via"]["kind"], "bundle")
            self.assertEqual(record["installed_via"]["target"], "telegram-starter")
            self.assertEqual(record["installed_via"]["bundle"], "telegram-starter")
            self.assertEqual(record["bundle_provenance"], ["telegram-starter"])
            self.assertEqual(record["last_install"]["status"], "ok")
            self.assertTrue(record["last_install"]["skip_install_commands"])
            self.assertEqual(record["last_update"]["status"], "ok")
            self.assertFalse(record["last_update"]["skip_install_commands"])
            self.assertEqual(record["installed_at"], record["last_install"]["at"])
            self.assertIn("updated_at", record)
        finally:
            if original is not None:
                REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
                REGISTRY_PATH.write_text(original, encoding="utf-8")
            elif REGISTRY_PATH.exists():
                REGISTRY_PATH.unlink()

    def test_build_module_repair_hints_reports_missing_dependency_and_config_regen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = Module(
                name="repair-target",
                path=Path(tmp_dir),
                manifest={
                    "module": {"name": "repair-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                    "needs": {"modules": ["spark-intelligence-builder"]},
                    "config": {"output": ".env", "installer_owned": True},
                    "healthcheck": {"failure_hint": "Run the module doctor."},
                },
            )
            result = {"name": "repair-target", "healthy": False, "failure_hint": "Run the module doctor."}
            hints = build_module_repair_hints(module, result, {"repair-target": result}, {"bundle": "telegram-starter"})
            self.assertIn("Install missing dependencies first: spark-intelligence-builder.", hints)
            self.assertIn("Run the module doctor.", hints)
            self.assertIn("Run `spark setup telegram-starter` to regenerate installer-owned config.", hints)

    def test_build_status_repair_hints_reports_missing_ingress_owner_and_unhealthy_dependency(self) -> None:
        builder = Module(
            name="spark-intelligence-builder",
            path=Path("C:/tmp/spark-intelligence-builder"),
            manifest={
                "module": {"name": "spark-intelligence-builder", "version": "0.1.0", "kind": "runtime", "plane": "runtime"}
            },
        )
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"modules": ["spark-intelligence-builder"]},
            },
        )
        hints = build_status_repair_hints(
            {gateway.name: gateway},
            [
                {"name": "spark-telegram-bot", "healthy": False},
            ],
            {"telegram_ingress_owner": "spark-intelligence-builder"},
        )
        self.assertIn(
            "Configured Telegram ingress owner `spark-intelligence-builder` is not installed. Run `spark setup telegram-starter`.",
            hints,
        )
        self.assertIn("spark-telegram-bot is missing dependencies: spark-intelligence-builder.", hints)

    def test_update_setup_state_after_uninstall_clears_empty_setup(self) -> None:
        original = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                '{\n  "modules": ["spark-telegram-bot"],\n  "telegram_ingress_owner": "spark-telegram-bot"\n}\n',
                encoding="utf-8",
            )
            update_setup_state_after_uninstall(["spark-telegram-bot"])
            self.assertFalse(CONFIG_PATH.exists())
        finally:
            if original is not None:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                CONFIG_PATH.write_text(original, encoding="utf-8")
            elif CONFIG_PATH.exists():
                CONFIG_PATH.unlink()


if __name__ == "__main__":
    unittest.main()
