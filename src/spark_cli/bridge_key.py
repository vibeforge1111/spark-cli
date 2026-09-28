from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path


RESERVED_CONTROL_KEYS = {
    "EVENTS_API_KEY",
    "MCP_API_KEY",
    "SPARK_GOVERNOR_HMAC_KEY",
    "SPARK_UI_API_KEY",
    "TELEGRAM_RELAY_SECRET",
}
BRIDGE_API_KEY_ENV = "SPARK_BRIDGE_API_KEY"
BRIDGE_API_KEY_SECRET_ID = "spark.bridge_api_key"
BRIDGE_API_KEY_PENDING_SECRET_ID = "spark.bridge_api_key.pending"
BRIDGE_CONSUMER_MODULES = frozenset({"spawner-ui", "spark-telegram-bot"})


def load_generated_bridge_envs(
    module_config_dir: Path,
    reader: Callable[[Path], dict[str, str]],
) -> dict[str, dict[str, str]]:
    return {
        module_name: reader(module_config_dir / f"{module_name}.env")
        for module_name in ("spawner-ui", "spark-telegram-bot")
    }


def resolve_shared_spawner_bridge_api_key(
    generated_envs: Mapping[str, Mapping[str, str]],
    *,
    explicit: str = "",
    forbidden_secrets: Iterable[str] = (),
    parent_control_values: Iterable[str] = (),
    token_factory: Callable[[], str] | None = None,
) -> str:
    explicit = explicit.strip()
    existing_keys = {
        (env_values.get("SPARK_BRIDGE_API_KEY") or "").strip()
        for env_values in generated_envs.values()
        if (env_values.get("SPARK_BRIDGE_API_KEY") or "").strip()
    }
    if not explicit and len(existing_keys) > 1:
        raise SystemExit(
            "Telegram and Spawner have mismatched SPARK_BRIDGE_API_KEY values. "
            "Rotate them together before restarting Spark."
        )

    generate = token_factory or (lambda: secrets.token_urlsafe(32))
    bridge_key = explicit or next(iter(existing_keys), "") or generate()
    lowered = bridge_key.lower()
    if (
        len(bridge_key) < 24
        or any(char.isspace() for char in bridge_key)
        or lowered in {"changeme", "change-me", "default", "password", "secret", "spark", "test", "token"}
        or any(marker in lowered for marker in ("changeme", "password", "placeholder"))
    ):
        raise SystemExit("SPARK_BRIDGE_API_KEY must be a strong secret of at least 24 characters.")

    reserved_values = {
        str(value).strip()
        for value in (
            *forbidden_secrets,
            *parent_control_values,
            *(
                (env_values.get(key) or "").strip()
                for env_values in generated_envs.values()
                for key in RESERVED_CONTROL_KEYS
            ),
        )
        if str(value).strip()
    }
    if bridge_key in reserved_values:
        raise SystemExit(
            "SPARK_BRIDGE_API_KEY must be different from UI, relay, provider, and other control secrets."
        )
    return bridge_key


def resolve_existing_bridge_api_key(
    generated_envs: Mapping[str, Mapping[str, str]],
    *,
    stored: str = "",
    parent: str = "",
    forbidden_secrets: Iterable[str] = (),
    parent_control_values: Iterable[str] = (),
    token_factory: Callable[[], str] | None = None,
) -> str:
    """Resolve local migration precedence without letting ambient env hide drift."""
    stored = stored.strip()
    parent = parent.strip()
    if stored:
        return resolve_shared_spawner_bridge_api_key(
            generated_envs,
            explicit=stored,
            forbidden_secrets=forbidden_secrets,
            parent_control_values=parent_control_values,
            token_factory=token_factory,
        )
    generated_values = {
        str(values.get(BRIDGE_API_KEY_ENV) or "").strip()
        for values in generated_envs.values()
        if str(values.get(BRIDGE_API_KEY_ENV) or "").strip()
    }
    if generated_values:
        return resolve_shared_spawner_bridge_api_key(
            generated_envs,
            forbidden_secrets=forbidden_secrets,
            parent_control_values=parent_control_values,
            token_factory=token_factory,
        )
    return resolve_shared_spawner_bridge_api_key(
        generated_envs,
        explicit=parent,
        forbidden_secrets=forbidden_secrets,
        parent_control_values=parent_control_values,
        token_factory=token_factory,
    )


def bridge_consumer_process_keys(pids: Mapping[str, object]) -> list[str]:
    """Return bridge consumers in safe stop order: Telegram profiles, then Spawner."""
    telegram = sorted(
        key
        for key in pids
        if key == "spark-telegram-bot" or key.startswith("spark-telegram-bot:")
    )
    spawner = ["spawner-ui"] if "spawner-ui" in pids else []
    return [*telegram, *spawner]


def bridge_consumer_start_order(process_keys: Iterable[str]) -> list[str]:
    """Return safe start order: Spawner, then the exact prior Telegram profiles."""
    keys = set(process_keys)
    result = ["spawner-ui"] if "spawner-ui" in keys else []
    result.extend(sorted(key for key in keys if key.startswith("spark-telegram-bot")))
    return result
