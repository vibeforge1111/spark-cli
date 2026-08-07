from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from spark_cli import cli
from spark_cli import managed_secret_runtime as managed
from spark_cli.cli import Module


def make_module(name: str, *, root: Path | None = None, secrets: list[str] | None = None) -> Module:
    path = (root or Path("C:/tmp")) / name
    manifest: dict[str, Any] = {
        "module": {"name": name, "version": "1.0.0", "kind": "service", "plane": "execution"},
        "provides": {"capabilities": []},
        "needs": {"modules": [], "secrets": list(secrets or [])},
        "claims": {"secrets": [], "ports": [], "routes": []},
        "secrets": {},
        "run": {"default": {"command": "npm run start", "ready_check": "process"}},
    }
    for secret_id in secrets or []:
        manifest["secrets"][secret_id.replace(".", "_")] = {
            "env_var": secret_id.upper().replace(".", "_"),
            "required": False,
            "storage": "keychain",
        }
    return Module(name=name, path=path, manifest=manifest)


@contextmanager
def unlocked(*_args: object, **_kwargs: object):
    yield


class ManagedVoiceRuntimeTests(unittest.TestCase):
    def test_voice_setup_keeps_elevenlabs_precedence_and_gateway_secret_free(self) -> None:
        builder: dict[str, str] = {}
        gateway: dict[str, str] = {}
        managed.configure_voice_owner_envs(
            builder,
            gateway,
            Path("C:/tmp/spark-voice-comms"),
            {
                managed.VOICE_ELEVENLABS_SECRET_ID: "eleven-secret",
                managed.VOICE_OPENAI_SECRET_ID: "openai-secret",
            },
        )

        self.assertEqual(builder["ELEVENLABS_API_KEY"], "eleven-secret")
        self.assertNotIn("VOICE_OPENAI_API_KEY", builder)
        self.assertEqual(gateway["SPARK_TELEGRAM_VOICE_TTS_PROVIDER"], "elevenlabs")
        self.assertEqual(gateway[managed.TELEGRAM_VOICE_TTS_SECRET_REF_ENV], "ELEVENLABS_API_KEY")
        self.assertNotIn("ELEVENLABS_API_KEY", gateway)

    def test_voice_setup_uses_dedicated_openai_key_when_elevenlabs_is_absent(self) -> None:
        builder: dict[str, str] = {}
        gateway: dict[str, str] = {}
        voice_root = Path("C:/tmp/spark-voice-comms")
        managed.configure_voice_owner_envs(
            builder,
            gateway,
            voice_root,
            {managed.VOICE_OPENAI_SECRET_ID: "openai-voice-secret"},
        )

        self.assertEqual(builder["VOICE_OPENAI_API_KEY"], "openai-voice-secret")
        self.assertEqual(builder["SPARK_TELEGRAM_VOICE_TTS_PROVIDER"], "openai-realtime")
        self.assertEqual(gateway["SPARK_VOICE_COMMS_ROOT"], str(voice_root))
        self.assertEqual(gateway[managed.TELEGRAM_VOICE_TTS_SECRET_REF_ENV], "VOICE_OPENAI_API_KEY")
        self.assertNotIn("VOICE_OPENAI_API_KEY", gateway)

    def test_named_profile_copy_is_available_for_one_time_voice_migration(self) -> None:
        profile_path = Path("C:/tmp/spark-telegram-bot.primary.env")
        requirement = {
            "env_var": "VOICE_OPENAI_API_KEY",
            "modules": ["spark-intelligence-builder", "spark-voice-comms"],
        }

        def read(path: Path) -> dict[str, str]:
            return {"VOICE_OPENAI_API_KEY": "legacy-voice-secret"} if path == profile_path else {}

        with patch.object(cli, "telegram_generated_env_paths", return_value=[profile_path]), patch.object(
            cli, "read_generated_env", side_effect=read
        ), patch.object(cli, "load_json", return_value={}):
            self.assertEqual(managed.fetch_generated_secret_value(cli, requirement), "legacy-voice-secret")

    def test_telegram_receives_only_the_selected_managed_voice_secret(self) -> None:
        gateway = make_module("spark-telegram-bot")
        generated = {
            "SPARK_VOICE_COMMS_ROOT": "C:/tmp/spark-voice-comms",
            managed.TELEGRAM_VOICE_TTS_SECRET_REF_ENV: "VOICE_OPENAI_API_KEY",
            "VOICE_OPENAI_API_KEY": "legacy-openai",
            "ELEVENLABS_API_KEY": "legacy-eleven",
        }
        secrets = {
            managed.VOICE_OPENAI_SECRET_ID: "managed-openai",
            managed.VOICE_ELEVENLABS_SECRET_ID: "managed-eleven",
        }
        with patch.object(cli, "shell_command_env", return_value={}), patch.object(
            cli, "read_generated_env", return_value=generated
        ), patch.object(cli, "keychain_env_for_module", return_value={}), patch.object(
            cli, "keychain_env_for_telegram_profile", return_value={}
        ), patch.object(cli, "fetch_secret", side_effect=lambda secret_id: secrets.get(secret_id)):
            env = cli.module_runtime_env(gateway)

        self.assertEqual(env["VOICE_OPENAI_API_KEY"], "managed-openai")
        self.assertNotIn("ELEVENLABS_API_KEY", env)

    def test_unselected_voice_secret_is_not_injected(self) -> None:
        gateway = make_module("spark-telegram-bot")
        with patch.object(cli, "shell_command_env", return_value={}), patch.object(
            cli, "read_generated_env", return_value={"VOICE_OPENAI_API_KEY": "legacy"}
        ), patch.object(cli, "keychain_env_for_module", return_value={}), patch.object(
            cli, "keychain_env_for_telegram_profile", return_value={}
        ), patch.object(
            cli,
            "fetch_secret",
            side_effect=lambda secret_id: "managed" if secret_id == managed.VOICE_OPENAI_SECRET_ID else None,
        ):
            env = cli.module_runtime_env(gateway)

        self.assertNotIn("VOICE_OPENAI_API_KEY", env)


class ManagedBridgeRuntimeTests(unittest.TestCase):
    def test_local_runtime_prefers_managed_bridge_and_unrelated_module_never_receives_it(self) -> None:
        spawner = make_module("spawner-ui")
        unrelated = make_module("spark-character")
        legacy = "legacy-bridge-" + "l" * 32
        stored = "stored-bridge-" + "s" * 32

        def fetch(secret_id: str) -> str | None:
            return stored if secret_id == "spark.bridge_api_key" else None

        with patch.dict(os.environ, {}, clear=True), patch.object(cli, "shell_command_env", side_effect=lambda **_kwargs: {}), patch.object(
            cli, "read_generated_env", return_value={"SPARK_BRIDGE_API_KEY": legacy}
        ), patch.object(cli, "keychain_env_for_module", return_value={}), patch.object(
            cli, "keychain_env_for_telegram_profile", return_value={}
        ), patch.object(cli, "fetch_secret", side_effect=fetch):
            spawner_env = cli.module_runtime_env(spawner)
            unrelated_env = cli.module_runtime_env(unrelated)

        self.assertEqual(spawner_env["SPARK_BRIDGE_API_KEY"], stored)
        self.assertNotIn("SPARK_BRIDGE_API_KEY", unrelated_env)

    def test_hosted_parent_bridge_remains_authoritative_over_stale_local_storage(self) -> None:
        spawner = make_module("spawner-ui")
        hosted = "hosted-bridge-" + "h" * 32
        stale = "stale-local-bridge-" + "s" * 32
        env = {"RAILWAY_ENVIRONMENT": "production", "SPARK_BRIDGE_API_KEY": hosted}
        with patch.dict(os.environ, env, clear=True), patch.object(cli, "shell_command_env", return_value={}), patch.object(
            cli, "read_generated_env", return_value={}
        ), patch.object(cli, "keychain_env_for_module", return_value={}), patch.object(
            cli, "fetch_secret", side_effect=lambda secret_id: stale if secret_id == "spark.bridge_api_key" else None
        ):
            runtime_env = cli.module_runtime_env(spawner)

        self.assertEqual(runtime_env["SPARK_BRIDGE_API_KEY"], hosted)

    def test_explicit_empty_local_bridge_config_blocks_ambient_parent_fallback(self) -> None:
        spawner = make_module("spawner-ui")
        parent = "parent-bridge-" + "p" * 32
        with patch.dict(os.environ, {"SPARK_BRIDGE_API_KEY": parent}, clear=True), patch.object(
            cli, "shell_command_env", return_value={}
        ), patch.object(cli, "read_generated_env", return_value={"SPARK_BRIDGE_API_KEY": ""}), patch.object(
            cli, "keychain_env_for_module", return_value={}
        ), patch.object(cli, "fetch_secret", return_value=None):
            runtime_env = cli.module_runtime_env(spawner)

        self.assertNotIn("SPARK_BRIDGE_API_KEY", runtime_env)

    def test_hosted_setup_does_not_persist_platform_bridge_secret(self) -> None:
        hosted = "hosted-bridge-" + "h" * 32
        env = {"SPARK_LIVE_CONTAINER": "1", "SPARK_BRIDGE_API_KEY": hosted}
        with patch.dict(os.environ, env, clear=True), patch.object(cli, "read_generated_env", return_value={}), patch.object(
            cli, "fetch_secret", return_value="stale-local-bridge-" + "s" * 32
        ), patch.object(cli, "store_secret") as store, patch.object(cli, "remember_setup_secret_key") as remember:
            value = managed.ensure_managed_bridge_api_key(cli, {})

        self.assertEqual(value, hosted)
        store.assert_not_called()
        remember.assert_not_called()

    def test_ready_headers_are_scoped_to_spawner_not_arbitrary_loopback_module(self) -> None:
        bridge = "managed-bridge-" + "m" * 32
        with patch.dict(os.environ, {}, clear=True), patch.object(
            cli, "fetch_secret", side_effect=lambda secret_id: bridge if secret_id == "spark.bridge_api_key" else None
        ):
            spawner_headers = cli.ready_check_headers(
                "http://127.0.0.1:3333/api/health/live", module_name="spawner-ui"
            )
            unrelated_headers = cli.ready_check_headers(
                "http://127.0.0.1:4444/ready", module_name="community-module"
            )

        self.assertEqual(spawner_headers, {"x-spawner-ui-key": bridge, "x-api-key": bridge})
        self.assertEqual(unrelated_headers, {})

    def test_revoke_all_never_recreates_bridge_plaintext(self) -> None:
        self.assertNotIn("SPARK_BRIDGE_API_KEY", cli.REVOKE_ALL_ROTATABLE_ENV_KEYS)
        self.assertNotIn("SPARK_BRIDGE_API_KEY", cli.REVOKE_ALL_SPAWNER_REQUIRED_KEYS)

    def test_scrub_removes_legacy_bridge_from_base_and_profile_files(self) -> None:
        modules = {
            "spawner-ui": make_module("spawner-ui"),
            "spark-telegram-bot": make_module("spark-telegram-bot"),
        }
        profile_path = Path("C:/tmp/spark-telegram-bot.primary.env")
        writes: dict[Path, dict[str, str]] = {}

        def read(path: Path) -> dict[str, str]:
            return {"SPARK_BRIDGE_API_KEY": "legacy-" + "l" * 32, "KEEP": path.name}

        with patch.object(cli, "read_generated_env", side_effect=read), patch.object(
            cli, "write_generated_env", side_effect=lambda path, values: writes.__setitem__(path, dict(values))
        ), patch.object(cli, "telegram_generated_env_paths", return_value=[profile_path]), patch.object(
            cli, "load_json", return_value={}
        ), patch.object(cli, "module_env_path", return_value=None):
            managed.scrub_legacy_bridge_key_files(cli, modules)

        self.assertEqual(len(writes), 3)
        self.assertTrue(all("SPARK_BRIDGE_API_KEY" not in values for values in writes.values()))
        self.assertTrue(all("KEEP" in values for values in writes.values()))

    def test_start_and_stop_bridge_consumers_share_the_rotation_lock(self) -> None:
        lock_held = False

        @contextmanager
        def tracked_lock(*_args: object, **_kwargs: object):
            nonlocal lock_held
            self.assertFalse(lock_held)
            lock_held = True
            try:
                yield
            finally:
                lock_held = False

        def start_probe(*_args: object, **_kwargs: object) -> bool:
            self.assertTrue(lock_held)
            return True

        def stop_probe(*_args: object, **_kwargs: object) -> bool:
            self.assertTrue(lock_held)
            return True

        with patch.object(cli, "process_log_lock", side_effect=tracked_lock), patch.object(
            cli, "_start_module_unlocked", side_effect=start_probe
        ), patch.object(cli, "_stop_tracked_process_key_unlocked", side_effect=stop_probe):
            self.assertTrue(cli.start_module(make_module("spawner-ui")))
            self.assertTrue(cli.stop_tracked_process_key("spark-telegram-bot:primary"))

    def test_start_resolves_child_environment_inside_pid_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            module = make_module("lock-probe", root=Path(tmp_dir))
            lock_held = False

            @contextmanager
            def tracked_pid_lock(*_args: object, **_kwargs: object):
                nonlocal lock_held
                lock_held = True
                try:
                    yield
                finally:
                    lock_held = False

            def resolve_env(*_args: object, **_kwargs: object) -> dict[str, str]:
                self.assertTrue(lock_held)
                return {}

            class RunningProcess:
                pid = 444

                def poll(self) -> None:
                    return None

            with patch.object(cli, "pid_file_lock", side_effect=tracked_pid_lock), patch.object(
                cli, "load_pids", return_value={}
            ), patch.object(cli, "save_pids"), patch.object(cli, "LOG_DIR", Path(tmp_dir) / "logs"), patch.object(
                cli, "module_runtime_env", side_effect=resolve_env
            ), patch.object(cli.subprocess, "Popen", return_value=RunningProcess()), patch.object(
                cli, "wait_for_ready_check", return_value=(True, "ready")
            ), patch.object(cli, "spawner_ready_listener_conflict_detail", return_value=None), patch.object(
                cli, "discover_runtime_pid", return_value=444
            ), patch.object(cli, "update_tracked_runtime_pid"), patch("sys.stdout", new_callable=StringIO):
                self.assertTrue(cli.start_module(module))


class BridgeRotationTests(unittest.TestCase):
    def rotation_patches(
        self,
        *,
        stored: dict[str, str],
        generated: dict[str, dict[str, str]],
        start_effect: Any = True,
        pids: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[Path, dict[str, str]], list[str]]:
        modules = {"spawner-ui": make_module("spawner-ui"), "spark-telegram-bot": make_module("spark-telegram-bot")}
        writes: dict[Path, dict[str, str]] = {}
        stopped: list[str] = []
        live_pids = pids if pids is not None else {}
        running = {int(item.get("pid") or 0) for item in live_pids.values() if isinstance(item, dict)}

        def read(path: Path) -> dict[str, str]:
            return dict(generated.get(path.stem, {}))

        def write(path: Path, values: dict[str, str]) -> None:
            writes[path] = dict(values)
            generated[path.stem] = dict(values)

        def fetch(secret_id: str) -> str | None:
            return stored.get(secret_id)

        def store(secret_id: str, value: str, preferred: str = "keychain") -> str:
            stored[secret_id] = value
            return preferred

        def delete(secret_id: str) -> bool:
            return stored.pop(secret_id, None) is not None

        def stop(process_key: str, pid: int) -> None:
            stopped.append(process_key)
            running.discard(pid)

        patches = patch.multiple(
            cli,
            resolve_installed_modules=lambda: modules,
            read_generated_env=read,
            write_generated_env=write,
            fetch_secret=fetch,
            store_secret=store,
            delete_secret=delete,
            list_stored_secrets=lambda: {key: "keychain" for key in stored},
            process_log_lock=unlocked,
            pid_file_lock=unlocked,
            load_pids=lambda: live_pids,
            save_pids=lambda _pids: None,
            pid_is_running=lambda pid: pid in running,
            stop_module=stop,
            _start_module_unlocked=start_effect if callable(start_effect) else lambda *_args, **_kwargs: bool(start_effect),
            _stop_tracked_process_key_unlocked=lambda _key: True,
            telegram_generated_env_paths=lambda _state: [],
            load_json=lambda *_args, **_kwargs: {},
            module_env_path=lambda _module: None,
            remember_setup_secret_key=lambda _secret_id: None,
        )
        return patches, writes, stopped

    def test_rotation_repairs_mismatched_legacy_and_restores_exact_snapshot_on_failure(self) -> None:
        stored: dict[str, str] = {}
        generated = {
            "spawner-ui": {"SPARK_BRIDGE_API_KEY": "weak"},
            "spark-telegram-bot": {"SPARK_BRIDGE_API_KEY": "different-legacy-" + "d" * 32},
        }
        start_results = iter([False, True])
        patches, _writes, _stopped = self.rotation_patches(
            stored=stored,
            generated=generated,
            start_effect=lambda *_args, **_kwargs: next(start_results),
            pids={"spawner-ui": {"pid": 22}},
        )
        original = {name: dict(values) for name, values in generated.items()}

        with patch.dict(os.environ, {}, clear=True), patches, self.assertRaisesRegex(
            SystemExit, "did not become healthy"
        ):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertNotIn("spark.bridge_api_key", stored)
        self.assertNotIn("spark.bridge_api_key.pending", stored)
        self.assertEqual(generated, original)

    def test_rotation_rejects_collision_with_other_managed_secret_before_staging(self) -> None:
        collision = "provider-secret-" + "p" * 32
        stored = {"llm.openai.api_key": collision}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        patches, _writes, _stopped = self.rotation_patches(stored=stored, generated=generated)

        with patch.dict(os.environ, {}, clear=True), patches, self.assertRaisesRegex(
            SystemExit, "must be different"
        ):
            managed.rotate_managed_bridge_api_key(cli, collision, backend="keychain")

        self.assertNotIn("spark.bridge_api_key.pending", stored)

    def test_keyboard_interrupt_rolls_back_and_cleans_pending_secret(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {"spark.bridge_api_key": old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        start_results = iter([KeyboardInterrupt(), True])

        def start(*_args: object, **_kwargs: object) -> bool:
            result = next(start_results)
            if isinstance(result, BaseException):
                raise result
            return bool(result)

        patches, _writes, _stopped = self.rotation_patches(
            stored=stored,
            generated=generated,
            start_effect=start,
            pids={"spawner-ui": {"pid": 22}},
        )
        with patch.dict(os.environ, {}, clear=True), patches, self.assertRaises(KeyboardInterrupt):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(stored["spark.bridge_api_key"], old)
        self.assertNotIn("spark.bridge_api_key.pending", stored)

    def test_rotation_keeps_exact_running_profiles_and_ignores_unrelated_process(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {"spark.bridge_api_key": old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        pids = {
            "spark-telegram-bot:primary": {"pid": 11},
            "spawner-ui": {"pid": 22},
            "unrelated": {"pid": 33},
        }
        starts: list[tuple[str, str | None]] = []

        def start(module: Module, *, profile: str | None = None, **_kwargs: object) -> bool:
            starts.append((module.name, profile))
            return True

        patches, _writes, stopped = self.rotation_patches(
            stored=stored,
            generated=generated,
            start_effect=start,
            pids=pids,
        )
        with patch.dict(os.environ, {}, clear=True), patches:
            backend = managed.rotate_managed_bridge_api_key(
                cli, "new-bridge-" + "n" * 32, backend="keychain"
            )

        self.assertEqual(backend, "keychain")
        self.assertEqual(stopped, ["spark-telegram-bot:primary", "spawner-ui"])
        self.assertEqual(starts, [("spawner-ui", None), ("spark-telegram-bot", "primary")])
        self.assertIn("unrelated", pids)

    def test_hosted_rotation_is_rejected_in_favor_of_platform_secret_manager(self) -> None:
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "prod"}, clear=True), self.assertRaisesRegex(
            SystemExit, "hosted platform secret manager"
        ):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

    def test_bridge_secret_cli_rejects_argv_and_redacts_generated_value(self) -> None:
        argv_args = cli.build_parser().parse_args(
            ["secrets", "set", "spark.bridge_api_key", "--value", "unsafe-in-argv"]
        )
        with patch.object(managed, "rotate_managed_bridge_api_key") as rotate, self.assertRaisesRegex(
            SystemExit, "Refusing --value"
        ):
            cli.cmd_secrets_set(argv_args)
        rotate.assert_not_called()

        generated = "generated-bridge-" + "g" * 32
        generate_args = cli.build_parser().parse_args(
            ["secrets", "set", "spark.bridge_api_key", "--generate"]
        )
        with patch.object(cli.py_secrets, "token_urlsafe", return_value=generated), patch.object(
            managed, "rotate_managed_bridge_api_key", return_value="keychain"
        ) as rotate, patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(cli.cmd_secrets_set(generate_args), 0)

        rotate.assert_called_once_with(cli, generated, backend="keychain")
        self.assertNotIn(generated, stdout.getvalue())
        self.assertIn("spark.bridge_api_key", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
