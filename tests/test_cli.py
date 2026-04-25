from __future__ import annotations

import os
import json
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from spark_cli.cli import (
    build_module_repair_hints,
    build_parser,
    build_status_repair_hints,
    build_module_envs,
    command_with_managed_python,
    collect_secret_requirements,
    collect_secret_values,
    collect_telegram_fix_payload,
    collect_verify_payload,
    cmd_setup,
    CONFIG_PATH,
    detect_runtime_binary,
    evaluate_module_health,
    clone_module_source,
    clone_target_for_module,
    ensure_generated_setup_secrets,
    ensure_bundle_modules_available,
    delete_secret,
    fetch_secret,
    infer_module_name_from_url,
    git_command,
    is_git_source,
    module_is_git_managed,
    normalize_git_url,
    pull_module_source,
    remove_tree,
    install_module_record,
    keychain_env_for_module,
    list_stored_secrets,
    load_json,
    long_path_aware,
    module_log_path,
    module_secret_env_bindings,
    check_runtime_version_for_module,
    clear_install_progress,
    coerce_config_value,
    dotted_get,
    dotted_set,
    dotted_unset,
    render_init_spark_toml,
    scaffold_module_files,
    validate_init_module_name,
    describe_install_risk,
    enforce_runtime_versions,
    ensure_trust_for_install,
    INSTALL_PROGRESS_PATH,
    is_blessed_registry_entry,
    load_install_progress,
    record_install_failure,
    record_install_step,
    run_install_commands_with_progress,
    step_previously_completed,
    manifest_schema_version,
    needs_capabilities,
    parse_version_constraint,
    parse_version_tuple,
    provider_status_payload,
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
    format_start_warning,
    ready_timeout_seconds,
    read_generated_env,
    required_runtimes_for_modules,
    resolve_runtime_binary,
    run_llm_provider_wizard,
    run_setup_wizard,
    shell_command_env,
    setup_is_interactive,
    start_module,
    stop_module,
    wait_for_ready_check,
    resolve_bundle_names,
    resolve_install_target,
    resolve_start_modules,
    resolve_stop_module_names,
    render_launch_agent_plist,
    render_systemd_autostart_unit,
    autostart_shell_command,
    linux_autostart_path,
    systemctl_command,
    spark_invocation_args,
    summarize_command_output,
    update_setup_state_after_uninstall,
    update_env_file,
    windows_startup_script_path,
    write_windows_startup_script,
    write_runtime_shim,
)


def make_module(name: str, capabilities: list[str], secrets: list[str] | None = None) -> Module:
    secret_definitions = {}
    for secret_id in secrets or []:
        toml_key = secret_id.replace(".", "_")
        secret_definitions[toml_key] = {
            "env_var": secret_id.upper().replace(".", "_"),
            "storage": "keychain",
            "required": False,
        }
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
            "needs": {
                "secrets": secrets or [],
            },
            "secrets": secret_definitions,
        },
    )


class SparkCliTests(unittest.TestCase):
    def test_validate_init_module_name_rejects_bad_names(self) -> None:
        validate_init_module_name("my-module")
        validate_init_module_name("m1")
        for bad in ("My-Module", "1starts-with-digit", "has_underscore", "-leading-dash", ""):
            with self.assertRaises(SystemExit):
                validate_init_module_name(bad)

    def test_render_init_spark_toml_produces_parseable_manifest(self) -> None:
        import tomllib as _toml
        rendered = render_init_spark_toml("my-module", "python", "Demo module")
        parsed = _toml.loads(rendered)
        self.assertEqual(parsed["module"]["name"], "my-module")
        self.assertEqual(parsed["runtime"]["kind"], "python")
        self.assertEqual(parsed["runtime"]["version"], ">=3.11")
        self.assertIn("python -c", parsed["healthcheck"]["command"])

    def test_render_init_spark_toml_node_variant(self) -> None:
        import tomllib as _toml
        parsed = _toml.loads(render_init_spark_toml("my-bot", "node", "Demo bot"))
        self.assertEqual(parsed["runtime"]["kind"], "node")
        self.assertEqual(parsed["runtime"]["version"], ">=22")
        self.assertIn("node -e", parsed["healthcheck"]["command"])

    def test_scaffold_module_files_writes_expected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "new-module"
            created = scaffold_module_files(target, "new-module", "python", "Demo module")
            names = sorted(path.name for path in created)
            self.assertEqual(names, [".gitignore", "README.md", "spark.toml"])
            gitignore = (target / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("__pycache__/", gitignore)
            readme = (target / "README.md").read_text(encoding="utf-8")
            self.assertIn("# new-module", readme)
            # Ensure the scaffold is installable by the CLI's own loader.
            from spark_cli.cli import load_module
            loaded = load_module(target)
            self.assertEqual(loaded.name, "new-module")
            self.assertEqual(loaded.kind, "service")

    def test_dotted_set_and_get_roundtrips_nested_paths(self) -> None:
        config: dict = {}
        dotted_set(config, "dashboard.port", 8765)
        dotted_set(config, "model", "sonnet")
        self.assertEqual(dotted_get(config, "dashboard.port"), 8765)
        self.assertEqual(dotted_get(config, "model"), "sonnet")
        self.assertIsNone(dotted_get(config, "missing.key"))
        self.assertEqual(dotted_get(config, "missing.key", default="fallback"), "fallback")

    def test_dotted_unset_removes_nested_key_and_reports_hit(self) -> None:
        config = {"dashboard": {"port": 8765, "theme": "dark"}}
        self.assertTrue(dotted_unset(config, "dashboard.port"))
        self.assertFalse(dotted_unset(config, "dashboard.port"))
        self.assertEqual(config, {"dashboard": {"theme": "dark"}})

    def test_coerce_config_value_parses_json_primitives_but_keeps_bare_strings(self) -> None:
        self.assertEqual(coerce_config_value("true"), True)
        self.assertEqual(coerce_config_value("42"), 42)
        self.assertEqual(coerce_config_value('"hello"'), "hello")
        self.assertEqual(coerce_config_value("[1,2,3]"), [1, 2, 3])
        self.assertEqual(coerce_config_value("sonnet"), "sonnet")

    def test_load_json_accepts_utf8_bom_from_windows_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "registry.json"
            path.write_text('\ufeff{"ok": true}', encoding="utf-8")
            self.assertEqual(load_json(path, {}), {"ok": True})

    def test_describe_install_risk_lists_commands_and_hooks(self) -> None:
        module = Module(
            name="thirdparty",
            path=Path("C:/tmp/thirdparty"),
            manifest={
                "module": {"name": "thirdparty", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "install": {"dev": {"commands": ["npm ci", "npm run build"]}},
                "hooks": {"post_install": "node scripts/init.js", "pre_uninstall": "node scripts/shutdown.js"},
            },
        )
        lines = describe_install_risk(module)
        combined = "\n".join(lines)
        self.assertIn("$ npm ci", combined)
        self.assertIn("$ npm run build", combined)
        self.assertIn("post_install", combined)
        self.assertIn("pre_uninstall", combined)

    def test_is_blessed_registry_entry_reads_registry(self) -> None:
        # telegram-starter bundle members are all blessed in this repo's registry.json.
        self.assertTrue(is_blessed_registry_entry("spark-telegram-bot"))
        self.assertFalse(is_blessed_registry_entry("definitely-not-registered"))

    def test_ensure_trust_for_install_passes_for_blessed_target(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "install": {"dev": {"commands": ["npm ci"]}},
            },
        )

        class Args:
            trust = False
            non_interactive = False
            skip_install_commands = False

        ensure_trust_for_install(Args(), module, "spark-telegram-bot")

    def test_ensure_trust_for_install_rejects_non_blessed_non_interactive(self) -> None:
        module = Module(
            name="thirdparty",
            path=Path("C:/tmp/thirdparty"),
            manifest={
                "module": {"name": "thirdparty", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "install": {"dev": {"commands": ["node evil.js"]}},
            },
        )

        class Args:
            trust = False
            non_interactive = True
            skip_install_commands = False

        with patch("spark_cli.cli.stdin_is_tty", return_value=False):
            with self.assertRaises(SystemExit) as error:
                ensure_trust_for_install(Args(), module, "thirdparty")
        self.assertIn("non-blessed", str(error.exception))

    def test_ensure_trust_for_install_accepts_trust_flag_non_interactive(self) -> None:
        module = Module(
            name="thirdparty",
            path=Path("C:/tmp/thirdparty"),
            manifest={
                "module": {"name": "thirdparty", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "install": {"dev": {"commands": ["node evil.js"]}},
            },
        )

        class Args:
            trust = True
            non_interactive = True
            skip_install_commands = False

        ensure_trust_for_install(Args(), module, "thirdparty")

    def test_install_progress_roundtrip_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            progress_path = Path(tmp_dir) / "install_progress.json"
            with patch("spark_cli.cli.INSTALL_PROGRESS_PATH", progress_path):
                record_install_step("mod-a", "install_commands")
                self.assertTrue(step_previously_completed("mod-a", "install_commands", resume=True))
                self.assertFalse(step_previously_completed("mod-a", "install_commands", resume=False))
                record_install_failure("mod-a", "install_commands", "npm ci: exit 1")
                progress = load_install_progress("mod-a")
                self.assertEqual(progress["failed_step"], "install_commands")
                self.assertIn("npm ci", progress["last_error"])
                clear_install_progress("mod-a")
                self.assertEqual(load_install_progress("mod-a"), {})
                self.assertFalse(progress_path.exists())

    def test_run_install_commands_with_progress_skips_when_resume_and_completed(self) -> None:
        module = Module(
            name="skip-me",
            path=Path("C:/tmp/skip-me"),
            manifest={
                "module": {"name": "skip-me", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "install": {"dev": {"commands": ["exit 1"]}},
            },
        )

        class Args:
            skip_install_commands = False

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("spark_cli.cli.INSTALL_PROGRESS_PATH", Path(tmp_dir) / "progress.json"):
                record_install_step("skip-me", "install_commands")
                # Would raise if it actually ran `exit 1`; --resume path must skip.
                run_install_commands_with_progress(module, "skip-me", Args(), resume=True)

    def test_run_install_commands_with_progress_records_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module_path = Path(tmp_dir) / "fail-me"
            module_path.mkdir()
            module = Module(
                name="fail-me",
                path=module_path,
                manifest={
                    "module": {"name": "fail-me", "version": "0.1.0", "kind": "service", "plane": "execution"},
                    "install": {"dev": {"commands": ["exit 1"]}},
                },
            )

            class Args:
                skip_install_commands = False

            with patch("spark_cli.cli.INSTALL_PROGRESS_PATH", Path(tmp_dir) / "progress.json"):
                with self.assertRaises(SystemExit):
                    run_install_commands_with_progress(module, "fail-me", Args(), resume=False)
                progress = load_install_progress("fail-me")
                self.assertEqual(progress["failed_step"], "install_commands")
                self.assertNotIn("install_commands", progress.get("steps_completed", []))

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
            "spark-researcher": object(),
            "spark-telegram-bot": object(),
            "spark-intelligence-builder": object(),
            "domain-chip-memory": object(),
            "spawner-ui": object(),
        }
        self.assertEqual(
            expand_targets("telegram-starter", modules, include_all=False),
            [
                "spark-researcher",
                "spark-intelligence-builder",
                "domain-chip-memory",
                "spawner-ui",
                "spark-telegram-bot",
            ],
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

    def test_summarize_command_output_handles_missing_streams(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout=None,
            stderr="module emitted undecodable output",
        )
        self.assertEqual(summarize_command_output(result), "module emitted undecodable output")

    def test_summarize_command_output_compacts_memory_json(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=0,
            stdout=json.dumps({"backend": "local", "document_count": 2, "manifest_present": True}, indent=2),
            stderr="",
        )
        self.assertEqual(
            summarize_command_output(result),
            "memory backend=local | documents=2 | manifest_present=True",
        )

    def test_summarize_command_output_compacts_contract_json(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=0,
            stdout=json.dumps(
                {
                    "normalized_contracts": ["A", "B"],
                    "official_benchmark_adapters": [{"benchmark_name": "One"}],
                    "shadow_benchmark_adapters": [{"benchmark_name": "Two"}],
                },
                indent=2,
            ),
            stderr="",
        )
        self.assertEqual(
            summarize_command_output(result),
            "2 normalized contracts | 1 official adapters | 1 shadow adapters",
        )

    def test_write_runtime_shim_reuses_matching_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            shim_path = Path(tmp_dir) / "python.cmd"
            shim_path.write_text("@python %*\n", encoding="utf-8")
            before = shim_path.stat().st_mtime_ns
            write_runtime_shim(shim_path, "@python %*\n")
            self.assertEqual(shim_path.read_text(encoding="utf-8"), "@python %*\n")
            self.assertEqual(shim_path.stat().st_mtime_ns, before)

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
            [
                "spark-researcher",
                "spark-intelligence-builder",
                "domain-chip-memory",
                "spawner-ui",
                "spark-telegram-bot",
            ],
        )

    def test_setup_defaults_to_telegram_starter_bundle(self) -> None:
        args = build_parser().parse_args(["setup", "--non-interactive"])
        self.assertEqual(args.bundle, "telegram-starter")

    def test_setup_accepts_role_specific_llm_providers(self) -> None:
        args = build_parser().parse_args(
            [
                "setup",
                "--non-interactive",
                "--chat-llm-provider",
                "zai",
                "--builder-llm-provider",
                "openai",
                "--memory-llm-provider",
                "ollama",
                "--mission-llm-provider",
                "anthropic",
            ]
        )
        self.assertEqual(args.chat_llm_provider, "zai")
        self.assertEqual(args.builder_llm_provider, "openai")
        self.assertEqual(args.memory_llm_provider, "ollama")
        self.assertEqual(args.mission_llm_provider, "anthropic")

    def test_autostart_install_defaults_to_telegram_starter_and_now_is_optional(self) -> None:
        args = build_parser().parse_args(["autostart", "install", "--now"])
        self.assertEqual(args.target, "telegram-starter")
        self.assertTrue(args.now)

    def test_restart_accepts_starter_bundle_target(self) -> None:
        args = build_parser().parse_args(["restart", "telegram-starter"])
        self.assertEqual(args.target, "telegram-starter")

    def test_render_systemd_autostart_unit_starts_and_stops_starter_bundle(self) -> None:
        unit = render_systemd_autostart_unit(
            target="telegram-starter",
            start_command="/tmp/spark start telegram-starter",
            stop_command="/tmp/spark stop telegram-starter",
        )
        self.assertIn("Description=Spark Telegram agent", unit)
        self.assertIn("ExecStart=/bin/sh -lc", unit)
        self.assertIn("/tmp/spark start telegram-starter", unit)
        self.assertIn("/tmp/spark stop telegram-starter", unit)
        self.assertIn("WantedBy=default.target", unit)

    def test_linux_autostart_path_uses_system_service_for_root_scope(self) -> None:
        self.assertEqual(
            linux_autostart_path("system"),
            Path("/etc/systemd/system/spark-telegram-agent.service"),
        )
        self.assertIn("--user", systemctl_command("user", "enable", "spark-telegram-agent.service"))
        self.assertNotIn("--user", systemctl_command("system", "enable", "spark-telegram-agent.service"))

    def test_render_launch_agent_plist_runs_at_login(self) -> None:
        plist = render_launch_agent_plist(
            target="telegram-starter",
            start_command="/tmp/spark start telegram-starter",
            stop_command="/tmp/spark stop telegram-starter",
        )
        self.assertIn("<key>RunAtLoad</key>", plist)
        self.assertIn("ai.sparkswarm.spark-telegram-agent", plist)
        self.assertIn("/tmp/spark start telegram-starter", plist)

    def test_autostart_shell_command_uses_current_spark_invocation(self) -> None:
        with patch("spark_cli.cli.spark_invocation_args", return_value=["/tmp/spark"]):
            self.assertEqual(
                autostart_shell_command("start", "telegram-starter"),
                "/tmp/spark start --allow-boot-warnings telegram-starter",
            )

    def test_spark_invocation_args_uses_python_module_when_running_source_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cli_file = tmp_path / "cli.py"
            cli_file.write_text("pass\n", encoding="utf-8")
            with patch("spark_cli.cli.sys.argv", [str(cli_file)]), \
                 patch("spark_cli.cli.shutil.which", return_value=None), \
                 patch("spark_cli.cli.SPARK_HOME", tmp_path / ".spark"), \
                 patch("spark_cli.cli.sys.executable", "/usr/bin/python3"):
                self.assertEqual(spark_invocation_args(), ["/usr/bin/python3", "-m", "spark_cli.cli"])

    def test_spark_invocation_args_prefers_installed_wrapper_for_autostart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            spark_home = Path(tmp_dir) / ".spark"
            wrapper = spark_home / "bin" / ("spark.cmd" if os.name == "nt" else "spark")
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text("", encoding="utf-8")
            with patch("spark_cli.cli.SPARK_HOME", spark_home):
                self.assertEqual(spark_invocation_args(), [str(wrapper.resolve())])

    def test_autostart_install_linux_writes_service_and_enables_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service_path = Path(tmp_dir) / "spark-telegram-agent.service"
            commands: list[list[str]] = []

            def fake_helper(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            args = build_parser().parse_args(["autostart", "install", "--now"])
            with patch("spark_cli.cli.sys.platform", "linux"), \
                 patch("spark_cli.cli.linux_autostart_scope", return_value="user"), \
                 patch("spark_cli.cli.linux_autostart_path", return_value=service_path), \
                 patch("spark_cli.cli.spark_invocation_args", return_value=["/tmp/spark"]), \
                 patch("spark_cli.cli.run_autostart_helper", side_effect=fake_helper), \
                 patch("sys.stdout", new_callable=StringIO):
                self.assertEqual(args.func(args), 0)

            unit = service_path.read_text(encoding="utf-8")
            self.assertIn("/tmp/spark start --allow-boot-warnings telegram-starter", unit)
            self.assertIn("/tmp/spark stop telegram-starter", unit)
            self.assertIn(["systemctl", "--user", "daemon-reload"], commands)
            self.assertIn(["systemctl", "--user", "enable", service_path.name], commands)
            self.assertIn(["systemctl", "--user", "restart", service_path.name], commands)

    def test_autostart_install_macos_replaces_existing_launch_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            plist_path = Path(tmp_dir) / "ai.sparkswarm.spark-telegram-agent.plist"
            commands: list[list[str]] = []

            def fake_helper(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            args = build_parser().parse_args(["autostart", "install", "--now"])
            with patch("spark_cli.cli.sys.platform", "darwin"), \
                 patch("spark_cli.cli.macos_autostart_path", return_value=plist_path), \
                 patch("spark_cli.cli.spark_invocation_args", return_value=["/tmp/spark"]), \
                 patch("spark_cli.cli.os.getuid", return_value=501, create=True), \
                 patch("spark_cli.cli.run_autostart_helper", side_effect=fake_helper), \
                 patch("sys.stdout", new_callable=StringIO):
                self.assertEqual(args.func(args), 0)

            self.assertTrue(plist_path.exists())
            self.assertIn(["launchctl", "bootout", "gui/501", str(plist_path)], commands)
            self.assertIn(["launchctl", "bootstrap", "gui/501", str(plist_path)], commands)
            self.assertIn(["launchctl", "kickstart", "-k", "gui/501/ai.sparkswarm.spark-telegram-agent"], commands)

    def test_write_windows_startup_script_writes_user_login_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            startup_script = Path(tmp_dir) / "spark-telegram-agent.cmd"
            with patch("spark_cli.cli.SPARK_HOME", Path("C:/Users/Example/.spark")):
                write_windows_startup_script(startup_script, r'"C:\Users\Example\.spark\bin\spark.cmd" start telegram-starter')
            content = startup_script.read_text(encoding="ascii")
            self.assertIn('@echo off', content)
            self.assertRegex(content, r'set "SPARK_HOME=C:[/\\]Users[/\\]Example[/\\]\.spark"')
            self.assertIn(r'"C:\Users\Example\.spark\bin\spark.cmd" start telegram-starter', content)

    def test_autostart_install_windows_falls_back_to_startup_folder_when_task_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            startup_script = Path(tmp_dir) / "spark-telegram-agent.cmd"
            commands: list[list[str]] = []

            def fake_helper(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[:2] == ["schtasks", "/Create"]:
                    return subprocess.CompletedProcess(command, 1, "", "ERROR: Access is denied.")
                return subprocess.CompletedProcess(command, 0, "", "")

            args = build_parser().parse_args(["autostart", "install", "--now"])
            with patch("spark_cli.cli.sys.platform", "win32"), \
                 patch("spark_cli.cli.windows_startup_script_path", return_value=startup_script), \
                 patch("spark_cli.cli.spark_invocation_args", return_value=[r"C:\Users\Example\.spark\bin\spark.cmd"]), \
                 patch("spark_cli.cli.run_autostart_helper", side_effect=fake_helper), \
                 patch("sys.stdout", new_callable=StringIO):
                self.assertEqual(args.func(args), 0)

            self.assertTrue(startup_script.exists())
            self.assertEqual(commands[0][:7], ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", "Spark Telegram Agent", "/TR"])
            self.assertIn("start --allow-boot-warnings telegram-starter", commands[0][7])
            self.assertEqual(commands[0][8], "/F")
            self.assertIn([r"C:\Users\Example\.spark\bin\spark.cmd", "start", "--allow-boot-warnings", "telegram-starter"], commands)

    def test_windows_startup_script_path_uses_appdata(self) -> None:
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\Example\AppData\Roaming"}):
            path_text = str(windows_startup_script_path())
            self.assertIn("Microsoft", path_text)
            self.assertIn("Startup", path_text)
            self.assertTrue(path_text.endswith("spark-telegram-agent.cmd"))

    def test_guide_prints_normie_onboarding_surface(self) -> None:
        args = build_parser().parse_args(["guide"])
        with patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(args.func(args), 0)
        output = stdout.getvalue()
        self.assertIn("@BotFather", output)
        self.assertIn("Windows PowerShell/CMD", output)
        self.assertIn("WSL Ubuntu shell", output)
        self.assertIn("Pick LLM providers", output)
        self.assertIn("chat: Telegram chat replies", output)
        self.assertIn("spark setup --llm-provider openai", output)
        self.assertIn("--chat-llm-provider openai", output)
        self.assertIn("signed-in Codex CLI", output)
        self.assertIn("spark autostart install --now", output)
        self.assertIn("spark start telegram-starter", output)
        self.assertIn("/diagnose", output)
        self.assertIn("/run <goal>", output)
        self.assertIn("spark secrets list", output)

    def test_guide_json_is_agent_readable(self) -> None:
        args = build_parser().parse_args(["guide", "--json"])
        with patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(args.func(args), 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["title"], "Spark starter guide")
        self.assertIn("starter_bundle", payload)
        self.assertIn("telegram_commands", payload)
        self.assertIn("Windows PowerShell/CMD", payload["operating_systems"])
        self.assertEqual(
            [item["role"] for item in payload["setup"]["llm_roles"]],
            ["chat", "builder", "memory", "mission"],
        )

    def test_setup_default_bundle_registers_five_module_starter_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            fixture_root = tmp / "fixtures"
            fixture_root.mkdir()

            manifests = {
                "spark-researcher": {
                    "kind": "runtime",
                    "plane": "research",
                    "capabilities": ["spark.researcher", "spark.advisory", "spark.research.memory"],
                    "needs_capabilities": [],
                    "needs_secrets": [],
                },
                "spark-intelligence-builder": {
                    "kind": "runtime",
                    "plane": "runtime",
                    "capabilities": ["spark.runtime"],
                    "needs_capabilities": [],
                    "needs_secrets": [],
                },
                "domain-chip-memory": {
                    "kind": "chip-pack",
                    "plane": "runtime",
                    "capabilities": ["spark.memory.default"],
                    "needs_capabilities": [],
                    "needs_secrets": [],
                },
                "spawner-ui": {
                    "kind": "app",
                    "plane": "execution",
                    "capabilities": ["mission.execution"],
                    "needs_capabilities": [],
                    "needs_secrets": [],
                },
                "spark-telegram-bot": {
                    "kind": "service",
                    "plane": "ingress",
                    "capabilities": ["telegram.ingress"],
                    "needs_capabilities": ["spark.runtime"],
                    "needs_secrets": ["telegram.bot_token", "telegram.admin_ids", "telegram.relay_secret", "llm.zai.api_key"],
                },
            }
            registry = {"modules": {}, "bundles": {"telegram-starter": {"modules": list(manifests)}}}
            for name, manifest in manifests.items():
                module_path = fixture_root / name
                module_path.mkdir()
                registry["modules"][name] = {"source": str(module_path), "blessed": True}
                module_path.joinpath("spark.toml").write_text(
                    "\n".join(
                        [
                            "[module]",
                            f'name = "{name}"',
                            'version = "0.1.0"',
                            f'kind = "{manifest["kind"]}"',
                            f'plane = "{manifest["plane"]}"',
                            "",
                            "[provides]",
                            "capabilities = [" + ", ".join(f'"{item}"' for item in manifest["capabilities"]) + "]",
                            "",
                            "[needs]",
                            "capabilities = [" + ", ".join(f'"{item}"' for item in manifest["needs_capabilities"]) + "]",
                            "secrets = [" + ", ".join(f'"{item}"' for item in manifest["needs_secrets"]) + "]",
                            "",
                            "[secrets.llm_zai_api_key]",
                            'prompt = "Z.AI API key"',
                            "required = false",
                            'storage = "keychain"',
                            'env_var = "ZAI_API_KEY"',
                            "",
                            "[secrets.telegram_bot_token]",
                            'prompt = "Telegram bot token from @BotFather"',
                            "required = true",
                            'storage = "keychain"',
                            'env_var = "BOT_TOKEN"',
                            "",
                            "[secrets.telegram_admin_ids]",
                            'prompt = "Comma-separated Telegram admin IDs"',
                            "required = true",
                            'storage = "file"',
                            'env_var = "ADMIN_TELEGRAM_IDS"',
                            "",
                            "[secrets.telegram_relay_secret]",
                            'prompt = "Local Spawner-to-Telegram relay secret"',
                            "required = false",
                            'storage = "keychain"',
                            'env_var = "TELEGRAM_RELAY_SECRET"',
                        ]
                    ),
                    encoding="utf-8",
                )

            spark_home = tmp / "spark-home"
            state_dir = spark_home / "state"
            config_dir = spark_home / "config"
            module_config_dir = config_dir / "modules"
            patches = {
                "SPARK_HOME": spark_home,
                "STATE_DIR": state_dir,
                "CONFIG_DIR": config_dir,
                "MODULE_CONFIG_DIR": module_config_dir,
                "LOG_DIR": spark_home / "logs",
                "REGISTRY_PATH": state_dir / "installed.json",
                "CONFIG_PATH": state_dir / "setup.json",
                "PID_PATH": state_dir / "pids.json",
                "INSTALL_PROGRESS_PATH": state_dir / "install_progress.json",
                "USER_CONFIG_PATH": config_dir / "config.json",
                "SECRETS_INDEX_PATH": config_dir / "secrets_index.json",
                "SECRETS_FILE_PATH": config_dir / "secrets.local.json",
            }
            args = build_parser().parse_args(
                [
                    "setup",
                    "--non-interactive",
                    "--skip-install-commands",
                    "--skip-runtime-check",
                    "--secret",
                    "telegram.bot_token=123456:test-token",
                    "--secret",
                    "telegram.admin_ids=111,222",
                    "--llm-provider",
                    "zai",
                    "--zai-api-key",
                    "zai-test-key",
                ]
            )

            with patch.multiple("spark_cli.cli", **patches), \
                 patch("spark_cli.cli.load_registry_definition", return_value=registry), \
                 patch("spark_cli.cli.keychain_available", return_value=False), \
                 patch("sys.stdout", new_callable=StringIO) as stdout:
                self.assertEqual(cmd_setup(args), 0)
            setup_output = stdout.getvalue()
            self.assertIn("Next steps:", setup_output)
            self.assertIn("spark status", setup_output)
            self.assertIn("spark autostart install --now", setup_output)
            self.assertIn("spark start telegram-starter", setup_output)
            self.assertIn("/diagnose", setup_output)
            self.assertIn("Need a bot token? Open @BotFather", setup_output)
            self.assertIn("LLM roles:", setup_output)
            self.assertIn("chat: zai", setup_output)
            self.assertIn("Builder runtime: prepared Builder home", setup_output)

            expected = [
                "spark-researcher",
                "spark-intelligence-builder",
                "domain-chip-memory",
                "spawner-ui",
                "spark-telegram-bot",
            ]
            installed = load_json(state_dir / "installed.json", {})
            self.assertEqual(list(installed), expected)
            for name in expected:
                self.assertEqual(
                    installed[name]["installed_via"],
                    {"kind": "bundle", "target": "telegram-starter", "bundle": "telegram-starter"},
                )
                self.assertEqual(installed[name]["bundle_provenance"], ["telegram-starter"])

            setup_state = load_json(state_dir / "setup.json", {})
            self.assertEqual(setup_state["bundle"], "telegram-starter")
            self.assertEqual(setup_state["modules"], expected)
            self.assertEqual(setup_state["telegram_ingress_owner"], "spark-telegram-bot")
            self.assertIn("telegram.relay_secret", setup_state["secret_keys"])
            self.assertEqual(setup_state["llm"]["provider"], "zai")
            self.assertEqual(setup_state["llm"]["model"], "glm-5.1")
            self.assertTrue(setup_state["llm"]["api_key_configured"])
            self.assertEqual(setup_state["llm"]["auth_mode"], "api_key")
            self.assertEqual(
                {role: state["provider"] for role, state in setup_state["llm"]["roles"].items()},
                {"chat": "zai", "builder": "zai", "memory": "zai", "mission": "zai"},
            )
            expected_builder_home = state_dir / "spark-intelligence"
            self.assertEqual(setup_state["builder_home"], str(expected_builder_home))
            self.assertTrue(expected_builder_home.exists())

            gateway_env = (module_config_dir / "spark-telegram-bot.env").read_text(encoding="utf-8")
            spawner_env = (module_config_dir / "spawner-ui.env").read_text(encoding="utf-8")
            builder_env = (module_config_dir / "spark-intelligence-builder.env").read_text(encoding="utf-8")
            self.assertNotIn("BOT_TOKEN=123456:test-token", gateway_env)
            self.assertIn("ADMIN_TELEGRAM_IDS=111,222", gateway_env)
            self.assertIn(f"SPARK_BUILDER_HOME={expected_builder_home}", gateway_env)
            self.assertIn(f"SPARK_BUILDER_PYTHON={Path(sys.executable)}", gateway_env)
            self.assertIn("SPARK_BUILDER_BRIDGE_MODE=required", gateway_env)
            self.assertIn("SPAWNER_UI_URL=http://127.0.0.1:5173", gateway_env)
            self.assertIn("LLM_PROVIDER=zai", gateway_env)
            self.assertNotIn("ZAI_API_KEY=zai-test-key", gateway_env)
            self.assertIn("ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4/", gateway_env)
            self.assertIn("ZAI_MODEL=glm-5.1", gateway_env)
            self.assertIn("SPARK_CHAT_LLM_PROVIDER=zai", gateway_env)
            self.assertIn("SPARK_BUILDER_LLM_PROVIDER=zai", gateway_env)
            self.assertIn("SPARK_MEMORY_LLM_PROVIDER=zai", gateway_env)
            self.assertIn("SPARK_MISSION_LLM_PROVIDER=zai", gateway_env)
            self.assertNotIn("BOT_TOKEN=", spawner_env)
            self.assertIn("SPARK_LLM_PROVIDER=zai", spawner_env)
            self.assertIn("SPARK_CHAT_LLM_PROVIDER=zai", spawner_env)
            self.assertNotIn("SPARK_SPARK_LLM_PROVIDER", spawner_env)
            self.assertNotIn("SPARK_ZAI_API_KEY", spawner_env)
            self.assertIn("MISSION_CONTROL_WEBHOOK_URLS=http://127.0.0.1:8788/spawner-events", spawner_env)
            self.assertIn("TELEGRAM_RELAY_SECRET=", spawner_env)
            self.assertNotIn("TELEGRAM_RELAY_SECRET=", gateway_env)
            self.assertIn(f"SPARK_INTELLIGENCE_HOME={expected_builder_home}", builder_env)
            self.assertIn(f"SPARK_RESEARCHER_ROOT={fixture_root / 'spark-researcher'}", builder_env)
            self.assertIn(f"SPARK_DOMAIN_CHIP_MEMORY_ROOT={fixture_root / 'domain-chip-memory'}", builder_env)
            secrets_index = load_json(config_dir / "secrets_index.json", {})
            secrets_file = load_json(config_dir / "secrets.local.json", {})
            self.assertEqual(secrets_index["telegram.relay_secret"], "file")
            self.assertIn("telegram.relay_secret", secrets_file)

    def test_ensure_generated_setup_secrets_adds_relay_secret_for_gateway(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"], secrets=["telegram.relay_secret"])
        values = ensure_generated_setup_secrets({}, [gateway])
        self.assertRegex(values["telegram.relay_secret"], r"^[A-Za-z0-9_-]{24,256}$")

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
            telegram_relay_secret = None

        values = collect_secret_values(Args(), [module])
        self.assertEqual(values["telegram.bot_token"], "abc")

    def test_generated_module_env_path_uses_canonical_module_config_dir(self) -> None:
        module = make_module("spawner-ui", ["mission.execution"])
        self.assertEqual(generated_module_env_path(module), MODULE_CONFIG_DIR / "spawner-ui.env")

    def test_build_module_envs_routes_telegram_secret_only_to_gateway(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])
        researcher = make_module("spark-researcher", ["spark.researcher"])
        memory = make_module("domain-chip-memory", ["spark.memory.substrate"])

        class Args:
            spawner_ui_url = "http://127.0.0.1:5173"
            telegram_relay_secret = None

        envs = build_module_envs(
            Args(),
            {
                gateway.name: gateway,
                builder.name: builder,
                spawner.name: spawner,
                researcher.name: researcher,
                memory.name: memory,
            },
            {
                "telegram.bot_token": "abc",
                "telegram.admin_ids": "123",
                "telegram.relay_secret": "relay_secret_abcdefghijklmnopqrstuvwxyz",
            },
        )
        self.assertEqual(envs["spark-telegram-bot"]["BOT_TOKEN"], "abc")
        self.assertNotIn("BOT_TOKEN", envs["spawner-ui"])
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_BUILDER_HOME"], str(REGISTRY_PATH.parent / "spark-intelligence"))
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_BUILDER_PYTHON"], str(Path(sys.executable)))
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_BUILDER_BRIDGE_MODE"], "required")
        self.assertEqual(envs["spark-intelligence-builder"]["SPARK_INTELLIGENCE_HOME"], str(REGISTRY_PATH.parent / "spark-intelligence"))
        self.assertEqual(envs["spark-intelligence-builder"]["SPARK_RESEARCHER_ROOT"], str(researcher.path))
        self.assertEqual(envs["spark-intelligence-builder"]["SPARK_DOMAIN_CHIP_MEMORY_ROOT"], str(memory.path))
        self.assertEqual(
            envs["spark-telegram-bot"]["TELEGRAM_RELAY_SECRET"],
            envs["spawner-ui"]["TELEGRAM_RELAY_SECRET"],
        )
        self.assertNotIn("TELEGRAM_WEBHOOK_SECRET", envs["spark-telegram-bot"])

    def test_build_module_envs_defaults_missing_spawner_ui_url(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])

        class Args:
            spawner_ui_url = None
            telegram_relay_secret = None

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
            },
        )
        self.assertEqual(envs["spark-telegram-bot"]["SPAWNER_UI_URL"], "http://127.0.0.1:5173")
        self.assertEqual(envs["spark-telegram-bot"]["TELEGRAM_GATEWAY_MODE"], "polling")
        self.assertEqual(envs["spawner-ui"]["MISSION_CONTROL_WEBHOOK_URLS"], "http://127.0.0.1:8788/spawner-events")
        self.assertIn("TELEGRAM_RELAY_SECRET", envs["spark-telegram-bot"])
        self.assertEqual(envs["spark-telegram-bot"]["TELEGRAM_RELAY_SECRET"], envs["spawner-ui"]["TELEGRAM_RELAY_SECRET"])
        self.assertEqual(envs["spark-telegram-bot"]["LLM_PROVIDER"], "not_configured")
        self.assertEqual(envs["spark-telegram-bot"]["BOT_DEFAULT_PROVIDER"], "none")
        self.assertNotIn("OLLAMA_URL", envs["spark-telegram-bot"])
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_CHAT_LLM_PROVIDER"], "not_configured")
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_BUILDER_LLM_PROVIDER"], "not_configured")
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_MEMORY_LLM_PROVIDER"], "not_configured")
        self.assertEqual(envs["spark-telegram-bot"]["SPARK_MISSION_LLM_PROVIDER"], "not_configured")
        self.assertEqual(envs["spark-intelligence-builder"]["SPARK_LLM_PROVIDER"], "not_configured")
        self.assertNotIn("SPARK_SPARK_LLM_PROVIDER", envs["spark-intelligence-builder"])

    def test_build_module_envs_wires_zai_gateway_configuration(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])

        class Args:
            spawner_ui_url = "http://127.0.0.1:5173"
            telegram_relay_secret = None
            llm_provider = "zai"
            zai_base_url = "https://api.z.ai/api/coding/paas/v4/"
            zai_model = "glm-5.1"

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
                "llm.zai.api_key": "zai-key",
            },
        )

        gateway_env = envs["spark-telegram-bot"]
        self.assertEqual(gateway_env["LLM_PROVIDER"], "zai")
        self.assertEqual(gateway_env["BOT_DEFAULT_PROVIDER"], "zai")
        self.assertEqual(gateway_env["ZAI_API_KEY"], "zai-key")
        self.assertEqual(gateway_env["ZAI_MODEL"], "glm-5.1")
        self.assertEqual(gateway_env["SPARK_CHAT_LLM_PROVIDER"], "zai")
        self.assertEqual(gateway_env["SPARK_CHAT_LLM_AUTH_MODE"], "api_key")
        self.assertEqual(envs["spawner-ui"]["SPARK_ZAI_MODEL"], "glm-5.1")
        self.assertEqual(envs["spawner-ui"]["SPARK_CHAT_LLM_PROVIDER"], "zai")
        self.assertNotIn("SPARK_ZAI_API_KEY", envs["spawner-ui"])
        self.assertNotIn("SPARK_ZAI_API_KEY", envs["spark-intelligence-builder"])

    def test_build_module_envs_supports_role_specific_llm_providers(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])

        class Args:
            spawner_ui_url = "http://127.0.0.1:5173"
            telegram_relay_secret = None
            llm_provider = None
            chat_llm_provider = "zai"
            builder_llm_provider = "openai"
            memory_llm_provider = "ollama"
            mission_llm_provider = "openai"
            zai_base_url = "https://api.z.ai/api/coding/paas/v4/"
            zai_model = "glm-5.1"
            openai_base_url = "https://api.openai.com/v1"
            openai_model = "gpt-5.5"
            ollama_url = "http://localhost:11434"
            ollama_model = "llama3.1"

        with patch("spark_cli.cli.detect_codex_cli", return_value={"present": True, "path": "/usr/local/bin/codex"}):
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
                    "llm.zai.api_key": "zai-key",
                },
            )

        gateway_env = envs["spark-telegram-bot"]
        self.assertEqual(gateway_env["LLM_PROVIDER"], "zai")
        self.assertEqual(gateway_env["BOT_DEFAULT_PROVIDER"], "zai")
        self.assertEqual(gateway_env["SPARK_CHAT_LLM_PROVIDER"], "zai")
        self.assertEqual(gateway_env["SPARK_CHAT_LLM_AUTH_MODE"], "api_key")
        self.assertEqual(gateway_env["SPARK_BUILDER_LLM_PROVIDER"], "openai")
        self.assertEqual(gateway_env["SPARK_BUILDER_LLM_MODEL"], "gpt-5.5")
        self.assertEqual(gateway_env["SPARK_BUILDER_LLM_AUTH_MODE"], "codex_oauth")
        self.assertEqual(gateway_env["SPARK_MEMORY_LLM_PROVIDER"], "ollama")
        self.assertEqual(gateway_env["SPARK_MEMORY_LLM_AUTH_MODE"], "local")
        self.assertEqual(gateway_env["SPARK_MISSION_LLM_PROVIDER"], "openai")
        self.assertEqual(envs["spawner-ui"]["SPARK_BUILDER_LLM_PROVIDER"], "openai")
        self.assertEqual(envs["spark-intelligence-builder"]["SPARK_MEMORY_LLM_PROVIDER"], "ollama")
        self.assertEqual(envs["spawner-ui"]["DEFAULT_MISSION_PROVIDER"], "codex")
        self.assertEqual(envs["spawner-ui"]["SPAWNER_PRD_AUTO_PROVIDER"], "codex")
        self.assertEqual(envs["spawner-ui"]["CODEX_PATH"], "/usr/local/bin/codex")
        self.assertNotIn("SPARK_ZAI_API_KEY", envs["spawner-ui"])
        self.assertNotIn("SPARK_OPENAI_API_KEY", envs["spawner-ui"])
        self.assertNotIn("SPARK_SPARK_LLM_PROVIDER", envs["spawner-ui"])

    def test_build_module_envs_wires_codex_as_local_execution_provider(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])

        class Args:
            spawner_ui_url = "http://127.0.0.1:5173"
            telegram_relay_secret = None
            llm_provider = "codex"
            chat_llm_provider = None
            builder_llm_provider = None
            memory_llm_provider = None
            mission_llm_provider = None
            codex_model = "gpt-5.5"

        with patch("spark_cli.cli.detect_codex_cli", return_value={"present": True, "path": "/usr/local/bin/codex"}):
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
                },
            )

        gateway_env = envs["spark-telegram-bot"]
        spawner_env = envs["spawner-ui"]
        self.assertEqual(gateway_env["LLM_PROVIDER"], "codex")
        self.assertEqual(gateway_env["SPARK_LLM_PROVIDER"], "codex")
        self.assertEqual(gateway_env["BOT_DEFAULT_PROVIDER"], "codex")
        self.assertEqual(gateway_env["CODEX_MODEL"], "gpt-5.5")
        self.assertEqual(gateway_env["CODEX_PATH"], "/usr/local/bin/codex")
        self.assertEqual(gateway_env["SPARK_CHAT_LLM_AUTH_MODE"], "codex_oauth")
        self.assertEqual(spawner_env["DEFAULT_MISSION_PROVIDER"], "codex")
        self.assertEqual(spawner_env["SPAWNER_PRD_AUTO_PROVIDER"], "codex")
        self.assertEqual(spawner_env["SPARK_CODEX_MODEL"], "gpt-5.5")
        self.assertEqual(spawner_env["CODEX_PATH"], "/usr/local/bin/codex")
        self.assertEqual(envs["spark-intelligence-builder"]["SPARK_LLM_PROVIDER"], "codex")

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

    def test_wait_for_ready_check_describes_http_timeout(self) -> None:
        module = Module(
            name="http-target",
            path=Path("C:/tmp/http-target"),
            manifest={
                "module": {"name": "http-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "run": {"default": {"ready_check": "http://127.0.0.1:5173/api/providers"}},
                "healthcheck": {"timeout_seconds": 1},
            },
        )

        with patch("spark_cli.cli.urllib.request.urlopen", side_effect=urllib.error.URLError(ConnectionRefusedError())), \
             patch("spark_cli.cli.time.time", side_effect=[100.0, 100.5, 101.5]), \
             patch("spark_cli.cli.time.sleep", return_value=None):
            ready, detail = wait_for_ready_check(module)

        self.assertFalse(ready)
        self.assertIn("http://127.0.0.1:5173/api/providers did not become ready within 1s", detail)
        self.assertIn("last error:", detail)

    def test_wait_for_ready_check_retries_transient_http_reset(self) -> None:
        module = Module(
            name="http-target",
            path=Path("C:/tmp/http-target"),
            manifest={
                "module": {"name": "http-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "run": {"default": {"ready_check": "http://127.0.0.1:5173/api/providers"}},
                "healthcheck": {"timeout_seconds": 3},
            },
        )

        class ReadyResponse:
            status = 200

            def __enter__(self) -> "ReadyResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        with patch("spark_cli.cli.urllib.request.urlopen", side_effect=[ConnectionResetError("reset"), ReadyResponse()]), \
             patch("spark_cli.cli.time.time", side_effect=[100.0, 100.5, 101.5]), \
             patch("spark_cli.cli.time.sleep", return_value=None):
            ready, detail = wait_for_ready_check(module)

        self.assertTrue(ready)
        self.assertEqual(detail, "http://127.0.0.1:5173/api/providers")

    def test_wait_for_ready_check_stops_when_http_process_exits(self) -> None:
        module = Module(
            name="http-target",
            path=Path("C:/tmp/http-target"),
            manifest={
                "module": {"name": "http-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "run": {"default": {"ready_check": "http://127.0.0.1:5173/api/providers"}},
                "healthcheck": {"timeout_seconds": 60},
            },
        )

        class ExitedProcess:
            def poll(self) -> int:
                return 127

        with patch("spark_cli.cli.urllib.request.urlopen") as urlopen:
            ready, detail = wait_for_ready_check(module, process=ExitedProcess())  # type: ignore[arg-type]

        self.assertFalse(ready)
        self.assertEqual(detail, "process exited with code 127")
        urlopen.assert_not_called()

    def test_wait_for_ready_check_includes_shell_ready_detail_when_process_exits(self) -> None:
        module = Module(
            name="telegram-target",
            path=Path("C:/tmp/telegram-target"),
            manifest={
                "module": {"name": "telegram-target", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                "run": {"default": {"ready_check": "npm run health:polling"}},
                "healthcheck": {"timeout_seconds": 20},
            },
        )

        class ExitedProcess:
            def poll(self) -> int:
                return 1

        completed = subprocess.CompletedProcess(
            "npm run health:polling",
            1,
            stdout="",
            stderr="Telegram health: FAILED - Telegram rejected BOT_TOKEN.",
        )

        with patch("spark_cli.cli.module_runtime_env", return_value={}), \
             patch("spark_cli.cli.run_shell", return_value=completed) as run:
            ready, detail = wait_for_ready_check(module, process=ExitedProcess())  # type: ignore[arg-type]

        self.assertFalse(ready)
        self.assertIn("Telegram rejected BOT_TOKEN", detail)
        self.assertIn("Process exited with code 1", detail)
        run.assert_called_once_with("npm run health:polling", module.path, env={}, timeout=20)

    def test_wait_for_ready_check_accepts_running_process(self) -> None:
        module = Module(
            name="polling-target",
            path=Path("C:/tmp/polling-target"),
            manifest={
                "module": {"name": "polling-target", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                "run": {"default": {"ready_check": "process"}},
                "healthcheck": {"timeout_seconds": 2},
            },
        )

        class RunningProcess:
            def poll(self) -> None:
                return None

        with patch("spark_cli.cli.time.time", side_effect=[100.0, 100.1, 102.1]), \
             patch("spark_cli.cli.time.sleep", return_value=None):
            ready, detail = wait_for_ready_check(module, process=RunningProcess())  # type: ignore[arg-type]

        self.assertTrue(ready)
        self.assertEqual(detail, "process is running")

    def test_wait_for_ready_check_rejects_exited_process(self) -> None:
        module = Module(
            name="polling-target",
            path=Path("C:/tmp/polling-target"),
            manifest={
                "module": {"name": "polling-target", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                "run": {"default": {"ready_check": "process"}},
                "healthcheck": {"timeout_seconds": 2},
            },
        )

        class ExitedProcess:
            def poll(self) -> int:
                return 1

        ready, detail = wait_for_ready_check(module, process=ExitedProcess())  # type: ignore[arg-type]

        self.assertFalse(ready)
        self.assertEqual(detail, "process exited with code 1")

    def test_wait_for_ready_check_rejects_process_that_exits_after_initial_poll(self) -> None:
        module = Module(
            name="polling-target",
            path=Path("C:/tmp/polling-target"),
            manifest={
                "module": {"name": "polling-target", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                "run": {"default": {"ready_check": "process"}},
                "healthcheck": {"timeout_seconds": 10},
            },
        )

        class EventuallyExitedProcess:
            def __init__(self) -> None:
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                if self.polls >= 3:
                    return 1
                return None

        with patch("spark_cli.cli.time.time", side_effect=[100.0, 100.1, 101.0, 102.0]), \
             patch("spark_cli.cli.time.sleep", return_value=None):
            ready, detail = wait_for_ready_check(module, process=EventuallyExitedProcess())  # type: ignore[arg-type]

        self.assertFalse(ready)
        self.assertEqual(detail, "process exited with code 1")

    def test_evaluate_module_health_passes_configured_timeout(self) -> None:
        module = Module(
            name="health-target",
            path=Path("C:/tmp/health-target"),
            manifest={
                "module": {"name": "health-target", "version": "0.1.0", "kind": "service", "plane": "execution"},
                "healthcheck": {"command": "npm run health", "timeout_seconds": 7},
            },
        )

        completed = subprocess.CompletedProcess("npm run health", 124, stdout="", stderr="command timed out after 7s")
        with patch("spark_cli.cli.module_runtime_env", return_value={}), \
             patch("spark_cli.cli.run_shell", return_value=completed) as run:
            result = evaluate_module_health(module)

        self.assertFalse(result["healthy"])
        self.assertEqual(result["detail"], "command timed out after 7s")
        run.assert_called_once_with("npm run health", module.path, env={}, timeout=7)

    def test_format_start_warning_mentions_running_process_and_logs(self) -> None:
        module = Module(
            name="spawner-ui",
            path=Path("C:/tmp/spawner-ui"),
            manifest={"module": {"name": "spawner-ui", "version": "0.1.0", "kind": "app", "plane": "execution"}},
        )

        class RunningProcess:
            def poll(self) -> None:
                return None

        warning = format_start_warning(module, "not ready", RunningProcess())  # type: ignore[arg-type]
        self.assertIn("still running and may still be booting", warning)
        self.assertIn("spark logs spawner-ui --lines 80", warning)

    def test_format_start_warning_mentions_exited_process_and_logs(self) -> None:
        module = Module(
            name="spawner-ui",
            path=Path("C:/tmp/spawner-ui"),
            manifest={"module": {"name": "spawner-ui", "version": "0.1.0", "kind": "app", "plane": "execution"}},
        )

        class ExitedProcess:
            def poll(self) -> int:
                return 1

        warning = format_start_warning(module, "not ready", ExitedProcess())  # type: ignore[arg-type]
        self.assertIn("exited with code 1", warning)
        self.assertIn("spark logs spawner-ui --lines 80", warning)

    def test_format_start_warning_does_not_repeat_embedded_exit_detail(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={"module": {"name": "spark-telegram-bot", "version": "0.1.0", "kind": "service", "plane": "ingress"}},
        )

        class ExitedProcess:
            def poll(self) -> int:
                return 1

        warning = format_start_warning(
            module,
            "Telegram health: FAILED - bad token; process exited with code 1",
            ExitedProcess(),  # type: ignore[arg-type]
        )

        self.assertEqual(warning.count("process exited with code 1"), 1)
        self.assertIn("spark logs spark-telegram-bot --lines 80", warning)

    def test_start_module_allows_boot_warning_when_process_keeps_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = Module(
                name="slow-spawner",
                path=Path(tmp_dir),
                manifest={
                    "module": {"name": "slow-spawner", "version": "0.1.0", "kind": "app", "plane": "execution"},
                    "run": {"default": {"command": "npm run dev", "ready_check": "http://127.0.0.1:5173"}},
                },
            )

            class RunningProcess:
                pid = 12345

                def poll(self) -> None:
                    return None

            with patch("spark_cli.cli.load_pids", return_value={}), \
                 patch("spark_cli.cli.save_pids"), \
                 patch("spark_cli.cli.LOG_DIR", Path(tmp_dir) / "logs"), \
                 patch("spark_cli.cli.module_runtime_env", return_value={}), \
                 patch("spark_cli.cli.os.name", "posix"), \
                 patch("spark_cli.cli.subprocess.Popen", return_value=RunningProcess()) as popen, \
                 patch("spark_cli.cli.wait_for_ready_check", return_value=(False, "not ready yet")), \
                 patch("sys.stdout", new_callable=StringIO):
                self.assertTrue(start_module(module, allow_boot_warnings=True))
            self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_start_module_fails_boot_warning_when_process_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = Module(
                name="failed-spawner",
                path=Path(tmp_dir),
                manifest={
                    "module": {"name": "failed-spawner", "version": "0.1.0", "kind": "app", "plane": "execution"},
                    "run": {"default": {"command": "npm run dev", "ready_check": "http://127.0.0.1:5173"}},
                },
            )

            class ExitedProcess:
                pid = 12346

                def poll(self) -> int:
                    return 1

            with patch("spark_cli.cli.load_pids", return_value={}), \
                 patch("spark_cli.cli.save_pids"), \
                 patch("spark_cli.cli.LOG_DIR", Path(tmp_dir) / "logs"), \
                 patch("spark_cli.cli.module_runtime_env", return_value={}), \
                 patch("spark_cli.cli.os.name", "posix"), \
                 patch("spark_cli.cli.subprocess.Popen", return_value=ExitedProcess()), \
                 patch("spark_cli.cli.wait_for_ready_check", return_value=(False, "not ready yet")), \
                 patch("sys.stdout", new_callable=StringIO):
                self.assertFalse(start_module(module, allow_boot_warnings=True))

    def test_start_module_removes_pid_record_when_process_exits_during_ready_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = Module(
                name="failed-telegram",
                path=Path(tmp_dir),
                manifest={
                    "module": {"name": "failed-telegram", "version": "0.1.0", "kind": "service", "plane": "ingress"},
                    "run": {"default": {"command": "npm run dev", "ready_check": "process"}},
                },
            )

            class ExitedProcess:
                pid = 12347

                def poll(self) -> int:
                    return 1

            saved_payloads: list[dict[str, Any]] = []

            def fake_save(payload: dict[str, Any]) -> None:
                saved_payloads.append(dict(payload))

            with patch("spark_cli.cli.load_pids", side_effect=[{}, {"failed-telegram": {"pid": 12347}}]), \
                 patch("spark_cli.cli.save_pids", side_effect=fake_save), \
                 patch("spark_cli.cli.LOG_DIR", Path(tmp_dir) / "logs"), \
                 patch("spark_cli.cli.module_runtime_env", return_value={}), \
                 patch("spark_cli.cli.os.name", "posix"), \
                 patch("spark_cli.cli.subprocess.Popen", return_value=ExitedProcess()), \
                 patch("spark_cli.cli.wait_for_ready_check", return_value=(False, "process exited with code 1")), \
                 patch("sys.stdout", new_callable=StringIO):
                self.assertFalse(start_module(module))

            self.assertIn("failed-telegram", saved_payloads[0])
            self.assertEqual(saved_payloads[-1], {})

    def test_stop_module_terminates_posix_process_group(self) -> None:
        with patch("spark_cli.cli.os.name", "posix"), \
             patch("spark_cli.cli.os.killpg", create=True) as killpg, \
             patch("spark_cli.cli.subprocess.run") as run, \
             patch("sys.stdout", new_callable=StringIO):
            stop_module("spawner-ui", 12345)

        killpg.assert_called_once_with(12345, signal.SIGTERM)
        run.assert_not_called()

    def test_stop_module_falls_back_to_single_posix_pid(self) -> None:
        with patch("spark_cli.cli.os.name", "posix"), \
             patch("spark_cli.cli.os.killpg", side_effect=ProcessLookupError(), create=True), \
             patch("spark_cli.cli.subprocess.run") as run, \
             patch("sys.stdout", new_callable=StringIO):
            stop_module("spawner-ui", 12345)

        run.assert_called_once_with(["kill", "12345"], check=False, capture_output=True)

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

    def test_detect_runtime_binary_falls_back_to_current_python(self) -> None:
        with patch("spark_cli.cli.shutil.which", return_value=None):
            path = resolve_runtime_binary("python")
        self.assertIsNotNone(path)
        self.assertTrue(Path(str(path)).exists())

    def test_shell_command_env_adds_python_shim_when_python_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir) / "state"
            with patch("spark_cli.cli.STATE_DIR", state_dir):
                with patch.dict(os.environ, {"PATH": ""}, clear=False):
                    env = shell_command_env()
            shim_dir = state_dir / "runtime-shims"
            self.assertEqual(env["PATH"].split(os.pathsep)[0], str(shim_dir))
            shim_name = "python.cmd" if os.name == "nt" else "python"
            self.assertTrue((shim_dir / shim_name).exists())

    def test_shell_command_env_prefers_managed_python_over_system_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir) / "state"
            fake_bin = Path(tmp_dir) / "fake-bin"
            fake_bin.mkdir()
            fake_python = fake_bin / ("python.exe" if os.name == "nt" else "python")
            fake_python.write_text("", encoding="utf-8")
            with patch("spark_cli.cli.STATE_DIR", state_dir):
                with patch.dict(os.environ, {"PATH": str(fake_bin)}, clear=False):
                    env = shell_command_env()
            shim_dir = state_dir / "runtime-shims"
            self.assertEqual(env["PATH"].split(os.pathsep)[0], str(shim_dir))
            expected = "python.cmd" if os.name == "nt" else "python"
            python_shim = shim_dir / expected
            self.assertTrue(python_shim.exists())
            if os.name != "nt":
                self.assertIn(str(Path(sys.executable)), python_shim.read_text(encoding="utf-8"))
                self.assertTrue((shim_dir / "pip").exists())
            else:
                self.assertIn(sys.executable, python_shim.read_text(encoding="utf-8"))
                self.assertTrue((shim_dir / "pip.cmd").exists())

    def test_read_generated_env_ignores_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / "module.env"
            env_path.write_text("# comment\n\nA=1\nB=two=three\n", encoding="utf-8")
            self.assertEqual(read_generated_env(env_path), {"A": "1", "B": "two=three"})

    def test_command_with_managed_python_rewrites_pip_installers(self) -> None:
        rewritten = command_with_managed_python("python -m pip install -e .")
        self.assertIn("-m pip install -e .", rewritten)
        self.assertNotEqual(rewritten, "python -m pip install -e .")
        self.assertIn(str(Path(sys.executable)), rewritten)
        uv_rewritten = command_with_managed_python("uv pip install -e .")
        self.assertIn("-m pip install -e .", uv_rewritten)
        self.assertNotIn("uv pip", uv_rewritten)

    def test_execute_install_commands_uses_managed_python_for_python_commands(self) -> None:
        module = Module(
            name="managed-python",
            path=Path.cwd(),
            manifest={
                "module": {"name": "managed-python", "version": "0.1.0", "kind": "runtime", "plane": "runtime"},
                "install": {"dev": {"commands": ["python -m pip install -e ."]}},
            },
        )
        captured: list[str] = []

        def fake_run_shell(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
            captured.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("spark_cli.cli.run_shell", fake_run_shell):
            execute_install_commands(module)

        self.assertEqual(len(captured), 1)
        self.assertIn(str(Path(sys.executable)), captured[0])
        self.assertIn("-m pip install -e .", captured[0])

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
            "telegram.relay_secret": {"prompt": "Relay secret", "required": False},
        }
        existing = {"telegram.bot_token": "already-set"}
        prompted: list[str] = []

        def fake_getpass(prompt: str) -> str:
            prompted.append(prompt)
            if "Admin ids" in prompt:
                return "123,456"
            if "Relay secret" in prompt:
                return ""
            return "SHOULD-NOT-HAPPEN"

        with patch("spark_cli.cli.getpass.getpass", side_effect=fake_getpass):
            collected = run_setup_wizard(existing, requirements)
        self.assertEqual(collected["telegram.bot_token"], "already-set")
        self.assertEqual(collected["telegram.admin_ids"], "123,456")
        self.assertNotIn("telegram.relay_secret", collected)
        self.assertEqual(len(prompted), 2)

    def test_run_setup_wizard_reprompts_when_required_secret_empty(self) -> None:
        requirements = {"telegram.bot_token": {"prompt": "Bot token", "required": True}}
        answers = iter(["", "finally-a-value"])

        with patch("spark_cli.cli.getpass.getpass", side_effect=lambda _prompt: next(answers)):
            collected = run_setup_wizard({}, requirements)
        self.assertEqual(collected["telegram.bot_token"], "finally-a-value")

    def test_run_llm_provider_wizard_selects_zai_and_collects_key(self) -> None:
        class Args:
            llm_provider = None
            chat_llm_provider = None
            builder_llm_provider = None
            memory_llm_provider = None
            mission_llm_provider = None

        args = Args()
        with patch("builtins.input", return_value="zai"), \
             patch("spark_cli.cli.getpass.getpass", return_value="zai-test-key"):
            values = run_llm_provider_wizard(args, {})
        self.assertEqual(args.llm_provider, "zai")
        self.assertEqual(values["llm.zai.api_key"], "zai-test-key")

    def test_run_llm_provider_wizard_defaults_to_openai_codex_oauth(self) -> None:
        class Args:
            llm_provider = None
            chat_llm_provider = None
            builder_llm_provider = None
            memory_llm_provider = None
            mission_llm_provider = None

        args = Args()
        with patch("builtins.input", return_value=""), \
             patch("spark_cli.cli.detect_codex_cli", return_value={"present": True, "path": "codex"}), \
             patch("spark_cli.cli.getpass.getpass") as getpass_mock:
            values = run_llm_provider_wizard(args, {})
        self.assertEqual(args.llm_provider, "openai")
        self.assertEqual(values, {})
        getpass_mock.assert_not_called()

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
            telegram_relay_secret = None
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
            telegram_relay_secret = None
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

    def test_git_command_enables_long_paths_for_registry_clones(self) -> None:
        self.assertEqual(
            git_command("clone", "--depth=1", "https://example.test/repo.git", "target"),
            ["git", "-c", "core.longpaths=true", "clone", "--depth=1", "https://example.test/repo.git", "target"],
        )

    def test_long_path_aware_prefixes_windows_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = long_path_aware(Path(tmp_dir))
        if os.name == "nt":
            self.assertTrue(result.startswith("\\\\?\\"))
        else:
            self.assertFalse(result.startswith("\\\\?\\"))

    def test_remove_tree_removes_readonly_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "tree"
            root.mkdir()
            readonly = root / "readonly.txt"
            readonly.write_text("locked", encoding="utf-8")
            readonly.chmod(0o444)
            remove_tree(root)
            self.assertFalse(root.exists())

    def test_ensure_bundle_modules_available_calls_resolve_for_missing(self) -> None:
        existing = make_module("already-here", ["cap.x"])

        def fake_resolver(target: str, modules: dict) -> Module:
            return make_module(target, ["cap.y"])

        with patch("spark_cli.cli.resolve_install_target", side_effect=fake_resolver):
            augmented = ensure_bundle_modules_available(
                ["already-here", "needs-clone-a", "needs-clone-b"],
                {existing.name: existing},
            )
        self.assertEqual(
            sorted(augmented.keys()),
            ["already-here", "needs-clone-a", "needs-clone-b"],
        )
        self.assertIs(augmented["already-here"], existing)

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
                "needs": {"secrets": ["telegram.bot_token", "telegram.relay_secret"]},
                "secrets": {
                    "telegram_bot_token": {"env_var": "BOT_TOKEN", "storage": "keychain"},
                    "telegram_relay_secret": {"env_var": "TELEGRAM_RELAY_SECRET", "storage": "keychain"},
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
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry_path = Path(tmp_dir) / "installed.json"
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
            with patch("spark_cli.cli.REGISTRY_PATH", registry_path):
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
            payload = load_json(registry_path, {})
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

    def test_build_module_repair_hints_reports_runtime_version_mismatch(self) -> None:
        module = Module(
            name="spawner-ui",
            path=Path("C:/tmp/spawner-ui"),
            manifest={
                "module": {"name": "spawner-ui", "version": "0.0.1", "kind": "app", "plane": "execution"},
                "runtime": {"kind": "node", "version": ">=22"},
            },
        )
        result = {"name": "spawner-ui", "healthy": False}
        with patch("spark_cli.cli.detect_runtime_binary", return_value={"present": True, "version": "v18.19.1", "path": "/usr/bin/node"}):
            hints = build_module_repair_hints(module, result, {"spawner-ui": result}, {})
        self.assertTrue(any("Repair runtime first:" in hint and "node >=22 not satisfied" in hint for hint in hints))
        self.assertTrue(any("installed wrapper" in hint for hint in hints))

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
        self.assertIn(
            "No LLM provider is configured. Run `spark setup` to choose chat, builder, memory, and mission providers.",
            hints,
        )

    def test_build_status_repair_hints_reports_cloud_llm_without_key(self) -> None:
        hints = build_status_repair_hints(
            {},
            [],
            {"llm": {"provider": "zai", "api_key_configured": False}},
        )
        self.assertIn("LLM provider uses Z.AI but is missing an API key. Re-run `spark setup --llm-provider zai --zai-api-key <key>`.", hints)

    def test_build_status_repair_hints_uses_legacy_secret_keys_for_api_auth(self) -> None:
        hints = build_status_repair_hints(
            {},
            [],
            {"secret_keys": ["llm.zai.api_key"], "llm": {"provider": "zai", "api_key_configured": True}},
        )
        self.assertEqual([], [hint for hint in hints if "Z.AI" in hint or "missing an API key" in hint])

    def test_build_status_repair_hints_allows_openai_codex_auth(self) -> None:
        hints = build_status_repair_hints(
            {},
            [],
            {"llm": {"provider": "openai", "api_key_configured": False, "auth_mode": "codex_oauth"}},
        )
        self.assertEqual([], [hint for hint in hints if "OpenAI is selected" in hint or "missing an API key" in hint])

    def test_build_status_repair_hints_reports_openai_without_auth(self) -> None:
        with patch("spark_cli.cli.detect_codex_cli", return_value={"present": False}):
            hints = build_status_repair_hints(
                {},
                [],
                {"llm": {"provider": "openai", "api_key_configured": False, "auth_mode": "not_configured"}},
            )
        self.assertIn(
            "LLM provider uses OpenAI but neither Codex CLI OAuth nor OPENAI_API_KEY is configured. Run `codex` to sign in with ChatGPT, or rerun `spark setup --llm-provider openai --openai-api-key <key>`.",
            hints,
        )

    def test_build_status_repair_hints_reports_unconfigured_llm_roles(self) -> None:
        hints = build_status_repair_hints(
            {},
            [],
            {
                "llm": {
                    "provider": "not_configured",
                    "roles": {
                        "chat": {"provider": "not_configured", "auth_mode": "not_configured"},
                        "builder": {"provider": "not_configured", "auth_mode": "not_configured"},
                        "memory": {"provider": "not_configured", "auth_mode": "not_configured"},
                        "mission": {"provider": "not_configured", "auth_mode": "not_configured"},
                    },
                }
            },
        )
        self.assertIn(
            "No LLM provider is configured. Run `spark setup` to choose chat, builder, memory, and mission providers.",
            hints,
        )
        self.assertIn(
            "LLM role `chat` is not configured. Run `spark setup --chat-llm-provider openai` to use Codex/OpenAI, or choose anthropic, zai, ollama, or codex.",
            hints,
        )

    def test_collect_telegram_fix_payload_flags_quiet_bot_blockers(self) -> None:
        status_payload = {
            "ok": False,
            "modules": [
                {"name": "spark-telegram-bot", "healthy": False, "detail": "Relay auth: configured"},
            ],
            "tracked_pids": {},
            "llm": {
                "provider": "not_configured",
                "roles": {
                    "chat": {"provider": "not_configured", "auth_mode": "not_configured"},
                    "builder": {"provider": "not_configured", "auth_mode": "not_configured"},
                    "memory": {"provider": "not_configured", "auth_mode": "not_configured"},
                    "mission": {"provider": "not_configured", "auth_mode": "not_configured"},
                },
            },
            "repair_hints": ["No LLM provider is configured."],
        }
        with patch("spark_cli.cli.collect_status_payload", return_value=status_payload), \
            patch("spark_cli.cli.load_json", return_value={"secret_keys": ["telegram.relay_secret"]}), \
            patch("spark_cli.cli.read_generated_env", return_value={}):
            payload = collect_telegram_fix_payload()
        self.assertFalse(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(checks["bot_token"]["ok"])
        self.assertFalse(checks["admin_allowlist"]["ok"])
        self.assertFalse(checks["builder_memory_roots"]["ok"])
        self.assertFalse(checks["llm_roles"]["ok"])
        self.assertFalse(checks["telegram_process"]["ok"])
        self.assertIn("spark verify --deep", payload["next_commands"])
        self.assertIn("spark restart telegram-starter", payload["next_commands"])

    def test_collect_telegram_fix_payload_flags_rejected_stored_bot_token(self) -> None:
        status_payload = {
            "ok": False,
            "modules": [
                {
                    "name": "spark-telegram-bot",
                    "healthy": False,
                    "detail": "Telegram health: FAILED - Telegram rejected BOT_TOKEN.",
                },
            ],
            "tracked_pids": {},
            "llm": {
                "provider": "zai",
                "roles": {
                    "chat": {"provider": "zai", "auth_mode": "api_key"},
                    "builder": {"provider": "zai", "auth_mode": "api_key"},
                    "memory": {"provider": "zai", "auth_mode": "api_key"},
                    "mission": {"provider": "zai", "auth_mode": "api_key"},
                },
            },
            "repair_hints": [],
        }
        with patch("spark_cli.cli.collect_status_payload", return_value=status_payload), \
             patch("spark_cli.cli.load_json", return_value={"secret_keys": ["telegram.bot_token", "telegram.admin_ids"]}), \
             patch("spark_cli.cli.read_generated_env", return_value={}):
            payload = collect_telegram_fix_payload()

        checks = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(checks["bot_token"]["ok"])
        self.assertIn("Telegram rejected it", checks["bot_token"]["detail"])
        self.assertEqual(checks["bot_token"]["repair"], "spark setup --bot-token <BOTFATHER_TOKEN>")

    def test_provider_status_payload_reports_role_readiness(self) -> None:
        setup_state = {
            "llm": {
                "provider": "openai",
                "roles": {
                    "chat": {"provider": "openai", "model": "gpt-5.5", "auth_mode": "codex_oauth", "bot_provider": "codex"},
                    "builder": {"provider": "openai", "model": "gpt-5.5", "auth_mode": "codex_oauth", "bot_provider": "codex"},
                    "memory": {"provider": "ollama", "model": "llama3.1", "auth_mode": "local", "bot_provider": "ollama"},
                    "mission": {"provider": "not_configured", "model": "", "auth_mode": "not_configured", "bot_provider": "none"},
                },
            }
        }
        with patch("spark_cli.cli.load_json", return_value=setup_state):
            payload = provider_status_payload()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["roles"]["chat"]["ready"])
        self.assertTrue(payload["roles"]["memory"]["ready"])
        self.assertFalse(payload["roles"]["mission"]["ready"])
        self.assertIn(
            "LLM role `mission` is not configured. Run `spark setup --mission-llm-provider openai` to use Codex/OpenAI, or choose anthropic, zai, ollama, or codex.",
            payload["repair_hints"],
        )

    def test_provider_status_payload_accepts_legacy_top_level_auth(self) -> None:
        setup_state = {
            "llm": {
                "provider": "openai",
                "model": "gpt-5.5",
                "auth_mode": "codex_oauth",
            }
        }
        with patch("spark_cli.cli.load_json", return_value=setup_state):
            payload = provider_status_payload()
        self.assertTrue(payload["ok"])
        for role in ("chat", "builder", "memory", "mission"):
            self.assertTrue(payload["roles"][role]["ready"])
            self.assertEqual(payload["roles"][role]["auth_mode"], "codex_oauth")
            self.assertEqual(payload["roles"][role]["model"], "gpt-5.5")

    def test_provider_status_payload_uses_legacy_secret_keys_for_api_auth(self) -> None:
        setup_state = {
            "secret_keys": ["llm.zai.api_key"],
            "llm": {
                "provider": "zai",
                "model": "glm-5.1",
                "api_key_configured": True,
            },
        }
        with patch("spark_cli.cli.load_json", return_value=setup_state):
            payload = provider_status_payload()
        self.assertTrue(payload["ok"])
        for role in ("chat", "builder", "memory", "mission"):
            self.assertTrue(payload["roles"][role]["ready"])
            self.assertEqual(payload["roles"][role]["auth_mode"], "api_key")
            self.assertEqual(payload["roles"][role]["model"], "glm-5.1")

    def test_collect_verify_payload_reports_launch_ready_stack(self) -> None:
        expected = [
            "spark-researcher",
            "spark-intelligence-builder",
            "domain-chip-memory",
            "spawner-ui",
            "spark-telegram-bot",
        ]
        status_payload = {
            "ok": True,
            "modules": [{"name": name, "healthy": True} for name in expected],
            "tracked_pids": {
                "spark-telegram-bot": {"pid": 101},
                "spawner-ui": {"pid": 102},
            },
            "repair_hints": [],
        }
        provider_payload = {
            "ok": True,
            "roles": {
                role: {"provider": "openai", "auth_mode": "codex_oauth", "ready": True}
                for role in ("chat", "builder", "memory", "mission")
            },
        }
        setup_state = {
            "bundle": "telegram-starter",
            "secret_keys": ["telegram.bot_token", "telegram.admin_ids"],
            "builder_home": "C:/tmp/spark/state/spark-intelligence",
        }
        installed = {name: {"path": f"C:/tmp/spark/modules/{name}"} for name in expected}

        def fake_load_json(path: Path, default: object) -> object:
            if Path(path).name == "setup.json":
                return setup_state
            if Path(path).name == "installed.json":
                return installed
            return default

        def fake_read_generated_env(path: Path) -> dict[str, str]:
            if Path(path).name == "spark-telegram-bot.env":
                return {
                    "TELEGRAM_GATEWAY_MODE": "polling",
                    "SPARK_BUILDER_BRIDGE_MODE": "required",
                    "SPARK_BUILDER_HOME": "C:/tmp/spark/state/spark-intelligence",
                }
            if Path(path).name == "spark-intelligence-builder.env":
                return {
                    "SPARK_INTELLIGENCE_HOME": "C:/tmp/spark/state/spark-intelligence",
                    "SPARK_DOMAIN_CHIP_MEMORY_ROOT": "C:/tmp/spark/modules/domain-chip-memory",
                    "SPARK_RESEARCHER_ROOT": "C:/tmp/spark/modules/spark-researcher",
                }
            if Path(path).name == "spawner-ui.env":
                return {
                    "MISSION_CONTROL_WEBHOOK_URLS": "http://127.0.0.1:8788/spawner-events",
                    "TELEGRAM_RELAY_SECRET": "relay",
                    "DEFAULT_MISSION_PROVIDER": "codex",
                }
            return {}

        with patch("spark_cli.cli.collect_status_payload", return_value=status_payload), \
            patch("spark_cli.cli.provider_status_payload", return_value=provider_payload), \
            patch("spark_cli.cli.load_json", side_effect=fake_load_json), \
            patch("spark_cli.cli.read_generated_env", side_effect=fake_read_generated_env), \
            patch("spark_cli.cli.resolve_bundle_names", return_value=expected), \
            patch("spark_cli.cli.pid_is_running", return_value=True):
            payload = collect_verify_payload()
        self.assertTrue(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(checks["starter_bundle"]["ok"])
        self.assertTrue(checks["telegram_long_polling_security"]["ok"])
        self.assertTrue(checks["builder_memory_bridge"]["ok"])
        self.assertTrue(checks["spawner_mission_relay"]["ok"])
        self.assertTrue(checks["runtime_processes"]["ok"])

    def test_collect_verify_payload_deep_runs_builder_memory_direct_smoke(self) -> None:
        expected = [
            "spark-researcher",
            "spark-intelligence-builder",
            "domain-chip-memory",
            "spawner-ui",
            "spark-telegram-bot",
        ]
        status_payload = {
            "ok": True,
            "modules": [{"name": name, "healthy": True} for name in expected],
            "tracked_pids": {
                "spark-telegram-bot": {"pid": 101},
                "spawner-ui": {"pid": 102},
            },
            "repair_hints": [],
        }
        provider_payload = {
            "ok": True,
            "roles": {
                role: {"provider": "openai", "auth_mode": "codex_oauth", "ready": True}
                for role in ("chat", "builder", "memory", "mission")
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            installed = {
                name: {"path": str(root / "modules" / name)}
                for name in expected
            }
            for name in expected:
                (root / "modules" / name / "src").mkdir(parents=True, exist_ok=True)
            setup_state = {
                "bundle": "telegram-starter",
                "secret_keys": ["telegram.bot_token", "telegram.admin_ids"],
                "builder_home": str(root / "state" / "spark-intelligence"),
            }

            def fake_load_json(path: Path, default: object) -> object:
                if Path(path).name == "setup.json":
                    return setup_state
                if Path(path).name == "installed.json":
                    return installed
                return default

            def fake_read_generated_env(path: Path) -> dict[str, str]:
                if Path(path).name == "spark-telegram-bot.env":
                    return {
                        "TELEGRAM_GATEWAY_MODE": "polling",
                        "SPARK_BUILDER_BRIDGE_MODE": "required",
                        "SPARK_BUILDER_HOME": str(root / "state" / "spark-intelligence"),
                    }
                if Path(path).name == "spark-intelligence-builder.env":
                    return {
                        "SPARK_INTELLIGENCE_HOME": str(root / "state" / "spark-intelligence"),
                        "SPARK_DOMAIN_CHIP_MEMORY_ROOT": str(root / "modules" / "domain-chip-memory"),
                        "SPARK_RESEARCHER_ROOT": str(root / "modules" / "spark-researcher"),
                    }
                if Path(path).name == "spawner-ui.env":
                    return {
                        "MISSION_CONTROL_WEBHOOK_URLS": "http://127.0.0.1:8788/spawner-events",
                        "TELEGRAM_RELAY_SECRET": "relay",
                        "DEFAULT_MISSION_PROVIDER": "codex",
                    }
                return {}

            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"ok": true}\n',
                stderr="",
            )
            with patch("spark_cli.cli.collect_status_payload", return_value=status_payload), \
                patch("spark_cli.cli.provider_status_payload", return_value=provider_payload), \
                patch("spark_cli.cli.load_json", side_effect=fake_load_json), \
                patch("spark_cli.cli.read_generated_env", side_effect=fake_read_generated_env), \
                patch("spark_cli.cli.resolve_bundle_names", return_value=expected), \
                patch("spark_cli.cli.pid_is_running", return_value=True), \
                patch("spark_cli.cli.subprocess.run", return_value=completed) as run_mock:
                payload = collect_verify_payload(deep=True)
        self.assertTrue(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(checks["builder_memory_direct_smoke"]["ok"])
        self.assertIn("wrote, read, and cleaned up", checks["builder_memory_direct_smoke"]["detail"])
        command = run_mock.call_args.args[0]
        self.assertIn("direct-smoke", command)
        self.assertIn("--sdk-module", command)

    def test_collect_verify_payload_flags_missing_mission_provider_and_webhook(self) -> None:
        expected = ["spark-researcher", "spark-intelligence-builder", "domain-chip-memory", "spawner-ui", "spark-telegram-bot"]
        status_payload = {
            "ok": False,
            "modules": [{"name": name, "healthy": True} for name in expected],
            "tracked_pids": {},
            "repair_hints": ["No LLM provider is configured."],
        }
        provider_payload = {"ok": False, "roles": {}, "repair_hints": ["configure providers"]}
        setup_state = {"bundle": "telegram-starter", "secret_keys": ["telegram.admin_ids"]}
        installed = {name: {"path": f"C:/tmp/spark/modules/{name}"} for name in expected}

        def fake_load_json(path: Path, default: object) -> object:
            if Path(path).name == "setup.json":
                return setup_state
            if Path(path).name == "installed.json":
                return installed
            return default

        def fake_read_generated_env(path: Path) -> dict[str, str]:
            if Path(path).name == "spark-telegram-bot.env":
                return {
                    "BOT_TOKEN": "should-not-be-here",
                    "TELEGRAM_GATEWAY_MODE": "webhook",
                    "TELEGRAM_WEBHOOK_URL": "https://example.test/hook",
                }
            if Path(path).name == "spawner-ui.env":
                return {"MISSION_CONTROL_WEBHOOK_URLS": "http://127.0.0.1:8788/spawner-events"}
            return {}

        with patch("spark_cli.cli.collect_status_payload", return_value=status_payload), \
            patch("spark_cli.cli.provider_status_payload", return_value=provider_payload), \
            patch("spark_cli.cli.load_json", side_effect=fake_load_json), \
            patch("spark_cli.cli.read_generated_env", side_effect=fake_read_generated_env), \
            patch("spark_cli.cli.resolve_bundle_names", return_value=expected):
            payload = collect_verify_payload()
        self.assertFalse(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(checks["llm_roles"]["ok"])
        self.assertFalse(checks["telegram_long_polling_security"]["ok"])
        self.assertFalse(checks["builder_memory_bridge"]["ok"])
        self.assertFalse(checks["spawner_mission_relay"]["ok"])
        self.assertFalse(checks["runtime_processes"]["ok"])

    def test_collect_verify_payload_accepts_legacy_spawner_bot_default_provider(self) -> None:
        expected = ["spark-researcher", "spark-intelligence-builder", "domain-chip-memory", "spawner-ui", "spark-telegram-bot"]
        status_payload = {
            "ok": True,
            "modules": [{"name": name, "healthy": True} for name in expected],
            "tracked_pids": {
                "spark-telegram-bot": {"pid": 101},
                "spawner-ui": {"pid": 102},
            },
            "repair_hints": [],
        }
        provider_payload = {
            "ok": True,
            "roles": {
                role: {"provider": "zai", "auth_mode": "api_key", "ready": True}
                for role in ("chat", "builder", "memory", "mission")
            },
        }
        setup_state = {
            "bundle": "telegram-starter",
            "secret_keys": ["telegram.bot_token", "telegram.admin_ids"],
            "builder_home": "C:/tmp/spark/state/spark-intelligence",
        }
        installed = {name: {"path": f"C:/tmp/spark/modules/{name}"} for name in expected}

        def fake_load_json(path: Path, default: object) -> object:
            if Path(path).name == "setup.json":
                return setup_state
            if Path(path).name == "installed.json":
                return installed
            return default

        def fake_read_generated_env(path: Path) -> dict[str, str]:
            if Path(path).name == "spark-telegram-bot.env":
                return {
                    "TELEGRAM_GATEWAY_MODE": "polling",
                    "SPARK_BUILDER_BRIDGE_MODE": "required",
                    "SPARK_BUILDER_HOME": "C:/tmp/spark/state/spark-intelligence",
                }
            if Path(path).name == "spark-intelligence-builder.env":
                return {
                    "SPARK_INTELLIGENCE_HOME": "C:/tmp/spark/state/spark-intelligence",
                    "SPARK_DOMAIN_CHIP_MEMORY_ROOT": "C:/tmp/spark/modules/domain-chip-memory",
                    "SPARK_RESEARCHER_ROOT": "C:/tmp/spark/modules/spark-researcher",
                }
            if Path(path).name == "spawner-ui.env":
                return {
                    "MISSION_CONTROL_WEBHOOK_URLS": "http://127.0.0.1:8788/spawner-events",
                    "TELEGRAM_RELAY_SECRET": "relay",
                    "SPARK_BOT_DEFAULT_PROVIDER": "zai",
                }
            return {}

        with patch("spark_cli.cli.collect_status_payload", return_value=status_payload), \
            patch("spark_cli.cli.provider_status_payload", return_value=provider_payload), \
            patch("spark_cli.cli.load_json", side_effect=fake_load_json), \
            patch("spark_cli.cli.read_generated_env", side_effect=fake_read_generated_env), \
            patch("spark_cli.cli.resolve_bundle_names", return_value=expected), \
            patch("spark_cli.cli.pid_is_running", return_value=True):
            payload = collect_verify_payload()
        self.assertTrue(payload["ok"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(checks["spawner_mission_relay"]["ok"])

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

    def test_install_script_bootstraps_local_prefix_contract(self) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"
        self.assertNotIn(b"\r\n", script_path.read_bytes())
        script = script_path.read_text(encoding="utf-8")
        self.assertIn('SPARK_PREFIX="${SPARK_PREFIX:-$HOME/.spark}"', script)
        self.assertIn('SPARK_NODE_VERSION="${SPARK_NODE_VERSION:-22.18.0}"', script)
        self.assertIn("normalize_macos_locale", script)
        self.assertIn('export LC_ALL="en_US.UTF-8"', script)
        self.assertIn("detect_node_platform", script)
        self.assertIn('Darwin) os_id="darwin"', script)
        self.assertIn('arm64|aarch64) arch_id="arm64"', script)
        self.assertIn("node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM.tar.xz", script)
        self.assertIn("SHASUMS256.txt", script)
        self.assertIn("verify_node_archive", script)
        self.assertIn("python3 -m venv", script)
        self.assertIn("pip install -e", script)
        self.assertIn("SPARK_LOCAL_REGISTRY", script)
        self.assertIn("SPARK_ALLOW_DEV_SOURCE", script)
        self.assertIn("validate_install_settings", script)
        self.assertIn("Refusing non-canonical Spark CLI source", script)
        self.assertIn('SPARK_AUTOSTART="${SPARK_AUTOSTART:-1}"', script)
        self.assertIn("--no-autostart", script)
        self.assertIn('export SPARK_HOME="$SPARK_PREFIX"', script)
        self.assertIn('local env_file="$SPARK_PREFIX/env"', script)
        self.assertIn('export PATH="$SPARK_PREFIX/bin:$SPARK_PREFIX/tools/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM/bin:\\$PATH"', script)
        self.assertIn('"$SPARK_PREFIX/bin/spark" setup "$SPARK_BUNDLE"', script)
        self.assertIn('"$SPARK_PREFIX/bin/spark" autostart install "$SPARK_BUNDLE" --now', script)
        self.assertIn('local spark_setup_cmd=("$SPARK_PREFIX/bin/spark" setup "$SPARK_BUNDLE")', script)
        self.assertNotIn('"${setup_words[@]}" "${extra_setup_args[@]}"', script)
        self.assertIn(r"To use \`spark\` by name in this terminal:", script)
        self.assertIn('source "$SPARK_PREFIX/env"', script)
        self.assertIn("$SPARK_PREFIX/bin/spark providers list", script)
        self.assertIn("$SPARK_PREFIX/bin/spark providers status", script)
        self.assertIn("$SPARK_PREFIX/bin/spark verify", script)
        self.assertIn("$SPARK_PREFIX/bin/spark fix telegram", script)
        self.assertIn("spark_cli.cli", script)

    def test_windows_install_script_bootstraps_local_prefix_contract(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "scripts" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$Prefix = "$HOME\\.spark"', script)
        self.assertIn('[string]$NodeVersion = "22.18.0"', script)
        self.assertIn("node-v$NodeVersion-win-x64.zip", script)
        self.assertIn("SHASUMS256.txt", script)
        self.assertIn("Test-NodeArchiveHash", script)
        self.assertIn("python -m venv", script)
        self.assertIn("pip install -e", script)
        self.assertIn("$env:PATH = \"$nodeDir;$env:PATH\"", script)
        self.assertIn('set "SPARK_HOME=$Script:SparkPrefix"', script)
        self.assertIn("function Add-SparkBinToUserPath", script)
        self.assertIn('[Environment]::SetEnvironmentVariable("Path", $newPath, "User")', script)
        self.assertIn("Add-SparkBinToUserPath", script)
        self.assertIn("Warn-SparkCommandConflict", script)
        self.assertIn("A different spark command is earlier on fresh Windows PATH", script)
        self.assertIn("[switch]$AllowDevSource", script)
        self.assertIn("Test-InstallSettings", script)
        self.assertIn("Refusing non-canonical Spark CLI source", script)
        self.assertIn("& $sparkCmd setup $Bundle @SetupArg", script)
        self.assertIn("[switch]$NoAutostart", script)
        self.assertIn("& $sparkCmd autostart install $Bundle --now", script)
        self.assertIn("spark providers list", script)
        self.assertIn("spark providers status", script)
        self.assertIn("spark verify", script)
        self.assertIn("spark fix telegram", script)

    def test_readme_does_not_recommend_piping_remote_installers_to_shell(self) -> None:
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        compact_readme = " ".join(readme.split())
        self.assertNotIn("| bash", readme)
        self.assertNotIn("| iex", readme.lower())
        self.assertIn("avoid piping remote scripts directly into a shell", compact_readme)

    def test_cli_honors_spark_home_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = dict(os.environ)
            env["SPARK_HOME"] = tmp_dir
            result = subprocess.run(
                [
                    os.environ.get("PYTHON", sys.executable),
                    "-c",
                    "import spark_cli.cli as c; print(c.SPARK_HOME)",
                ],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(Path(result.stdout.strip()), Path(tmp_dir))


if __name__ == "__main__":
    unittest.main()
