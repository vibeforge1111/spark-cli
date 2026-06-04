from __future__ import annotations

import pytest

from spark_cli.security.approval import CommandContext, approval_required_for_command


@pytest.mark.parametrize(
    "command",
    [
        ["kubectl", "get", "secret/spark-token", "-o", "yaml"],
        ["kubectl", "get", "secrets/spark-token"],
        ["kubectl", "--context", "prod", "describe", "-n", "spark", "secret/spark-token"],
        ["kubectl", "get", "--namespace=spark", "secret", "spark-token"],
    ],
)
def test_kubernetes_secret_resource_forms_require_approval(command: list[str]) -> None:
    decision = approval_required_for_command(command, CommandContext(non_interactive=True))
    assert decision.requires_approval
    assert decision.action_class == "credential_mutation"
    assert decision.risk == "critical"
    assert decision.approval_mode == "blocked"
    assert decision.confirmation_phrase == "approve kubernetes secret reveal"


@pytest.mark.parametrize(
    "command",
    [
        ["kubectl", "get", "secretive/spark-token"],
        ["kubectl", "get", "configmap", "secret/spark-token"],
        ["kubectl", "get", "pods", "--selector", "app=secret/spark-token"],
    ],
)
def test_kubernetes_non_secret_resources_remain_read_only(command: list[str]) -> None:
    assert not approval_required_for_command(command, CommandContext()).requires_approval
