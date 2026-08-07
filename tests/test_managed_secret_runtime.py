from __future__ import annotations

import os
import tempfile
import threading
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

    def test_stop_command_reads_pid_registry_only_after_rotation_lock(self) -> None:
        rotation_lock = threading.Lock()
        entered = threading.Event()
        finished = threading.Event()
        stopped: list[str] = []

        @contextmanager
        def shared_lock(*_args: object, **_kwargs: object):
            with rotation_lock:
                yield

        def load_pids() -> dict[str, Any]:
            entered.set()
            return {"spawner-ui": {"pid": 71}}

        def run_stop() -> None:
            args = cli.build_parser().parse_args(["stop", "spawner-ui"])
            cli.cmd_stop_plain(args)
            finished.set()

        rotation_lock.acquire()
        try:
            with patch.object(cli, "process_log_lock", side_effect=shared_lock), patch.object(
                cli, "load_pids", side_effect=load_pids
            ), patch.object(cli, "resolve_installed_modules", return_value={"spawner-ui": make_module("spawner-ui")}), patch.object(
                cli, "resolve_exact_stop_module_names", return_value=["spawner-ui"]
            ), patch.object(cli, "_stop_tracked_process_key_unlocked", side_effect=lambda key: stopped.append(key) or True):
                worker = threading.Thread(target=run_stop)
                worker.start()
                self.assertFalse(entered.wait(0.05))
                rotation_lock.release()
                self.assertTrue(finished.wait(1.0))
                worker.join(timeout=1.0)
        finally:
            if rotation_lock.locked():
                rotation_lock.release()

        self.assertEqual(stopped, ["spawner-ui"])

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
        index = {key: "keychain" for key in stored}
        live_pids = pids if pids is not None else {}
        running = {int(item.get("pid") or 0) for item in live_pids.values() if isinstance(item, dict)}

        class FakeKeyring:
            @staticmethod
            def get_password(_service: str, account: str) -> str | None:
                return stored.get(account)

            @staticmethod
            def delete_password(_service: str, account: str) -> None:
                stored.pop(account, None)

        def read(path: Path) -> dict[str, str]:
            return dict(generated.get(path.stem, {}))

        def write(path: Path, values: dict[str, str]) -> None:
            writes[path] = dict(values)
            generated[path.stem] = dict(values)

        def fetch(secret_id: str) -> str | None:
            return stored.get(secret_id) if secret_id in index else None

        def store(secret_id: str, value: str, preferred: str = "keychain") -> str:
            stored[secret_id] = value
            index[secret_id] = preferred
            return preferred

        def save_index(values: dict[str, str]) -> None:
            index.clear()
            index.update(values)

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
            list_stored_secrets=lambda: dict(index),
            load_secrets_index=lambda: dict(index),
            save_secrets_index=save_index,
            HAS_KEYRING=True,
            _keyring=FakeKeyring(),
            keychain_account=lambda secret_id: secret_id,
            default_home_uses_legacy_keychain=lambda: False,
            MODULE_CONFIG_DIR=Path("C:/tmp/generated"),
            SECRETS_FILE_PATH=Path("C:/tmp/generated/secrets.local.json"),
            save_json=lambda *_args, **_kwargs: None,
            harden_secret_file=lambda _path: None,
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

    def test_rotation_lock_timeout_never_stages_or_mutates_runtime(self) -> None:
        stored: dict[str, str] = {}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        patches, writes, stopped = self.rotation_patches(stored=stored, generated=generated)

        @contextmanager
        def unavailable_lock(*_args: object, **_kwargs: object):
            raise TimeoutError("busy")
            yield

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "process_log_lock", side_effect=unavailable_lock
        ), self.assertRaises(TimeoutError):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(stored, {})
        self.assertEqual(writes, {})
        self.assertEqual(stopped, [])

    def test_rotation_holds_lock_from_pending_stage_through_cleanup(self) -> None:
        stored = {"spark.bridge_api_key": "old-bridge-" + "o" * 32}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        patches, _writes, _stopped = self.rotation_patches(stored=stored, generated=generated)
        held = False
        events: list[str] = []

        @contextmanager
        def tracked_lock(*_args: object, **_kwargs: object):
            nonlocal held
            held = True
            events.append("lock-enter")
            try:
                yield
            finally:
                events.append("lock-exit")
                held = False

        def store(secret_id: str, value: str, preferred: str = "keychain") -> str:
            self.assertTrue(held)
            events.append("stage" if secret_id.endswith(".pending") else "promote")
            stored[secret_id] = value
            index = cli.load_secrets_index()
            index[secret_id] = preferred
            cli.save_secrets_index(index)
            return preferred

        original_purge = managed._purge_secret_backends

        def purge(runtime: Any, secret_id: str) -> None:
            self.assertTrue(held)
            events.append("cleanup" if secret_id.endswith(".pending") else "purge-stable")
            original_purge(runtime, secret_id)

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "process_log_lock", side_effect=tracked_lock
        ), patch.object(cli, "store_secret", side_effect=store), patch.object(
            managed, "_purge_secret_backends", side_effect=purge
        ):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(events[0], "lock-enter")
        self.assertEqual(events[-1], "lock-exit")
        self.assertLess(events.index("stage"), events.index("promote"))
        self.assertLess(events.index("promote"), len(events) - 1)
        self.assertGreaterEqual(events.count("cleanup"), 2)

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

    def test_rotation_rejects_named_profile_and_generated_provider_collisions(self) -> None:
        for filename, key in (
            ("spark-telegram-bot.primary", "TELEGRAM_RELAY_SECRET"),
            ("spark-intelligence-builder", "OPENAI_API_KEY"),
            ("spark-database", "POSTGRES_PASSWORD"),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp_dir:
                candidate = "collision-" + "c" * 32
                (Path(tmp_dir) / f"{filename}.env").touch()
                stored: dict[str, str] = {}
                generated = {
                    "spawner-ui": {},
                    "spark-telegram-bot": {},
                    filename: {key: candidate},
                }
                patches, writes, stopped = self.rotation_patches(stored=stored, generated=generated)
                profile_paths = [Path(tmp_dir) / f"{filename}.env"] if "primary" in filename else []
                with patch.dict(os.environ, {}, clear=True), patches, patch.object(
                    cli, "MODULE_CONFIG_DIR", Path(tmp_dir)
                ), patch.object(cli, "telegram_generated_env_paths", return_value=profile_paths), self.assertRaisesRegex(
                    SystemExit, "must be different"
                ):
                    managed.rotate_managed_bridge_api_key(cli, candidate, backend="keychain")

                self.assertNotIn("spark.bridge_api_key.pending", stored)
                self.assertEqual(writes, {})
                self.assertEqual(stopped, [])

    def test_rotation_rejects_manifest_declared_nonstandard_secret_env_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            candidate = "collision-" + "c" * 32
            secret_module = make_module("community-module", secrets=["community.access"])
            secret_module.manifest["secrets"]["community_access"]["env_var"] = "SERVICE_ACCESS"
            modules = {
                "spawner-ui": make_module("spawner-ui"),
                "spark-telegram-bot": make_module("spark-telegram-bot"),
                "community-module": secret_module,
            }
            generated = {
                "spawner-ui": {},
                "spark-telegram-bot": {},
                "community-module": {"SERVICE_ACCESS": candidate},
            }
            (Path(tmp_dir) / "community-module.env").touch()
            stored: dict[str, str] = {}
            patches, writes, stopped = self.rotation_patches(stored=stored, generated=generated)
            with patch.dict(os.environ, {}, clear=True), patches, patch.object(
                cli, "MODULE_CONFIG_DIR", Path(tmp_dir)
            ), patch.object(cli, "resolve_installed_modules", return_value=modules), self.assertRaisesRegex(
                SystemExit, "must be different"
            ):
                managed.rotate_managed_bridge_api_key(cli, candidate, backend="keychain")

            self.assertNotIn(managed.BRIDGE_API_KEY_PENDING_SECRET_ID, stored)
            self.assertEqual(writes, {})
            self.assertEqual(stopped, [])

    def test_stable_keychain_read_failure_aborts_before_pending_stage(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {managed.BRIDGE_API_KEY_SECRET_ID: old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        patches, writes, stopped = self.rotation_patches(stored=stored, generated=generated)

        class StableReadFailure:
            @staticmethod
            def get_password(_service: str, account: str) -> str | None:
                if account == managed.BRIDGE_API_KEY_SECRET_ID:
                    raise RuntimeError("unavailable")
                return stored.get(account)

            @staticmethod
            def delete_password(_service: str, account: str) -> None:
                stored.pop(account, None)

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "_keyring", StableReadFailure()
        ), self.assertRaisesRegex(SystemExit, "could not be read"):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(stored, {managed.BRIDGE_API_KEY_SECRET_ID: old})
        self.assertEqual(writes, {})
        self.assertEqual(stopped, [])

    def test_backend_replacement_and_rollback_leave_one_exact_copy(self) -> None:
        for old_backend, new_backend in (("file", "keychain"), ("keychain", "file")):
            with self.subTest(old_backend=old_backend, new_backend=new_backend):
                self._assert_backend_replacement_and_rollback(old_backend, new_backend)

    def _assert_backend_replacement_and_rollback(self, old_backend: str, new_backend: str) -> None:
        secret_id = managed.BRIDGE_API_KEY_SECRET_ID
        index = {secret_id: old_backend}
        keychain: dict[str, str] = {}
        file_values: dict[str, str] = {}
        target = keychain if old_backend == "keychain" else file_values
        target[secret_id] = "old-secret"

        class FakeKeyring:
            def get_password(self, _service: str, account: str) -> str | None:
                return keychain.get(account)

            def delete_password(self, _service: str, account: str) -> None:
                keychain.pop(account, None)

        def load_json(_path: Path, default: Any) -> dict[str, str]:
            return dict(file_values) if file_values else dict(default)

        def save_json(_path: Path, values: dict[str, str]) -> None:
            file_values.clear()
            file_values.update(values)

        def save_index(values: dict[str, str]) -> None:
            index.clear()
            index.update(values)

        def fetch(requested: str) -> str | None:
            return (keychain if index.get(requested) == "keychain" else file_values).get(requested)

        def store(requested: str, value: str, preferred: str = "keychain") -> str:
            (keychain if preferred == "keychain" else file_values)[requested] = value
            index[requested] = preferred
            return preferred

        with patch.multiple(
            cli,
            HAS_KEYRING=True,
            _keyring=FakeKeyring(),
            KEYCHAIN_SERVICE="test",
            SECRETS_FILE_PATH=Path("C:/tmp/secrets.json"),
            keychain_account=lambda requested: requested,
            default_home_uses_legacy_keychain=lambda: False,
            load_json=load_json,
            save_json=save_json,
            harden_secret_file=lambda _path: None,
            dpapi_unprotect=lambda value: value,
            load_secrets_index=lambda: dict(index),
            save_secrets_index=save_index,
            fetch_secret=fetch,
            store_secret=store,
        ):
            actual, prior = managed._replace_secret_backend(cli, secret_id, "new-secret", new_backend)
            self.assertEqual((actual, prior), (new_backend, old_backend))
            self.assertEqual(index[secret_id], new_backend)
            self.assertEqual((keychain if new_backend == "keychain" else file_values)[secret_id], "new-secret")
            self.assertNotIn(secret_id, file_values if new_backend == "keychain" else keychain)
            managed._restore_bridge_generation(
                cli,
                old_stored="old-secret",
                old_backend=old_backend,
                legacy_snapshot=[],
            )

        self.assertEqual(index[secret_id], old_backend)
        self.assertEqual(target[secret_id], "old-secret")
        self.assertNotIn(secret_id, file_values if old_backend == "keychain" else keychain)

    def test_backend_delete_failure_aborts_and_transient_cleanup_restores_old_copy(self) -> None:
        secret_id = managed.BRIDGE_API_KEY_SECRET_ID
        index = {secret_id: "keychain"}
        keychain = {secret_id: "old-secret"}
        file_values: dict[str, str] = {}
        delete_calls = 0

        class FlakyKeyring:
            def get_password(self, _service: str, account: str) -> str | None:
                return keychain.get(account)

            def delete_password(self, _service: str, account: str) -> None:
                nonlocal delete_calls
                delete_calls += 1
                if delete_calls == 1:
                    raise RuntimeError("backend unavailable")
                keychain.pop(account, None)

        def load_json(_path: Path, default: Any) -> dict[str, str]:
            return dict(file_values) if file_values else dict(default)

        def save_json(_path: Path, values: dict[str, str]) -> None:
            file_values.clear()
            file_values.update(values)

        def save_index(values: dict[str, str]) -> None:
            index.clear()
            index.update(values)

        def fetch(requested: str) -> str | None:
            return (keychain if index.get(requested) == "keychain" else file_values).get(requested)

        def store(requested: str, value: str, preferred: str = "keychain") -> str:
            (keychain if preferred == "keychain" else file_values)[requested] = value
            index[requested] = preferred
            return preferred

        with patch.multiple(
            cli,
            HAS_KEYRING=True,
            _keyring=FlakyKeyring(),
            KEYCHAIN_SERVICE="test",
            SECRETS_FILE_PATH=Path("C:/tmp/secrets.json"),
            keychain_account=lambda requested: requested,
            default_home_uses_legacy_keychain=lambda: False,
            load_json=load_json,
            save_json=save_json,
            harden_secret_file=lambda _path: None,
            dpapi_unprotect=lambda value: value,
            load_secrets_index=lambda: dict(index),
            save_secrets_index=save_index,
            fetch_secret=fetch,
            store_secret=store,
        ), self.assertRaisesRegex(SystemExit, "prior secret backend"):
            try:
                managed._replace_secret_backend(cli, secret_id, "new-secret", "file")
            except SystemExit:
                managed._restore_bridge_generation(
                    cli,
                    old_stored="old-secret",
                    old_backend="keychain",
                    legacy_snapshot=[],
                )
                raise

        self.assertEqual(index, {secret_id: "keychain"})
        self.assertEqual(keychain, {secret_id: "old-secret"})
        self.assertNotIn(secret_id, file_values)

    def test_file_backend_cleanup_does_not_require_a_system_keyring(self) -> None:
        secret_id = managed.BRIDGE_API_KEY_PENDING_SECRET_ID
        index = {secret_id: "file"}
        file_values = {secret_id: "staged-secret"}

        def save_json(_path: Path, values: dict[str, str]) -> None:
            file_values.clear()
            file_values.update(values)

        def save_index(values: dict[str, str]) -> None:
            index.clear()
            index.update(values)

        with patch.multiple(
            cli,
            HAS_KEYRING=False,
            SECRETS_FILE_PATH=Path("C:/tmp/secrets.json"),
            load_json=lambda _path, _default: dict(file_values),
            save_json=save_json,
            harden_secret_file=lambda _path: None,
            dpapi_unprotect=lambda value: value,
            load_secrets_index=lambda: dict(index),
            save_secrets_index=save_index,
        ):
            managed._purge_secret_backends(cli, secret_id)

        self.assertEqual(index, {})
        self.assertEqual(file_values, {})

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

    def test_keyboard_interrupt_during_success_cleanup_rolls_back_inside_lock(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {"spark.bridge_api_key": old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        patches, _writes, _stopped = self.rotation_patches(
            stored=stored,
            generated=generated,
            pids={"spawner-ui": {"pid": 22}},
        )
        original_cleanup = managed._delete_pending_or_raise
        cleanup_calls = 0
        held = False

        @contextmanager
        def tracked_lock(*_args: object, **_kwargs: object):
            nonlocal held
            held = True
            try:
                yield
            finally:
                held = False

        def cleanup(runtime: Any) -> None:
            nonlocal cleanup_calls
            self.assertTrue(held)
            cleanup_calls += 1
            if cleanup_calls == 1:
                raise KeyboardInterrupt
            original_cleanup(runtime)

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "process_log_lock", side_effect=tracked_lock
        ), patch.object(managed, "_delete_pending_or_raise", side_effect=cleanup), self.assertRaises(KeyboardInterrupt):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(cleanup_calls, 2)
        self.assertEqual(stored[managed.BRIDGE_API_KEY_SECRET_ID], old)
        self.assertNotIn(managed.BRIDGE_API_KEY_PENDING_SECRET_ID, stored)

    def test_cleanup_failure_after_restore_leaves_bridge_consumers_stopped(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {managed.BRIDGE_API_KEY_SECRET_ID: old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        pids: dict[str, Any] = {"spawner-ui": {"pid": 22}}
        patches, _writes, _stopped = self.rotation_patches(
            stored=stored,
            generated=generated,
            pids=pids,
        )
        next_pid = 80

        def start(module: Module, *, profile: str | None = None, **_kwargs: object) -> bool:
            nonlocal next_pid
            key = cli.module_process_key(module.name, profile)
            next_pid += 1
            pids[key] = {"pid": next_pid}
            return True

        def stop(key: str, _pid: int | None = None) -> bool:
            pids.pop(key, None)
            return True

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "pid_is_running", side_effect=lambda pid: any(item.get("pid") == pid for item in pids.values())
        ), patch.object(cli, "stop_module", side_effect=stop), patch.object(
            cli, "_stop_tracked_process_key_unlocked", side_effect=stop
        ), patch.object(cli, "_start_module_unlocked", side_effect=start), patch.object(
            managed, "_delete_pending_or_raise", side_effect=SystemExit("cleanup unavailable")
        ), self.assertRaisesRegex(SystemExit, "bridge consumers remain stopped"):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(managed.bridge_consumer_process_keys(pids), [])

    def test_pre_stop_failure_with_cleanup_failure_reports_original_set_unchanged(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {managed.BRIDGE_API_KEY_SECRET_ID: old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        pids: dict[str, Any] = {"spawner-ui": {"pid": 22}}
        patches, _writes, stopped = self.rotation_patches(stored=stored, generated=generated, pids=pids)

        @contextmanager
        def unavailable_pid_lock(*_args: object, **_kwargs: object):
            raise TimeoutError("busy")
            yield

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "pid_file_lock", side_effect=unavailable_pid_lock
        ), patch.object(
            managed, "_delete_pending_or_raise", side_effect=SystemExit("cleanup unavailable")
        ), self.assertRaisesRegex(SystemExit, "original consumer set remains unchanged"):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(pids, {"spawner-ui": {"pid": 22}})
        self.assertEqual(stopped, [])

    def test_partial_rollback_restart_is_stopped_before_failure_returns(self) -> None:
        old = "old-bridge-" + "o" * 32
        stored = {managed.BRIDGE_API_KEY_SECRET_ID: old}
        generated = {"spawner-ui": {}, "spark-telegram-bot": {}}
        pids: dict[str, Any] = {
            "spawner-ui": {"pid": 22},
            "spark-telegram-bot:primary": {"pid": 23},
        }
        patches, _writes, _stopped = self.rotation_patches(stored=stored, generated=generated, pids=pids)
        outcomes = iter((False, True, False))
        next_pid = 90

        def start(module: Module, *, profile: str | None = None, **_kwargs: object) -> bool:
            nonlocal next_pid
            outcome = next(outcomes)
            if outcome:
                next_pid += 1
                pids[cli.module_process_key(module.name, profile)] = {"pid": next_pid}
            return outcome

        def stop(key: str, _pid: int | None = None) -> bool:
            pids.pop(key, None)
            return True

        with patch.dict(os.environ, {}, clear=True), patches, patch.object(
            cli, "pid_is_running", side_effect=lambda pid: any(item.get("pid") == pid for item in pids.values())
        ), patch.object(cli, "stop_module", side_effect=stop), patch.object(
            cli, "_stop_tracked_process_key_unlocked", side_effect=stop
        ), patch.object(cli, "_start_module_unlocked", side_effect=start), self.assertRaisesRegex(
            SystemExit, "bridge consumers remain stopped"
        ):
            managed.rotate_managed_bridge_api_key(cli, "new-bridge-" + "n" * 32, backend="keychain")

        self.assertEqual(managed.bridge_consumer_process_keys(pids), [])

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
