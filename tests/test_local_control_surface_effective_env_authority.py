from __future__ import annotations

import os
from unittest.mock import patch

from spark_cli.cli import local_control_surface_errors


CONTROL_ENV_KEYS = {
    "HOST",
    "SPARK_ALLOWED_HOSTS",
    "SPARK_BRIDGE_API_KEY",
    "SPARK_SPAWNER_HOST",
    "SPARK_UI_API_KEY",
}
STRONG_UI_KEY = "ui-key-abcdefghijklmnopqrstuvwxyz"
STRONG_BRIDGE_KEY = "bridge-key-abcdefghijklmnopqrstuvwxyz"


def control_surface_errors(
    generated: dict[str, str],
    parent: dict[str, str] | None = None,
) -> list[str]:
    clean_parent = {key: value for key, value in os.environ.items() if key not in CONTROL_ENV_KEYS}
    clean_parent.update(parent or {})
    with (
        patch("spark_cli.cli.read_generated_env", return_value=generated),
        patch.dict(os.environ, clean_parent, clear=True),
    ):
        return local_control_surface_errors()


def test_generated_host_overrides_filtered_parent_host() -> None:
    errors = control_surface_errors(
        {"SPARK_SPAWNER_HOST": "127.0.0.1"},
        {"SPARK_SPAWNER_HOST": "10.0.0.5"},
    )

    assert errors == []


def test_filtered_parent_host_applies_when_generated_host_is_missing() -> None:
    errors = control_surface_errors(
        {},
        {
            "SPARK_SPAWNER_HOST": "10.0.0.5",
            "SPARK_UI_API_KEY": STRONG_UI_KEY,
            "SPARK_BRIDGE_API_KEY": STRONG_BRIDGE_KEY,
        },
    )

    assert any("publicly bound" in error for error in errors)
    assert any("SPARK_ALLOWED_HOSTS" in error for error in errors)


def test_generated_lan_bind_is_treated_as_exposed() -> None:
    errors = control_surface_errors(
        {
            "SPARK_SPAWNER_HOST": "192.168.1.100",
            "SPARK_UI_API_KEY": STRONG_UI_KEY,
            "SPARK_BRIDGE_API_KEY": STRONG_BRIDGE_KEY,
        }
    )

    assert any("publicly bound" in error for error in errors)


def test_filtered_parent_allowed_hosts_apply_when_generated_value_is_missing() -> None:
    errors = control_surface_errors(
        {"SPARK_SPAWNER_HOST": "127.0.0.1"},
        {
            "SPARK_ALLOWED_HOSTS": "public.example",
            "SPARK_UI_API_KEY": STRONG_UI_KEY,
            "SPARK_BRIDGE_API_KEY": STRONG_BRIDGE_KEY,
        },
    )

    assert errors == []


def test_generated_empty_control_keys_override_strong_parent_keys() -> None:
    errors = control_surface_errors(
        {
            "SPARK_SPAWNER_HOST": "0.0.0.0",
            "SPARK_ALLOWED_HOSTS": "public.example",
            "SPARK_UI_API_KEY": "",
            "SPARK_BRIDGE_API_KEY": "",
        },
        {
            "SPARK_UI_API_KEY": STRONG_UI_KEY,
            "SPARK_BRIDGE_API_KEY": STRONG_BRIDGE_KEY,
        },
    )

    assert "SPARK_UI_API_KEY is missing." in errors
    assert "SPARK_BRIDGE_API_KEY is missing." in errors


def test_generic_parent_host_is_not_a_runtime_input() -> None:
    errors = control_surface_errors({}, {"HOST": "public.example"})

    assert errors == []


def test_generated_legacy_host_is_still_a_runtime_input() -> None:
    errors = control_surface_errors(
        {
            "HOST": "10.0.0.8",
            "SPARK_UI_API_KEY": STRONG_UI_KEY,
            "SPARK_BRIDGE_API_KEY": STRONG_BRIDGE_KEY,
        }
    )

    assert any("publicly bound" in error for error in errors)
