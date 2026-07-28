from __future__ import annotations

import re
import unittest
from pathlib import Path


CODEQL_VERSION = "v4.37.1"
CODEQL_SHA = "7188fc363630916deb702c7fdcf4e481b751f97a"


class CodeqlActionPinTests(unittest.TestCase):
    def test_codeql_steps_share_the_latest_verified_immutable_pin(self) -> None:
        root = Path(__file__).resolve().parent.parent
        workflow = (root / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
        pins = re.findall(r"github/codeql-action/(?:init|analyze)@([0-9a-f]{40})\s+#\s+(v\d+\.\d+\.\d+)", workflow)

        self.assertEqual(pins, [(CODEQL_SHA, CODEQL_VERSION), (CODEQL_SHA, CODEQL_VERSION)])


if __name__ == "__main__":
    unittest.main()
