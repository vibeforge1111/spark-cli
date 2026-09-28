from __future__ import annotations

import pytest

from spark_cli.security.approval import CommandContext, approval_required_for_command


@pytest.mark.parametrize(
    "command,display",
    [
        (["cat", ".env.production"], ".env.production"),
        (["less", "~/.aws/credentials"], "credentials"),
        (["more", "~/.kube/config"], "config"),
        (["type", r"C:\Users\alice\.docker\config.json"], "config.json"),
        (["Get-Content", r"C:\Users\alice\.ssh\id_rsa"], "id_rsa"),
        (["head", "~/.config/gcloud/application_default_credentials.json"], "application_default_credentials.json"),
        (["tail", "service-account.json"], "service-account.json"),
    ],
)
def test_local_secret_file_reads_require_approval(command: list[str], display: str) -> None:
    decision = approval_required_for_command(command, CommandContext(non_interactive=True))
    assert decision.requires_approval
    assert decision.action_class == "credential_mutation"
    assert decision.risk == "critical"
    assert decision.approval_mode == "blocked"
    assert decision.confirmation_phrase == "approve local secret file reveal"
    assert decision.target_display == f"local secret file ({display})"
    assert "users" not in decision.target_display.lower()


@pytest.mark.parametrize(
    "command",
    [
        ["cat", "README.md"],
        ["cat", ".env.example"],
        ["head", "~/.aws/config"],
        ["less", "docs/secrets.md"],
        ["type", "credentials.md"],
        ["Get-Content", "secretive.json"],
    ],
)
def test_plain_and_template_file_reads_remain_unclassified(command: list[str]) -> None:
    assert not approval_required_for_command(command, CommandContext()).requires_approval
