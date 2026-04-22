from __future__ import annotations

import os
import shutil
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
    detect_runtime_binary,
    clone_module_source,
    clone_target_for_module,
    delete_secret,
    fetch_secret,
    infer_module_name_from_url,
    is_git_source,
    module_is_git_managed,
    normalize_git_url,
    pull_module_source,
    install_module_record,
    keychain_env_for_module,
    list_stored_secrets,
    load_json,
    module_log_path,
    module_secret_env_bindings,
    check_runtime_version_for_module,
    enforce_runtime_versions,
    manifest_schema_version,
    needs_capabilities,
    parse_version_constraint,
    parse_version_tuple,
    runtime_version_satisfies,
    validate_capability_needs_for_install,
    validate_manifest_schema,
    persist_keychain_secrets,
    split_secret_bindings,
    store_secret,
    strip_keychain_env_vars,
    tail_log_lines,
    Module,
    MODULE_CONFIG_DIR,
    REGISTRY_PATH,
    capability_providers,
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
    required_runtimes_for_modules,
    run_setup_wizard,
    setup_is_interactive,
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
    def test_parse_version_tuple_extracts_digits(self) -> None:
        self.assertEqual(parse_version_tuple("Python 3.13.5"), (3, 13, 5))
        self.assertEqual(parse_version_tuple("v22.18.0"), (22, 18, 0))
        self.assertEqual(parse_version_tuple("uv 0.9.16 (abcd)"), (0, 9, 16))
        self.assertEqual(parse_version_tuple("22"), (22,))
        self.assertIsNone(parse_version_tuple(""))
        self.assertIsNone(parse_version_tuple("no digits here"))

    def test_parse_version_constraint_handles_default_operator_and_commas(self) -> None:
        self.assertEqual(parse_version_constraint(">=3.11"), [(">=", (3, 11))])
        self.assertEqual(parse_version_constraint("3.11"), [(">=", (3, 11))])
        self.assertEqual(
            parse_version_constraint(">=3.11, <4"),
            [(">=", (3, 11)), ("<", (4,))],
        )

    def test_runtime_version_satisfies_true_when_actual_meets_constraint(self) -> None:
        ok, detail = runtime_version_satisfies("Python 3.13.5", ">=3.11")
        self.assertTrue(ok)
        self.assertIn("3.13.5", detail)

    def test_runtime_version_satisfies_false_when_actual_below_constraint(self) -> None:
        ok, detail = runtime_version_satisfies("v20.10.0", ">=22")
        self.assertFalse(ok)
        self.assertIn("20.10.0 does not satisfy >=22", detail)

    def test_runtime_version_satisfies_skips_when_detected_unparseable(self) -> None:
        ok, detail = runtime_version_satisfies("", ">=3.11")
        self.assertTrue(ok)
        self.assertIn("skipping", detail)

    def test_check_runtime_version_for_module_skips_when_no_runtime_block(self) -> None:
        module = Module(
            name="no-runtime",
            path=Path("C:/tmp/no-runtime"),
            manifest={"module": {"name": "no-runtime", "version": "0.1.0", "kind": "service", "plane": "execution"}},
        )
        ok, detail = check_runtime_version_for_module(module)
        self.assertTrue(ok)
        self.assertEqual(detail, "")

    def test_check_runtime_version_for_module_fails_when_binary_missing(self) -> None:
        module = Module(
            name="missing-runtime",
            path=Path("C:/tmp/missing"),
            manifest={
                "module": {"name": "missing-runtime", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "runtime": {"kind": "definitely-not-a-real-tool-xyz", "version": ">=1"},
            },
        )
        ok, detail = check_runtime_version_for_module(module)
        self.assertFalse(ok)
        self.assertIn("not on PATH", detail)

    def test_check_runtime_version_for_module_passes_for_present_python(self) -> None:
        module = Module(
            name="python-module",
            path=Path("C:/tmp/python-module"),
            manifest={
                "module": {"name": "python-module", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "runtime": {"kind": "python", "version": ">=3.0"},
            },
        )
        ok, detail = check_runtime_version_for_module(module)
        self.assertTrue(ok)
        self.assertIn("satisfied", detail)

    def test_enforce_runtime_versions_raises_with_all_failures(self) -> None:
        missing_a = Module(
            name="missing-a",
            path=Path("C:/tmp/a"),
            manifest={
                "module": {"name": "missing-a", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "runtime": {"kind": "definitely-not-a-real-tool-xyz", "version": ">=1"},
            },
        )
        missing_b = Module(
            name="missing-b",
            path=Path("C:/tmp/b"),
            manifest={
                "module": {"name": "missing-b", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "runtime": {"kind": "also-fake-tool-xyz", "version": ">=1"},
            },
        )
        with self.assertRaises(SystemExit) as error:
            enforce_runtime_versions([missing_a, missing_b])
        text = str(error.exception)
        self.assertIn("missing-a", text)
        self.assertIn("missing-b", text)

    def test_manifest_schema_version_defaults_to_one(self) -> None:
        module = Module(name="m", path=Path("C:/tmp/m"), manifest={"module": {"name": "m"}})
        self.assertEqual(manifest_schema_version(module), 1)

    def test_validate_manifest_schema_rejects_future_schema(self) -> None:
        future = Module(
            name="from-future",
            path=Path("C:/tmp/from-future"),
            manifest={"schema": 99, "module": {"name": "from-future"}},
        )
        with self.assertRaises(SystemExit) as error:
            validate_manifest_schema(future)
        self.assertIn("schema 99", str(error.exception))

    def test_validate_manifest_schema_accepts_current_and_missing(self) -> None:
        current = Module(name="c", path=Path("C:/tmp/c"), manifest={"schema": 1, "module": {"name": "c"}})
        implicit = Module(name="i", path=Path("C:/tmp/i"), manifest={"module": {"name": "i"}})
        validate_manifest_schema(current)
        validate_manifest_schema(implicit)

    def test_needs_capabilities_reads_manifest_block(self) -> None:
        module = Module(
            name="consumer",
            path=Path("C:/tmp/consumer"),
            manifest={
                "module": {"name": "consumer", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                "needs": {"capabilities": ["memory.store", "spark.runtime"]},
            },
        )
        self.assertEqual(needs_capabilities(module), ["memory.store", "spark.runtime"])

    def test_capability_providers_returns_sorted_names(self) -> None:
        alpha = make_module("alpha", ["memory.store"])
        beta = make_module("beta", ["memory.store", "other.thing"])
        providers = capability_providers("memory.store", {alpha.name: alpha, beta.name: beta})
        self.assertEqual(providers, ["alpha", "beta"])

    def test_validate_capability_needs_satisfied_by_same_batch(self) -> None:
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"capabilities": ["spark.runtime"]},
            },
        )
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        errors = validate_capability_needs_for_install([gateway, builder], {}, {})
        self.assertEqual(errors, [])

    def test_validate_capability_needs_suggests_discoverable_provider(self) -> None:
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"capabilities": ["spark.runtime"]},
            },
        )
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        errors = validate_capability_needs_for_install([gateway], {}, {builder.name: builder})
        self.assertEqual(
            errors,
            ["spark-telegram-bot needs capability `spark.runtime`; install one of: spark-intelligence-builder"],
        )

    def test_validate_capability_needs_reports_completely_missing(self) -> None:
        consumer = Module(
            name="consumer",
            path=Path("C:/tmp/consumer"),
            manifest={
                "module": {"name": "consumer", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                "needs": {"capabilities": ["nobody.has.this"]},
            },
        )
        errors = validate_capability_needs_for_install([consumer], {}, {})
        self.assertEqual(
            errors,
            ["consumer needs capability `nobody.has.this` but no discoverable module provides it"],
        )

    def test_validate_capability_needs_accepts_already_installed_provider(self) -> None:
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"capabilities": ["spark.runtime"]},
            },
        )
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        errors = validate_capability_needs_for_install([gateway], {builder.name: builder}, {})
        self.assertEqual(errors, [])

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

    def test_required_runtimes_for_modules_dedups_across_bundle(self) -> None:
        python_module = Module(
            name="python-a",
            path=Path("C:/tmp/python-a"),
            manifest={
                "module": {"name": "python-a", "version": "0.1.0", "kind": "runtime", "plane": "runtime"},
                "runtime": {"kind": "python", "package_manager": "uv"},
            },
        )
        python_module_b = Module(
            name="python-b",
            path=Path("C:/tmp/python-b"),
            manifest={
                "module": {"name": "python-b", "version": "0.1.0", "kind": "runtime", "plane": "runtime"},
                "runtime": {"kind": "python", "package_manager": "uv"},
            },
        )
        node_module = Module(
            name="node-app",
            path=Path("C:/tmp/node-app"),
            manifest={
                "module": {"name": "node-app", "version": "0.1.0", "kind": "app", "plane": "execution"},
                "runtime": {"kind": "node", "package_manager": "bun"},
            },
        )
        self.assertEqual(
            required_runtimes_for_modules([python_module, python_module_b, node_module]),
            ["uv", "python", "bun", "node"],
        )

    def test_detect_runtime_binary_reports_present_for_python(self) -> None:
        info = detect_runtime_binary("python")
        self.assertTrue(info["present"])
        self.assertIsNotNone(info["path"])

    def test_detect_runtime_binary_reports_absent_for_missing_tool(self) -> None:
        info = detect_runtime_binary("definitely-not-a-real-tool-xyz")
        self.assertFalse(info["present"])
        self.assertIsNone(info["path"])
        self.assertIsNone(info["version"])

    def test_setup_is_interactive_honors_non_interactive_flag(self) -> None:
        class Args:
            non_interactive = True
        self.assertFalse(setup_is_interactive(Args()))

    def test_run_setup_wizard_only_prompts_for_missing_secrets(self) -> None:
        requirements = {
            "telegram.bot_token": {"prompt": "Bot token", "required": True},
            "telegram.admin_ids": {"prompt": "Admin ids", "required": True},
            "telegram.webhook_secret": {"prompt": "Webhook secret", "required": False},
        }
        existing = {"telegram.bot_token": "already-set"}
        prompted: list[str] = []

        def fake_getpass(prompt: str) -> str:
            prompted.append(prompt)
            if "Admin ids" in prompt:
                return "123,456"
            if "Webhook secret" in prompt:
                return ""
            return "SHOULD-NOT-HAPPEN"

        with patch("spark_cli.cli.getpass.getpass", side_effect=fake_getpass):
            collected = run_setup_wizard(existing, requirements)
        self.assertEqual(collected["telegram.bot_token"], "already-set")
        self.assertEqual(collected["telegram.admin_ids"], "123,456")
        self.assertNotIn("telegram.webhook_secret", collected)
        self.assertEqual(len(prompted), 2)

    def test_run_setup_wizard_reprompts_when_required_secret_empty(self) -> None:
        requirements = {"telegram.bot_token": {"prompt": "Bot token", "required": True}}
        answers = iter(["", "finally-a-value"])

        with patch("spark_cli.cli.getpass.getpass", side_effect=lambda _prompt: next(answers)):
            collected = run_setup_wizard({}, requirements)
        self.assertEqual(collected["telegram.bot_token"], "finally-a-value")

    def test_collect_secret_values_prompts_when_interactive_and_missing(self) -> None:
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
            secret = None
            bot_token = None
            admin_telegram_ids = None
            telegram_webhook_secret = None
            non_interactive = False

        with patch("spark_cli.cli.getpass.getpass", return_value="prompted-value"):
            values = collect_secret_values(Args(), [module], interactive=True)
        self.assertEqual(values["telegram.bot_token"], "prompted-value")

    def test_collect_secret_values_non_interactive_raises_on_missing(self) -> None:
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
            secret = None
            bot_token = None
            admin_telegram_ids = None
            telegram_webhook_secret = None
            non_interactive = True

        with self.assertRaises(SystemExit) as error:
            collect_secret_values(Args(), [module], interactive=False)
        self.assertIn("Missing required secrets", str(error.exception))

    def test_is_git_source_recognizes_common_url_shapes(self) -> None:
        self.assertTrue(is_git_source("https://github.com/spark/memory"))
        self.assertTrue(is_git_source("git@github.com:spark/memory.git"))
        self.assertTrue(is_git_source("github.com/spark/memory"))
        self.assertTrue(is_git_source("https://gitlab.com/foo/bar.git"))
        self.assertFalse(is_git_source("C:/Users/USER/Desktop/spark-memory"))
        self.assertFalse(is_git_source(""))

    def test_normalize_git_url_adds_https_for_shorthand(self) -> None:
        self.assertEqual(
            normalize_git_url("github.com/spark/memory"),
            "https://github.com/spark/memory",
        )
        self.assertEqual(
            normalize_git_url("https://github.com/spark/memory"),
            "https://github.com/spark/memory",
        )

    def test_infer_module_name_from_url_drops_git_suffix(self) -> None:
        self.assertEqual(infer_module_name_from_url("https://github.com/spark/memory.git"), "memory")
        self.assertEqual(infer_module_name_from_url("https://github.com/spark/memory/"), "memory")
        self.assertEqual(infer_module_name_from_url("git@github.com:spark/memory.git"), "memory")

    def test_module_is_git_managed_detects_spark_modules_dir(self) -> None:
        from spark_cli.cli import SPARK_HOME
        managed = SPARK_HOME / "modules" / "memory" / "source"
        self.assertTrue(module_is_git_managed(managed))
        self.assertFalse(module_is_git_managed(Path("C:/Users/USER/Desktop/memory")))

    def test_clone_module_source_clones_and_pull_updates_from_local_bare_repo(self) -> None:
        if not shutil.which("git"):
            self.skipTest("git not available on PATH")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            work = tmp / "work"
            work.mkdir()
            subprocess.run(["git", "-C", str(work), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", str(work), "config", "user.name", "t"], check=True)
            (work / "spark.toml").write_text(
                '[module]\nname = "git-demo"\nversion = "0.1.0"\nkind = "service"\nplane = "execution"\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(work), "add", "."], check=True)
            subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True)

            bare = tmp / "remote.git"
            subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)

            clone_home = tmp / "spark-home"
            with patch("spark_cli.cli.SPARK_HOME", clone_home):
                cloned = clone_module_source("git-demo", str(bare))
                self.assertTrue((cloned / ".git").exists())
                self.assertTrue((cloned / "spark.toml").exists())
                # Second call returns the same path without re-cloning.
                self.assertEqual(clone_module_source("git-demo", str(bare)), cloned)

                # Add a new commit upstream, verify pull surfaces it.
                (work / "extra.txt").write_text("hello", encoding="utf-8")
                subprocess.run(["git", "-C", str(work), "add", "extra.txt"], check=True)
                subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "second"], check=True)
                subprocess.run(["git", "-C", str(work), "push", "-q", str(bare), "HEAD"], check=True)

                ok, _detail = pull_module_source(cloned)
                self.assertTrue(ok)
                self.assertTrue((cloned / "extra.txt").exists())
                self.assertEqual(clone_target_for_module("git-demo"), clone_home / "modules" / "git-demo" / "source")

    def test_module_secret_env_bindings_returns_env_var_mapping(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token", "telegram.admin_ids"]},
                "secrets": {
                    "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
                    "telegram_admin_ids": {"env_var": "ADMIN_TELEGRAM_IDS", "storage": "file"},
                },
            },
        )
        bindings = module_secret_env_bindings(module)
        by_id = {b["secret_id"]: b for b in bindings}
        self.assertEqual(by_id["telegram.bot_token"]["env_var"], "BOT_TOKEN")
        self.assertEqual(by_id["telegram.bot_token"]["storage"], "keychain")
        self.assertEqual(by_id["telegram.admin_ids"]["storage"], "file")

    def test_split_secret_bindings_separates_keychain_and_file(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token", "telegram.admin_ids"]},
                "secrets": {
                    "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
                    "telegram_admin_ids": {"env_var": "ADMIN_TELEGRAM_IDS", "storage": "file"},
                },
            },
        )
        file_backed, keychain_backed = split_secret_bindings(module)
        self.assertEqual([b["env_var"] for b in file_backed], ["ADMIN_TELEGRAM_IDS"])
        self.assertEqual([b["env_var"] for b in keychain_backed], ["BOT_TOKEN"])

    def test_strip_keychain_env_vars_removes_keychain_backed_keys(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token"]},
                "secrets": {
                    "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
                },
            },
        )
        result = strip_keychain_env_vars(
            {"BOT_TOKEN": "abc", "ADMIN_TELEGRAM_IDS": "123", "SPAWNER_UI_URL": "http://x"},
            module,
        )
        self.assertEqual(result, {"ADMIN_TELEGRAM_IDS": "123", "SPAWNER_UI_URL": "http://x"})

    def test_store_and_fetch_secret_roundtrip_via_file_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "secrets_index.json"
            file_path = Path(tmp_dir) / "secrets.local.json"
            with patch("spark_cli.cli.SECRETS_INDEX_PATH", index_path), \
                 patch("spark_cli.cli.SECRETS_FILE_PATH", file_path), \
                 patch("spark_cli.cli.keychain_available", return_value=False):
                backend = store_secret("telegram.bot_token", "abc", preferred="keychain")
                self.assertEqual(backend, "file")
                self.assertEqual(fetch_secret("telegram.bot_token"), "abc")
                self.assertEqual(list_stored_secrets(), {"telegram.bot_token": "file"})
                self.assertTrue(delete_secret("telegram.bot_token"))
                self.assertIsNone(fetch_secret("telegram.bot_token"))
                self.assertEqual(list_stored_secrets(), {})

    def test_persist_keychain_secrets_stores_only_keychain_declared(self) -> None:
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token", "telegram.admin_ids"]},
                "secrets": {
                    "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
                    "telegram_admin_ids": {"env_var": "ADMIN_TELEGRAM_IDS", "storage": "file"},
                },
            },
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("spark_cli.cli.SECRETS_INDEX_PATH", Path(tmp_dir) / "idx.json"), \
                 patch("spark_cli.cli.SECRETS_FILE_PATH", Path(tmp_dir) / "file.json"), \
                 patch("spark_cli.cli.keychain_available", return_value=False):
                report = persist_keychain_secrets(
                    [gateway],
                    {"telegram.bot_token": "abc", "telegram.admin_ids": "123"},
                )
                self.assertEqual(report, {"telegram.bot_token": "file"})
                self.assertEqual(fetch_secret("telegram.bot_token"), "abc")
                self.assertIsNone(fetch_secret("telegram.admin_ids"))

    def test_keychain_env_for_module_returns_only_stored_bindings(self) -> None:
        gateway = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token", "telegram.webhook_secret"]},
                "secrets": {
                    "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
                    "telegram_webhook_secret": {"env_var": "TELEGRAM_WEBHOOK_SECRET", "storage": "keychain"},
                },
            },
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("spark_cli.cli.SECRETS_INDEX_PATH", Path(tmp_dir) / "idx.json"), \
                 patch("spark_cli.cli.SECRETS_FILE_PATH", Path(tmp_dir) / "file.json"), \
                 patch("spark_cli.cli.keychain_available", return_value=False):
                store_secret("telegram.bot_token", "abc", preferred="keychain")
                env = keychain_env_for_module(gateway)
                self.assertEqual(env, {"BOT_TOKEN": "abc"})

    def test_tail_log_lines_returns_trailing_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "process.log"
            log_path.write_text("\n".join(f"line-{n}" for n in range(1, 11)) + "\n", encoding="utf-8")
            last_three = tail_log_lines(log_path, 3)
            self.assertEqual(last_three, ["line-8\n", "line-9\n", "line-10\n"])

    def test_tail_log_lines_returns_all_when_lines_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "process.log"
            log_path.write_text("a\nb\nc\n", encoding="utf-8")
            self.assertEqual(tail_log_lines(log_path, 0), ["a\n", "b\n", "c\n"])

    def test_tail_log_lines_empty_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(tail_log_lines(Path(tmp_dir) / "missing.log", 50), [])

    def test_module_log_path_points_under_spark_log_dir(self) -> None:
        path = module_log_path("spark-telegram-bot")
        self.assertEqual(path.name, "process.log")
        self.assertEqual(path.parent.name, "spark-telegram-bot")

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
