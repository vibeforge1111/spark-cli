import sys
sys.path.insert(0, "src")
from spark_cli.security.approval import approval_required_for_command


def test_chmod_sensitive_path_requires_approval():
    d = approval_required_for_command(["chmod", "777", "/etc/passwd"])
    assert d.requires_approval is True
    assert d.action_class == "identity_access_mutation"


def test_chown_sensitive_path_requires_approval():
    d = approval_required_for_command(["chown", "root:root", "/etc/shadow"])
    assert d.requires_approval is True


def test_chgrp_sensitive_path_requires_approval():
    d = approval_required_for_command(["chgrp", "0", "/etc/sudoers"])
    assert d.requires_approval is True


def test_chmod_recursive_requires_approval():
    d = approval_required_for_command(["chmod", "-R", "755", "/var/www"])
    assert d.requires_approval is True


def test_chmod_local_file_no_approval():
    d = approval_required_for_command(["chmod", "755", "./local-file.txt"])
    assert d.requires_approval is False
