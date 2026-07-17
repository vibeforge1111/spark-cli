from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spark_cli.sandbox.access import home_or_default, module_env_dir, spark_workspace_root


def test_empty_spark_home_uses_the_user_default() -> None:
    default = Path("/Users/spark/.spark")
    with patch("spark_cli.sandbox.access.Path.home", return_value=default.parent):
        assert home_or_default(env={"SPARK_HOME": ""}) == default
        assert spark_workspace_root(env={"SPARK_HOME": ""}) == default / "workspaces"
        assert module_env_dir(env={"SPARK_HOME": ""}) == default / "config" / "modules"


def test_explicit_empty_environment_does_not_borrow_ambient_spark_home() -> None:
    default = Path("/Users/spark/.spark")
    with (
        patch("spark_cli.sandbox.access.Path.home", return_value=default.parent),
        patch.dict("spark_cli.sandbox.access.os.environ", {"SPARK_HOME": "/ambient/spark"}, clear=False),
    ):
        assert home_or_default(env={}) == default
        assert spark_workspace_root(env={}) == default / "workspaces"
        assert module_env_dir(env={}) == default / "config" / "modules"
