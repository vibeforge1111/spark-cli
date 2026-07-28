from __future__ import annotations

import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from spark_cli.cli import Module, collect_secret_requirements, collect_secret_values


class SecretRequiredDefaultTests(unittest.TestCase):
    @staticmethod
    def module(name: str, definition: dict[str, Any]) -> Module:
        return Module(
            name=name,
            path=Path(f"C:/tmp/{name}"),
            manifest={
                "module": {"name": name, "version": "1.0.0", "kind": "service", "plane": "runtime"},
                "needs": {"secrets": ["shared.api_key"]},
                "secrets": {"shared_api_key": definition},
            },
        )

    def test_default_required_is_order_independent(self) -> None:
        optional = self.module("optional-consumer", {"prompt": "Shared key", "required": False})
        default_required = self.module("default-consumer", {"prompt": "Shared key"})

        self.assertTrue(collect_secret_requirements([optional, default_required])["shared.api_key"]["required"])
        self.assertTrue(collect_secret_requirements([default_required, optional])["shared.api_key"]["required"])
        self.assertFalse(collect_secret_requirements([optional, optional])["shared.api_key"]["required"])

    def test_collect_values_fails_closed_when_later_module_omits_required(self) -> None:
        optional = self.module("optional-consumer", {"prompt": "Shared key", "required": False})
        default_required = self.module("default-consumer", {"prompt": "Shared key"})

        with patch("spark_cli.cli.fetch_secret", return_value=None), \
             patch("spark_cli.cli.fetch_generated_secret_value", return_value=None), \
             self.assertRaisesRegex(SystemExit, "Missing required secrets: shared.api_key"):
            collect_secret_values(Namespace(secret=None), [optional, default_required], interactive=False)


if __name__ == "__main__":
    unittest.main()
