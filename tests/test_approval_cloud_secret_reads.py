from __future__ import annotations

import pytest

from spark_cli.security.approval import CommandContext, approval_required_for_command


@pytest.mark.parametrize(
    "command,target",
    [
        (["gcloud", "--project", "spark", "secrets", "versions", "access", "latest", "--secret", "api"], "gcloud secrets versions access"),
        (["az", "keyvault", "secret", "show", "--vault-name", "spark", "--name", "api"], "az keyvault secret show"),
        (["az", "--subscription=prod", "keyvault", "secret", "download", "--file", "out"], "az keyvault secret download"),
        (["op", "read", "op://spark/api/password"], "op read"),
        (["op", "item", "get", "api-key", "--fields", "password"], "op item get"),
        (["op", "document", "get", "certificate"], "op document get"),
        (["doppler", "--project", "spark", "secrets", "get", "API_KEY", "--plain"], "doppler secrets get"),
        (["doppler", "secrets", "download", "--no-file", "--format", "json"], "doppler secrets download"),
    ],
)
def test_cloud_secret_reads_require_approval(command: list[str], target: str) -> None:
    decision = approval_required_for_command(command, CommandContext(hosted=True, non_interactive=True))
    assert decision.requires_approval
    assert decision.action_class == "credential_mutation"
    assert decision.risk == "critical"
    assert decision.approval_mode == "blocked"
    assert decision.confirmation_phrase == "approve cloud secret reveal"
    assert decision.target_display == target


@pytest.mark.parametrize(
    "command",
    [
        ["gcloud", "secrets", "versions", "list", "api"],
        ["az", "keyvault", "secret", "list", "--vault-name", "spark"],
        ["op", "item", "list"],
        ["op", "document", "list"],
        ["doppler", "secrets", "set", "API_KEY=redacted"],
    ],
)
def test_cloud_secret_metadata_and_mutation_near_misses_are_not_read_reveals(command: list[str]) -> None:
    decision = approval_required_for_command(command, CommandContext())
    assert decision.confirmation_phrase != "approve cloud secret reveal"
