from __future__ import annotations

import subprocess
import unittest

from spark_cli.cli import summarize_command_output


class CliHealthcheckSummaryTests(unittest.TestCase):
    def test_typescript_failure_prefers_actionable_error_over_braces(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout="> spark-telegram-bot@1.0.0 health:polling\n> node scripts/run-health-polling.cjs\n",
            stderr=(
                "TSError: Unable to compile TypeScript:\n"
                "src/healthRuntime.ts(5,37): error TS2503: Cannot find namespace 'NodeJS'.\n"
                "    at createTSError (/Users/alice/project/node_modules/ts-node/src/index.ts:859:12)\n"
                "  diagnosticCodes: [\n"
                "    2503\n"
                "  ]\n"
                "}\n"
            ),
        )

        summary = summarize_command_output(result)

        self.assertIn("error TS2503", summary)
        self.assertIn("Cannot find namespace", summary)
        self.assertNotEqual(summary, "}")
        self.assertNotIn("/Users/alice", summary)

    def test_failure_summary_redacts_secrets_before_selection(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout="",
            stderr=(
                "Error: provider failed with Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
                "while opening https://api.example.test/run?api_key=sk-abcdefghi123456789\n"
            ),
        )

        summary = summarize_command_output(result)

        self.assertIn("[REDACTED]", summary)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", summary)
        self.assertNotIn("sk-abcdefghi123456789", summary)

    def test_failure_summary_strips_terminal_controls(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout="",
            stderr="\x1b]8;;https://example.test\x07Error: Missing module\x1b]8;;\x07\n",
        )

        self.assertEqual(summarize_command_output(result), "Error: Missing module")

    def test_structural_only_failure_never_returns_bare_braces(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout="{\n",
            stderr="diagnosticCodes: [\n2503\n]\n}\n",
        )

        self.assertEqual(summarize_command_output(result), "command failed without a readable diagnostic")


if __name__ == "__main__":
    unittest.main()
