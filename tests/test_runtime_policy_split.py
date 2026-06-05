from __future__ import annotations

import unittest

from spark_cli.runtime_policy import SHELL_CHAIN_TOKENS, split_single_argv_command


class SplitSingleArgvCommandTests(unittest.TestCase):
    def test_returns_argv_parts_for_simple_command(self) -> None:
        self.assertEqual(
            split_single_argv_command("python -m my.module", "Runtime command"),
            ["python", "-m", "my.module"],
        )

    def test_respects_quoted_arguments_with_spaces(self) -> None:
        self.assertEqual(
            split_single_argv_command('npm run "lint:check"', "Runtime command"),
            ["npm", "run", "lint:check"],
        )

    def test_empty_command_raises_with_subject_label(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            split_single_argv_command("   ", "Spawner command")
        # The subject label must show up in the error so the caller knows which slot is empty.
        self.assertIn("Spawner command", str(ctx.exception))

    def test_rejects_every_shell_chain_token(self) -> None:
        # SHELL_CHAIN_TOKENS includes &&, ||, ;, |, >, >>, <.
        for chain in ("npm test && echo ok", "ls | wc -l", "cat a > b", "echo a ; echo b"):
            with self.subTest(chain=chain):
                with self.assertRaises(SystemExit) as ctx:
                    split_single_argv_command(chain, "Runtime command")
                self.assertIn("single argv command", str(ctx.exception))

    def test_shell_chain_tokens_constant_includes_documented_set(self) -> None:
        # Lock the documented set so a future edit can't silently widen or narrow it.
        self.assertEqual(
            SHELL_CHAIN_TOKENS,
            {"&&", "||", ";", "|", ">", ">>", "<"},
        )

    def test_token_that_only_resembles_chain_is_not_rejected(self) -> None:
        # "&" alone is not in the chain-token set, so it is treated as a literal argv part.
        # This pins the current contract: only the exact tokens in SHELL_CHAIN_TOKENS trip the rejection.
        self.assertEqual(
            split_single_argv_command("python -c 'print(1 & 2)'", "Runtime command"),
            ["python", "-c", "print(1 & 2)"],
        )

    def test_argument_containing_redirect_in_quotes_is_not_rejected(self) -> None:
        # The redirect-looking text is inside a single quoted argument, so shlex emits one part
        # with no chain token, and the command is accepted.
        self.assertEqual(
            split_single_argv_command('python -c "print(\'>\')"', "Runtime command"),
            ["python", "-c", "print('>')"],
        )


if __name__ == "__main__":
    unittest.main()
