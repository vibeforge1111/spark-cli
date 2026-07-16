from __future__ import annotations

from collections.abc import Callable, Mapping, Set
from typing import Any


ProviderSpecs = Mapping[str, Mapping[str, str]]
DEFAULT_PROVIDER_KEYS = frozenset(
    {
        "LLM_PROVIDER",
        "SPARK_LLM_PROVIDER",
        "SPARK_CHAT_LLM_PROVIDER",
        "SPARK_BUILDER_LLM_PROVIDER",
        "SPARK_MEMORY_LLM_PROVIDER",
        "SPARK_MISSION_LLM_PROVIDER",
    }
)
RUNTIME_PROVIDER_KEYS = {
    "spark-telegram-bot": DEFAULT_PROVIDER_KEYS,
    "spawner-ui": frozenset(
        {
            "SPARK_MISSION_LLM_PROVIDER",
            "SPARK_MISSION_LLM_BOT_PROVIDER",
            "DEFAULT_MISSION_PROVIDER",
            "SPARK_BOT_DEFAULT_PROVIDER",
            "BOT_DEFAULT_PROVIDER",
        }
    ),
}


def provider_secret_env_names(specs: ProviderSpecs) -> set[str]:
    return {
        str(spec["api_key_env"]).upper()
        for spec in specs.values()
        if spec.get("api_key_env")
    }


def strip_provider_secret_values(env: Mapping[str, str], specs: ProviderSpecs) -> dict[str, str]:
    blocked = provider_secret_env_names(specs)
    return {key: value for key, value in env.items() if key.upper() not in blocked}


def store_provider_secrets(
    secret_values: Mapping[str, str],
    specs: ProviderSpecs,
    store_secret: Callable[..., str],
    *,
    skip: set[str] | None = None,
) -> dict[str, str]:
    report: dict[str, str] = {}
    seen = set(skip or ())
    for spec in specs.values():
        secret_id = str(spec.get("api_key_secret") or "")
        if not secret_id or secret_id in seen:
            continue
        value = secret_values.get(secret_id)
        if not value:
            continue
        report[secret_id] = store_secret(secret_id, value, preferred="keychain")
        seen.add(secret_id)
    return report


def selected_provider_names(env: Mapping[str, str], keys: Set[str] | None = None) -> set[str]:
    keys = DEFAULT_PROVIDER_KEYS if keys is None else keys
    return {str(env.get(key) or "").strip().lower() for key in keys if env.get(key)}


def resolve_provider_secret_env(
    env: Mapping[str, str],
    specs: ProviderSpecs,
    fetch_secret: Callable[[str], Any],
    *,
    provider_keys: Set[str] | None = None,
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for provider in sorted(selected_provider_names(env, provider_keys)):
        spec = specs.get(provider)
        if not spec:
            continue
        secret_id = str(spec.get("api_key_secret") or "")
        env_name = str(spec.get("api_key_env") or "")
        if not secret_id or not env_name:
            continue
        value = fetch_secret(secret_id)
        if value:
            resolved[env_name] = str(value)
    return resolved


def resolve_runtime_provider_secret_env(
    module_name: str,
    env: Mapping[str, str],
    specs: ProviderSpecs,
    fetch_secret: Callable[[str], Any],
) -> dict[str, str]:
    provider_keys = RUNTIME_PROVIDER_KEYS.get(module_name)
    if provider_keys is None:
        return {}
    return resolve_provider_secret_env(env, specs, fetch_secret, provider_keys=provider_keys)


def redaction_followup(payload: Mapping[str, Any]) -> tuple[int, list[str]]:
    if payload.get("ok"):
        return 0, ["", "Next:", "  spark verify --deep"]
    findings = payload.get("findings")
    config_remaining = isinstance(findings, list) and any(
        str(item.get("path") or "").lower().endswith(".env")
        for item in findings
        if isinstance(item, Mapping)
    )
    if config_remaining:
        return 1, [
            "",
            "[FIX] Generated config still needs attention.",
            "      Log redaction intentionally does not rewrite generated module config.",
            "",
            "Next:",
            "  spark setup --resume",
            "  spark verify --deep",
        ]
    return 1, ["", "[FIX] A generated secret surface still needs attention.", "", "Next:", "  spark fix secrets"]
