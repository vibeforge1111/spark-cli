"""Test that spark uninstall requires a target or --all flag."""
import argparse
import pytest
from spark_cli.cli import cmd_uninstall


def test_uninstall_requires_target_or_all():
    """spark uninstall with no target and no --all should raise SystemExit."""
    args = argparse.Namespace(
        all=False, target=None, purge_home=False, yes=False,
        force=False, remove_autostart=False, remove_user_path=False,
    )
    with pytest.raises(SystemExit, match="Specify a module to uninstall"):
        cmd_uninstall(args)


def test_uninstall_rejects_both_target_and_all():
    """spark uninstall with both target and --all should raise SystemExit."""
    args = argparse.Namespace(
        all=True, target="spark-cli", purge_home=False, yes=False,
        force=False, remove_autostart=False, remove_user_path=False,
    )
    with pytest.raises(SystemExit, match="Use either a target or --all"):
        cmd_uninstall(args)
