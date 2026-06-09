from __future__ import annotations

from spark_cli.sandbox.docker import docker_capabilities


def test_docker_capabilities_use_declared_literal_values() -> None:
    payload = docker_capabilities().to_dict()

    assert payload["privilege"] == "rootless-container"
    assert payload["cost"] == "free-local"
