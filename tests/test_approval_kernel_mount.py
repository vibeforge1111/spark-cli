"""Tests for kernel module and mount command gating in approval.py."""

from spark_cli.security.approval import approval_required_for_command


def test_mount_remount_rw():
    result = approval_required_for_command(['mount', '-o', 'remount,rw', '/'])
    assert result.requires_approval is True
    assert result.action_class == 'container_privilege_escalation'


def test_umount_boot():
    result = approval_required_for_command(['umount', '/boot'])
    assert result.requires_approval is True


def test_modprobe_remove():
    result = approval_required_for_command(['modprobe', '-r', 'kvm'])
    assert result.requires_approval is True


def test_insmod_payload():
    result = approval_required_for_command(['insmod', './payload.ko'])
    assert result.requires_approval is True


def test_rmmod_kvm():
    result = approval_required_for_command(['rmmod', 'kvm'])
    assert result.requires_approval is True


def test_ls_no_approval():
    result = approval_required_for_command(['ls', '-la'])
    assert result.requires_approval is False
