"""Tests for chmod/chown/chgrp sensitive path gating."""

from spark_cli.security.approval import CommandContext, approval_required_for_command

ctx = CommandContext()


def test_chmod_etc_passwd():
    d = approval_required_for_command(['chmod', '777', '/etc/passwd'], ctx)
    assert d.requires_approval is True
    assert d.action_class == 'identity_access_mutation'


def test_chown_etc_shadow():
    d = approval_required_for_command(['chown', 'root:root', '/etc/shadow'], ctx)
    assert d.requires_approval is True


def test_chgrp_etc_sudoers():
    d = approval_required_for_command(['chgrp', '0', '/etc/sudoers'], ctx)
    assert d.requires_approval is True


def test_chmod_recursive():
    d = approval_required_for_command(['chmod', '-R', '755', '/var/www'], ctx)
    assert d.requires_approval is True


def test_chmod_local_file_no_approval():
    d = approval_required_for_command(['chmod', '755', './local-file.txt'], ctx)
    assert d.requires_approval is False
