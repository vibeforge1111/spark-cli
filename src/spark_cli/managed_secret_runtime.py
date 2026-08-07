from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .bridge_key import (
    BRIDGE_API_KEY_ENV,
    BRIDGE_API_KEY_PENDING_SECRET_ID,
    BRIDGE_API_KEY_SECRET_ID,
    BRIDGE_CONSUMER_MODULES,
    RESERVED_CONTROL_KEYS,
    bridge_consumer_process_keys,
    bridge_consumer_start_order,
    load_generated_bridge_envs,
    resolve_existing_bridge_api_key,
    resolve_shared_spawner_bridge_api_key,
)

VOICE_MODULE_NAME = "spark-voice-comms"
VOICE_OPENAI_SECRET_ID = "voice.openai.api_key"
VOICE_OPENAI_SECRET_ENV = "VOICE_OPENAI_API_KEY"
VOICE_ELEVENLABS_SECRET_ID = "voice.elevenlabs.api_key"
VOICE_ELEVENLABS_SECRET_ENV = "ELEVENLABS_API_KEY"
TELEGRAM_VOICE_TTS_SECRET_REF_ENV = "SPARK_TELEGRAM_VOICE_TTS_SECRET_ENV_REF"


def ensure_managed_bridge_api_key(runtime: Any, secret_values: dict[str, str]) -> str:
    """Migrate or generate the shared local bridge key into managed storage."""
    generated_envs = load_generated_bridge_envs(runtime.MODULE_CONFIG_DIR, runtime.read_generated_env)
    stored = (runtime.fetch_secret(BRIDGE_API_KEY_SECRET_ID) or "").strip()
    parent = (os.environ.get(BRIDGE_API_KEY_ENV) or "").strip()
    if hosted_bridge_authority() and parent:
        return resolve_shared_spawner_bridge_api_key(
            generated_envs,
            explicit=parent,
            forbidden_secrets=secret_values.values(),
            parent_control_values=((os.environ.get(key) or "").strip() for key in RESERVED_CONTROL_KEYS),
        )
    value = resolve_existing_bridge_api_key(
        generated_envs,
        stored=stored,
        parent=parent,
        forbidden_secrets=secret_values.values(),
        parent_control_values=((os.environ.get(key) or "").strip() for key in RESERVED_CONTROL_KEYS),
    )
    if stored != value:
        runtime.store_secret(BRIDGE_API_KEY_SECRET_ID, value, preferred="keychain")
    runtime.remember_setup_secret_key(BRIDGE_API_KEY_SECRET_ID)
    return value


def add_setup_bridge_report(
    runtime: Any,
    modules: dict[str, Any],
    secret_values: dict[str, str],
    keychain_report: dict[str, str],
) -> None:
    if not {"spawner-ui", "spark-telegram-bot"}.issubset(modules):
        return
    ensure_managed_bridge_api_key(runtime, secret_values)
    if hosted_bridge_authority():
        return
    backend = runtime.list_stored_secrets().get(BRIDGE_API_KEY_SECRET_ID)
    if backend:
        keychain_report[BRIDGE_API_KEY_SECRET_ID] = backend


def hosted_bridge_authority() -> bool:
    return bool(os.environ.get("SPARK_LIVE_CONTAINER") or os.environ.get("RAILWAY_ENVIRONMENT"))


def setup_bridge_explicit(runtime: Any) -> str:
    parent = (os.environ.get(BRIDGE_API_KEY_ENV) or "").strip()
    if hosted_bridge_authority() and parent:
        return parent
    return (runtime.fetch_secret(BRIDGE_API_KEY_SECRET_ID) or "").strip() or parent


def control_surface_bridge_explicit(runtime: Any) -> str:
    if hosted_bridge_authority():
        return (os.environ.get(BRIDGE_API_KEY_ENV) or "").strip()
    return (runtime.fetch_secret(BRIDGE_API_KEY_SECRET_ID) or "").strip()


def strip_managed_runtime_secret_values(env_values: dict[str, str]) -> dict[str, str]:
    blocked = {BRIDGE_API_KEY_ENV, VOICE_OPENAI_SECRET_ENV, VOICE_ELEVENLABS_SECRET_ENV}
    return {key: value for key, value in env_values.items() if key not in blocked}


def find_profile_voice_secret(
    requirement: dict[str, Any],
    profile_paths: Iterable[Path],
    reader: Any,
) -> str | None:
    env_var = str(requirement.get("env_var") or "")
    if env_var not in {VOICE_OPENAI_SECRET_ENV, VOICE_ELEVENLABS_SECRET_ENV}:
        return None
    for path in profile_paths:
        value = reader(path).get(env_var)
        if value:
            return str(value)
    return None


def fetch_generated_secret_value(runtime: Any, requirement: dict[str, Any]) -> str | None:
    env_var = requirement.get("env_var")
    if not env_var:
        return None
    for module_name in requirement.get("modules", []):
        value = runtime.read_generated_env(runtime.MODULE_CONFIG_DIR / f"{module_name}.env").get(str(env_var))
        if value:
            return str(value)
    return find_profile_voice_secret(
        requirement,
        runtime.telegram_generated_env_paths(runtime.load_json(runtime.CONFIG_PATH, {})),
        runtime.read_generated_env,
    )


def apply_managed_secret_runtime_env(
    runtime: Any,
    module: Any,
    profile: str | None,
    env: dict[str, str],
) -> dict[str, str]:
    """Overlay only the managed secrets authorized for this module instance."""
    generated_env = runtime.read_generated_env(runtime.generated_module_env_path(module))
    legacy_bridge_declared = BRIDGE_API_KEY_ENV in generated_env
    legacy_bridge_values = {str(generated_env.get(BRIDGE_API_KEY_ENV) or "").strip()} - {""}
    if module.name in BRIDGE_CONSUMER_MODULES:
        for values in load_generated_bridge_envs(runtime.MODULE_CONFIG_DIR, runtime.read_generated_env).values():
            legacy_bridge_declared = legacy_bridge_declared or BRIDGE_API_KEY_ENV in values
            legacy_value = str(values.get(BRIDGE_API_KEY_ENV) or "").strip()
            if legacy_value:
                legacy_bridge_values.add(legacy_value)
    env.update(runtime.strip_reserved_workspace_env(strip_managed_runtime_secret_values(generated_env)))

    named_profile = module.name == "spark-telegram-bot" and not runtime.telegram_profile_is_default(profile)
    if named_profile:
        profile_env = runtime.read_generated_env(runtime.generated_module_env_path(module, profile))
        legacy_bridge_declared = legacy_bridge_declared or BRIDGE_API_KEY_ENV in profile_env
        profile_bridge_value = str(profile_env.get(BRIDGE_API_KEY_ENV) or "").strip()
        if profile_bridge_value:
            legacy_bridge_values.add(profile_bridge_value)
        env.update(runtime.strip_reserved_workspace_env(strip_managed_runtime_secret_values(profile_env)))

    env.update(runtime.keychain_env_for_module(module))
    if module.name in BRIDGE_CONSUMER_MODULES:
        _apply_bridge_runtime_secret(runtime, env, legacy_bridge_values, legacy_bridge_declared)
    if module.name == "spark-telegram-bot":
        profile_secrets = runtime.keychain_env_for_telegram_profile(profile)
        if named_profile:
            env.pop("BOT_TOKEN", None)
            env.pop("TELEGRAM_BOT_TOKEN", None)
        env.update(profile_secrets)
        _apply_selected_voice_secret(runtime, env)
    return env


def _apply_bridge_runtime_secret(
    runtime: Any,
    env: dict[str, str],
    legacy_values: set[str],
    legacy_declared: bool,
) -> None:
    hosted = (os.environ.get(BRIDGE_API_KEY_ENV) or "").strip() if hosted_bridge_authority() else ""
    managed = (runtime.fetch_secret(BRIDGE_API_KEY_SECRET_ID) or "").strip()
    if hosted:
        env[BRIDGE_API_KEY_ENV] = resolve_shared_spawner_bridge_api_key({}, explicit=hosted)
    elif managed:
        env[BRIDGE_API_KEY_ENV] = resolve_shared_spawner_bridge_api_key({}, explicit=managed)
    elif len(legacy_values) > 1:
        raise SystemExit(
            "Telegram and Spawner have mismatched legacy SPARK_BRIDGE_API_KEY values. "
            "Rotate them together with `spark secrets set spark.bridge_api_key --generate`."
        )
    elif legacy_values:
        env[BRIDGE_API_KEY_ENV] = next(iter(legacy_values))
    elif not legacy_declared:
        parent = (os.environ.get(BRIDGE_API_KEY_ENV) or "").strip()
        if parent:
            env[BRIDGE_API_KEY_ENV] = resolve_shared_spawner_bridge_api_key({}, explicit=parent)


def _apply_selected_voice_secret(runtime: Any, env: dict[str, str]) -> None:
    secret_id = {
        VOICE_OPENAI_SECRET_ENV: VOICE_OPENAI_SECRET_ID,
        VOICE_ELEVENLABS_SECRET_ENV: VOICE_ELEVENLABS_SECRET_ID,
    }.get(str(env.get(TELEGRAM_VOICE_TTS_SECRET_REF_ENV) or "").strip())
    if not secret_id:
        return
    value = runtime.fetch_secret(secret_id)
    if value:
        env[
            VOICE_OPENAI_SECRET_ENV if secret_id == VOICE_OPENAI_SECRET_ID else VOICE_ELEVENLABS_SECRET_ENV
        ] = value


def configure_voice_owner_envs(
    builder_env: dict[str, str],
    gateway_env: dict[str, str],
    voice_root: Path,
    secret_values: dict[str, str],
) -> None:
    root = str(voice_root)
    builder_env["SPARK_VOICE_COMMS_ROOT"] = root
    gateway_env["SPARK_VOICE_COMMS_ROOT"] = root
    config: dict[str, str] = {}
    if secret_values.get(VOICE_ELEVENLABS_SECRET_ID):
        builder_env[VOICE_ELEVENLABS_SECRET_ENV] = secret_values[VOICE_ELEVENLABS_SECRET_ID]
        config = {
            "SPARK_TELEGRAM_VOICE_TTS_PROVIDER": "elevenlabs",
            TELEGRAM_VOICE_TTS_SECRET_REF_ENV: VOICE_ELEVENLABS_SECRET_ENV,
            "SPARK_TELEGRAM_VOICE_TTS_ELEVENLABS_MODEL_ID": "eleven_multilingual_v2",
        }
    elif secret_values.get(VOICE_OPENAI_SECRET_ID):
        builder_env[VOICE_OPENAI_SECRET_ENV] = secret_values[VOICE_OPENAI_SECRET_ID]
        config = {
            "SPARK_TELEGRAM_VOICE_TTS_PROVIDER": "openai-realtime",
            TELEGRAM_VOICE_TTS_SECRET_REF_ENV: VOICE_OPENAI_SECRET_ENV,
        }
    builder_env.update(config)
    gateway_env.update(config)


def ready_check_headers(runtime: Any, ready_check: str, *, module_name: str | None) -> dict[str, str]:
    if module_name != "spawner-ui" or not ready_check.startswith(("http://", "https://")):
        return {}
    parsed = runtime.urllib.parse.urlparse(ready_check)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return {}
    key = os.environ.get("SPARK_UI_API_KEY") or setup_bridge_explicit(runtime)
    return {"x-spawner-ui-key": key, "x-api-key": key} if key else {}


def prepare_module_launch(
    runtime: Any,
    module: Any,
    command: str,
    profile: str | None,
) -> tuple[dict[str, str], list[str], str, int, dict[str, Any]]:
    env = runtime.module_runtime_env(module, profile)
    argv = runtime.module_runtime_command_argv(module, command, module.path, env)
    ready_check = runtime.module_runtime_ready_check(module, env)
    relay_port = 0
    if module.name == "spark-telegram-bot":
        try:
            relay_port = int((env.get("TELEGRAM_RELAY_PORT") or "").strip() or "0")
        except ValueError:
            relay_port = 0
    popen_kwargs: dict[str, Any] = {
        "cwd": str(module.path),
        "shell": False,
        "stdin": runtime.subprocess.DEVNULL,
        "stderr": runtime.subprocess.STDOUT,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = runtime.windows_service_creationflags()
    else:
        popen_kwargs["start_new_session"] = True
    return env, argv, ready_check, relay_port, popen_kwargs


def bridge_process_profile(runtime: Any, process_key: str) -> str | None:
    if process_key == "spark-telegram-bot":
        return runtime.DEFAULT_TELEGRAM_PROFILE
    prefix = "spark-telegram-bot:"
    if process_key.startswith(prefix):
        return runtime.normalize_telegram_profile(process_key[len(prefix) :])
    return None


def start_bridge_consumer_snapshot(
    runtime: Any,
    process_keys: Iterable[str],
    installed_modules: dict[str, Any],
) -> bool:
    for process_key in bridge_consumer_start_order(process_keys):
        if process_key == "spawner-ui":
            module, profile = installed_modules.get("spawner-ui"), None
        else:
            module = installed_modules.get("spark-telegram-bot")
            profile = bridge_process_profile(runtime, process_key)
        if module is None or not runtime._start_module_unlocked(module, profile=profile):
            return False
    return True


def stop_live_bridge_consumers(runtime: Any) -> None:
    with runtime.pid_file_lock():
        process_keys = bridge_consumer_process_keys(runtime.load_pids())
    for process_key in process_keys:
        runtime._stop_tracked_process_key_unlocked(process_key)


def legacy_bridge_key_file_snapshot(
    runtime: Any,
    installed_modules: dict[str, Any],
) -> list[tuple[Path, Any | None, dict[str, str]]]:
    paths: list[tuple[Path, Any | None]] = []
    for module_name in sorted(BRIDGE_CONSUMER_MODULES):
        module = installed_modules.get(module_name)
        if module is not None:
            paths.append((runtime.generated_module_env_path(module), module))
    setup_state = runtime.load_json(runtime.CONFIG_PATH, {})
    for path in runtime.telegram_generated_env_paths(setup_state):
        if all(path != existing for existing, _module in paths):
            paths.append((path, None))
    return [
        (path, module, values)
        for path, module in paths
        if BRIDGE_API_KEY_ENV in (values := runtime.read_generated_env(path))
    ]


def scrub_legacy_bridge_key_files(runtime: Any, installed_modules: dict[str, Any]) -> None:
    for path, module, original in legacy_bridge_key_file_snapshot(runtime, installed_modules):
        values = dict(original)
        values.pop(BRIDGE_API_KEY_ENV)
        runtime.write_generated_env(path, values)
        if module is not None:
            env_path = runtime.module_env_path(module)
            if env_path is not None:
                runtime.update_env_file(env_path, values)


def restore_legacy_bridge_key_files(runtime: Any, snapshot: list[tuple[Path, Any | None, dict[str, str]]]) -> None:
    for path, module, values in snapshot:
        runtime.write_generated_env(path, values)
        if module is not None:
            env_path = runtime.module_env_path(module)
            if env_path is not None:
                runtime.update_env_file(env_path, values)


def _rotation_forbidden_values(runtime: Any, generated_envs: dict[str, dict[str, str]]) -> list[str]:
    values = [
        str(env.get(key) or "").strip()
        for env in generated_envs.values()
        for key in ({BRIDGE_API_KEY_ENV} | RESERVED_CONTROL_KEYS)
    ]
    values.extend(
        (os.environ.get(key) or "").strip()
        for key in ({BRIDGE_API_KEY_ENV} | RESERVED_CONTROL_KEYS | set(runtime.STATIC_PROVIDER_ENV_BLOCKLIST))
    )
    for secret_id in runtime.list_stored_secrets():
        if secret_id not in {BRIDGE_API_KEY_SECRET_ID, BRIDGE_API_KEY_PENDING_SECRET_ID}:
            values.append((runtime.fetch_secret(secret_id) or "").strip())
    return [value for value in values if value]


def _restore_bridge_generation(
    runtime: Any,
    *,
    old_stored: str,
    backend: str,
    legacy_snapshot: list[tuple[Path, Any | None, dict[str, str]]],
) -> None:
    if old_stored:
        runtime.store_secret(BRIDGE_API_KEY_SECRET_ID, old_stored, preferred=backend)
    else:
        runtime.delete_secret(BRIDGE_API_KEY_SECRET_ID)
    restore_legacy_bridge_key_files(runtime, legacy_snapshot)


def _delete_pending_or_raise(runtime: Any) -> None:
    runtime.delete_secret(BRIDGE_API_KEY_PENDING_SECRET_ID)
    if runtime.fetch_secret(BRIDGE_API_KEY_PENDING_SECRET_ID) is not None:
        raise SystemExit("Bridge key rotation stopped because the staged secret could not be removed.")


def rotate_managed_bridge_api_key(runtime: Any, new_value: str, *, backend: str) -> str:
    if hosted_bridge_authority():
        raise SystemExit("Rotate SPARK_BRIDGE_API_KEY through the hosted platform secret manager.")
    installed = runtime.resolve_installed_modules()
    missing = sorted(BRIDGE_CONSUMER_MODULES - set(installed))
    if missing:
        raise SystemExit(
            "Install the Telegram starter stack before rotating the local bridge key: " + ", ".join(missing)
        )
    generated_envs = load_generated_bridge_envs(runtime.MODULE_CONFIG_DIR, runtime.read_generated_env)
    old_stored = (runtime.fetch_secret(BRIDGE_API_KEY_SECRET_ID) or "").strip()
    old_values = {
        str(env.get(BRIDGE_API_KEY_ENV) or "").strip() for env in generated_envs.values()
    } - {""}
    if old_stored:
        old_values.add(old_stored)
    candidate = resolve_shared_spawner_bridge_api_key(
        {},
        explicit=new_value,
        forbidden_secrets=(*old_values, *_rotation_forbidden_values(runtime, generated_envs)),
    )

    runtime.store_secret(BRIDGE_API_KEY_PENDING_SECRET_ID, candidate, preferred=backend)
    if runtime.fetch_secret(BRIDGE_API_KEY_PENDING_SECRET_ID) != candidate:
        _delete_pending_or_raise(runtime)
        raise SystemExit("Bridge key rotation stopped because staged secret verification failed.")

    snapshot: list[str] = []
    legacy_snapshot = legacy_bridge_key_file_snapshot(runtime, installed)
    promoted = False
    promotion_attempted = False
    promoted_backend = backend
    failure: BaseException | None = None
    with runtime.process_log_lock(runtime.BRIDGE_ROTATION_LOCK_PATH, timeout_seconds=30.0):
        try:
            with runtime.pid_file_lock(timeout_seconds=30.0):
                pids = runtime.load_pids()
                snapshot = [
                    key
                    for key in bridge_consumer_process_keys(pids)
                    if isinstance(pids.get(key), dict)
                    and int(pids[key].get("pid") or 0)
                    and runtime.pid_is_running(int(pids[key].get("pid") or 0))
                ]
                for process_key in snapshot:
                    record = pids.get(process_key, {})
                    pid = int(record.get("pid") or 0) if isinstance(record, dict) else 0
                    if pid:
                        runtime.stop_module(process_key, pid)
                    if pid and runtime.pid_is_running(pid):
                        raise SystemExit(
                            f"Bridge key rotation stopped because {process_key} did not exit cleanly."
                        )
                    pids.pop(process_key, None)
                runtime.save_pids(pids)
                promotion_attempted = True
                promoted_backend = runtime.store_secret(BRIDGE_API_KEY_SECRET_ID, candidate, preferred=backend)
                if runtime.fetch_secret(BRIDGE_API_KEY_SECRET_ID) != candidate:
                    raise SystemExit("Bridge key rotation stopped because promoted secret verification failed.")
                promoted = True
                scrub_legacy_bridge_key_files(runtime, installed)
            if not start_bridge_consumer_snapshot(runtime, snapshot, installed):
                raise SystemExit("A bridge consumer did not become healthy with the new key.")
        except (SystemExit, KeyboardInterrupt, Exception) as exc:  # noqa: BLE001 - rollback every operational failure
            failure = exc
            stop_live_bridge_consumers(runtime)
            if promoted or promotion_attempted:
                _restore_bridge_generation(
                    runtime,
                    old_stored=old_stored,
                    backend=backend,
                    legacy_snapshot=legacy_snapshot,
                )
            rollback_started = start_bridge_consumer_snapshot(runtime, snapshot, installed)
            _delete_pending_or_raise(runtime)
            if not rollback_started:
                raise SystemExit(
                    "Bridge key rotation failed and the prior consumer set could not be fully restored."
                ) from None

    if failure is not None:
        if isinstance(failure, (SystemExit, KeyboardInterrupt)):
            raise failure
        raise SystemExit("Bridge key rotation failed and the prior generation was restored.") from None
    _delete_pending_or_raise(runtime)
    runtime.remember_setup_secret_key(BRIDGE_API_KEY_SECRET_ID)
    return promoted_backend
