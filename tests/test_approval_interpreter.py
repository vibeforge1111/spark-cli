from spark_cli.security.approval import approval_required_for_command


def test_bash_c_requires_approval():
    d = approval_required_for_command(['bash', '-c', 'rm -rf /'])
    assert d.requires_approval is True
    assert d.action_class == 'remote_code_execution'


def test_python_c_requires_approval():
    d = approval_required_for_command(['python', '-c', 'import os'])
    assert d.requires_approval is True


def test_perl_e_requires_approval():
    d = approval_required_for_command(['perl', '-e', 'system("id")'])
    assert d.requires_approval is True


def test_node_e_requires_approval():
    d = approval_required_for_command(['node', '-e', 'process.exit()'])
    assert d.requires_approval is True


def test_python_script_no_approval():
    d = approval_required_for_command(['python', 'script.py'])
    assert d.requires_approval is False


def test_bash_script_no_approval():
    d = approval_required_for_command(['bash', 'script.sh'])
    assert d.requires_approval is False
