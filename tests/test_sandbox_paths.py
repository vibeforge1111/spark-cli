from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from spark_cli.sandbox.paths import spark_home


class SandboxPathTests(unittest.TestCase):
    def test_spark_home_defaults_when_env_is_unset_or_empty(self) -> None:
        default_home = (Path.home() / ".spark").expanduser()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SPARK_HOME", None)
            self.assertEqual(spark_home(), default_home)

        with patch.dict(os.environ, {"SPARK_HOME": ""}, clear=False):
            self.assertEqual(spark_home(), default_home)

    def test_spark_home_honors_non_empty_env(self) -> None:
        custom_home = Path("C:/spark-test-home")

        with patch.dict(os.environ, {"SPARK_HOME": str(custom_home)}, clear=False):
            self.assertEqual(spark_home(), custom_home.expanduser())


if __name__ == "__main__":
    unittest.main()
