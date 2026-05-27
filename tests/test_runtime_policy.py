"""Tests for module install-command runtime policy (SPARK-005)."""

from __future__ import annotations

import pytest

from spark_cli.runtime_policy import runtime_command_argv, sanitize_npm_env


def test_npm_install_allowed():
    argv = runtime_command_argv("npm install express")
    # We don't assert the resolved npm path (varies by host), just that
    # the subcommand+arg got through unchanged.
    assert argv[-2:] == ["install", "express"]


def test_npm_ci_allowed():
    argv = runtime_command_argv("npm ci")
    assert argv[-1:] == ["ci"]


def test_npm_run_blocked():
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm run postinstall")
    assert "not permitted" in str(exc.value)


def test_npm_exec_blocked():
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm exec evil-package")
    assert "not permitted" in str(exc.value)


def test_npm_publish_blocked():
    with pytest.raises(SystemExit):
        runtime_command_argv("npm publish")


def test_npm_with_no_subcommand_blocked():
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm")
    assert "no subcommand" in str(exc.value)


def test_npm_install_script_shell_flag_blocked():
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm install --script-shell=/bin/sh some-package")
    assert "--script-shell" in str(exc.value)


def test_npm_install_ignore_scripts_false_blocked():
    # --ignore-scripts=false is the explicit re-enable; blocked.
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm install --ignore-scripts=false some-package")
    assert "--ignore-scripts=false" in str(exc.value)


def test_npm_install_prefix_flag_blocked():
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm install --prefix /usr/local some-package")
    assert "--prefix" in str(exc.value)


def test_npm_install_prefix_equals_blocked():
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv("npm install --prefix=/usr/local some-package")
    assert "--prefix=" in str(exc.value)


# --- expanded denylist (Option 2 strengthening) ---

@pytest.mark.parametrize("cmd,needle", [
    ("npm install -g some-package", "-g"),
    ("npm install --global some-package", "--global"),
    ("npm install --location=global some-package", "--location=global"),
    ("npm install --install-links some-package", "--install-links"),
    ("npm install --unsafe-perm some-package", "--unsafe-perm"),
    ("npm install --userconfig /tmp/evil.npmrc some-package", "--userconfig"),
    ("npm install --globalconfig=/tmp/evil.npmrc some-package", "--globalconfig"),
    ("npm install --registry http://evil.example some-package", "--registry"),
    ("npm install --cache /tmp/evil-cache some-package", "--cache"),
])
def test_npm_install_dangerous_flags_blocked(cmd, needle):
    with pytest.raises(SystemExit) as exc:
        runtime_command_argv(cmd)
    assert needle in str(exc.value)


@pytest.mark.parametrize("cmd", [
    "npm install --ignore-scripts=true some-package",  # disabling scripts is the safe form
    "npm install --ignore-scripts some-package",
    "npm install --global=false some-package",
    "npm install --location=project some-package",
])
def test_npm_install_safe_flag_forms_allowed(cmd):
    # The safe form of a dangerous flag must NOT be blocked.
    argv = runtime_command_argv(cmd)
    assert argv[-1] == "some-package"


# --- env sanitization (close the npm_config_* / NODE_OPTIONS bypass) ---

def test_sanitize_npm_env_strips_dangerous_keys():
    env = {
        "PATH": "/usr/bin",
        "npm_config_ignore_scripts": "false",
        "NPM_CONFIG_SCRIPT_SHELL": "/bin/sh",
        "npm_config_userconfig": "/tmp/evil.npmrc",
        "npm_config_registry": "http://evil.example",
        "NODE_OPTIONS": "--require /tmp/evil.js",
        "npm_config_loglevel": "warn",   # benign config — kept
    }
    cleaned = sanitize_npm_env(env)
    assert "npm_config_ignore_scripts" not in cleaned
    assert "NPM_CONFIG_SCRIPT_SHELL" not in cleaned
    assert "npm_config_userconfig" not in cleaned
    assert "npm_config_registry" not in cleaned
    assert "NODE_OPTIONS" not in cleaned
    # benign vars are preserved
    assert cleaned["PATH"] == "/usr/bin"
    assert cleaned["npm_config_loglevel"] == "warn"
