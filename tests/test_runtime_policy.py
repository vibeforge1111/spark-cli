"""Tests for module install-command runtime policy (SPARK-005)."""

from __future__ import annotations

import pytest

from spark_cli.runtime_policy import runtime_command_argv


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
