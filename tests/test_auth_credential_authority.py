from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class AuthCredentialAuthorityTests(unittest.TestCase):
    def assert_blocked(self, command: list[str], risk: str, phrase: str) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.action_class, "credential_mutation", command)
        self.assertEqual(decision.risk, risk, command)
        self.assertEqual(decision.approval_mode, "blocked", command)
        self.assertEqual(decision.confirmation_phrase, phrase, command)

    def assert_allowed(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertFalse(decision.requires_approval, command)
        self.assertEqual(decision.action_class, "none", command)

    def test_provider_auth_mutations(self) -> None:
        for command in (
            ["huggingface-cli", "login", "--token", "placeholder-token"],
            ["huggingface-cli", "logout"],
            ["hf", "auth", "login", "--token", "placeholder-token"],
            ["hf", "auth", "logout"],
            ["wandb", "login", "placeholder-token"],
            ["wandb", "logout"],
            ["modal", "token", "set", "placeholder-id", "placeholder-secret"],
            ["modal", "token", "delete"],
            ["modal", "token", "remove"],
            ["modal", "token", "clear"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "high", "approve provider auth change")
        for command in (
            ["huggingface-cli", "whoami"],
            ["hf", "auth", "whoami"],
            ["wandb", "status"],
            ["modal", "profile", "current"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_cloud_auth_token_reveals_and_mutations(self) -> None:
        for command in (
            ["gcloud", "auth", "print-access-token"],
            ["gcloud", "auth", "application-default", "print-access-token"],
            ["az", "account", "get-access-token"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "critical", "approve cloud token reveal")
        for command in (
            ["gcloud", "auth", "login"],
            ["gcloud", "auth", "activate-service-account", "--key-file", "synthetic-key.json"],
            ["gcloud", "auth", "application-default", "login"],
            ["gcloud", "auth", "application-default", "revoke"],
            ["gcloud", "auth", "revoke"],
            ["az", "login"],
            ["az", "logout"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "high", "approve cloud auth change")
        for command in (
            ["gcloud", "config", "list"],
            ["gcloud", "auth", "list"],
            ["az", "account", "show"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_github_auth_reveal_and_mutations(self) -> None:
        for command in (
            ["gh", "auth", "login", "--with-token"],
            ["gh", "auth", "logout"],
            ["gh", "auth", "refresh", "-s", "repo"],
            ["gh", "auth", "setup-git"],
            ["gh", "auth", "switch"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "high", "approve github auth change")
        self.assert_blocked(["gh", "auth", "token"], "critical", "approve github token reveal")
        self.assert_allowed(["gh", "auth", "status"])

    def test_package_auth_mutations_and_read_only_inventory(self) -> None:
        for command in (
            ["npm", "login"],
            ["npm", "logout"],
            ["npm", "adduser"],
            ["npm", "token", "create"],
            ["npm", "token", "revoke", "synthetic-token-id"],
            ["npm", "token", "delete", "synthetic-token-id"],
            ["pnpm", "login"],
            ["pnpm", "logout"],
            ["pnpm", "adduser"],
            ["pnpm", "token", "create"],
            ["pnpm", "token", "revoke", "synthetic-token-id"],
            ["pnpm", "token", "delete", "synthetic-token-id"],
            ["yarn", "npm", "login"],
            ["yarn", "npm", "logout"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "high", "approve package auth change")
        for command in (
            ["npm", "whoami"],
            ["pnpm", "whoami"],
            ["yarn", "npm", "whoami"],
            ["npm", "token", "list"],
            ["npm", "token", "list", "--json"],
            ["pnpm", "token", "list"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)


if __name__ == "__main__":
    unittest.main()
