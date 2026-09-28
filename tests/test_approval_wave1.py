"""Approval-gating coverage for spark-compete Wave-1 PRs #1440 / #1441 (@mrxlolcat).

These are `adopt_interim`: the CLI-surface approval classifier is a still-live gate
that will be re-homed into the harness-core Governor on CLI migration.
"""

from spark_cli.security.approval import approval_required_for_command, CommandContext


def _decide(argv):
    return approval_required_for_command(argv, CommandContext())


def test_container_privilege_escalation_requires_approval() -> None:
    for argv in (["docker", "exec", "-it", "c", "sh"], ["nsenter", "-t", "1", "sh"], ["chroot", "/mnt"]):
        d = _decide(argv)
        assert d.requires_approval, argv
        assert d.action_class == "container_privilege_escalation"


def test_user_account_mutations_require_approval() -> None:
    for argv in (
        ["adduser", "alice"], ["useradd", "-m", "alice"], ["usermod", "-aG", "sudo", "alice"],
        ["userdel", "alice"], ["deluser", "alice"], ["groupadd", "devs"],
        ["groupmod", "-n", "x", "y"], ["groupdel", "devs"], ["passwd", "alice"], ["chpasswd"],
    ):
        d = _decide(argv)
        assert d.requires_approval, argv
        assert d.action_class == "identity_access_mutation"
        assert d.risk == "high"


def test_benign_command_needs_no_approval() -> None:
    assert not _decide(["ls", "-la"]).requires_approval
