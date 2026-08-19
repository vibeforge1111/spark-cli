from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class CredentialAuthorityTests(unittest.TestCase):
    def assert_blocked(
        self,
        command: list[str],
        action_class: str,
        risk: str,
        phrase: str,
    ) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.action_class, action_class, command)
        self.assertEqual(decision.risk, risk, command)
        self.assertEqual(decision.approval_mode, "blocked", command)
        self.assertEqual(decision.confirmation_phrase, phrase, command)

    def assert_allowed(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertFalse(decision.requires_approval, command)
        self.assertEqual(decision.action_class, "none", command)

    def test_pip_config_credential_access(self) -> None:
        # Exact-source behavior from spark-compete PR #1080.
        for command in (
            ["pip", "config", "get", "global.index-url"],
            ["pip", "config", "set", "global.index-url", "https://user:pass@example.test/simple"],
            ["pip", "config", "unset", "global.index-url"],
            ["pip", "config", "list"],
            ["python", "-m", "pip", "config", "get", "global.index-url"],
            ["python3.12", "-m", "pip", "config", "list"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve pip config access")
        for command in (
            ["pip", "config", "get", "global.timeout"],
            ["pip", "config", "set", "global.timeout", "30"],
            ["pip", "index", "versions", "requests"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_gpg_secret_key_access(self) -> None:
        # Exact-source behavior from #1087.
        for command in (
            ["gpg", "--export-secret-keys"],
            ["gpg", "--batch", "--export-secret-subkeys", "user@example.test"],
            ["gpg", "--delete-secret-keys", "user@example.test"],
            ["gpg2", "--delete-secret-and-public-keys", "user@example.test"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve gpg secret key access")
        for command in (
            ["gpg", "--list-secret-keys"],
            ["gpg", "--list-keys"],
            ["gpg", "--import", "public-key.asc"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_ssh_key_private_access(self) -> None:
        # Exact-source behavior from #1215.
        for command in (
            ["ssh-keygen", "-p", "-f", "synthetic-key"],
            ["ssh-keygen", "-y", "-f", "synthetic-key"],
            ["ssh-keygen", "-yf", "synthetic-key"],
            ["ssh-keygen", "-qyf", "synthetic-key"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve ssh key access")
        self.assert_allowed(["ssh-keygen", "-l", "-f", "synthetic-key.pub"])

    def test_password_manager_secret_reads(self) -> None:
        # Exact-source behavior from #1216, normalized over the narrower prior R30 phrase.
        for command in (
            ["pass", "show", "spark/demo"],
            ["pass", "otp", "spark/demo"],
            ["op", "read", "op://Vault/Item/password"],
            ["op", "item", "get", "Demo"],
            ["op", "document", "get", "Demo"],
            ["bw", "get", "password", "Demo"],
            ["bw", "get", "item", "Demo"],
            ["bw", "get", "totp", "Demo"],
            ["security", "find-generic-password", "-w", "-s", "spark-demo"],
            ["security", "find-internet-password", "-w", "-s", "spark-demo"],
            ["secret-tool", "lookup", "service", "spark-demo"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve password manager access")
        for command in (
            ["pass", "ls"],
            ["op", "whoami"],
            ["bw", "status"],
            ["security", "find-generic-password", "-s", "spark-demo"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_package_manager_credential_config(self) -> None:
        # Exact-source behavior from #1217.
        for command in (
            ["npm", "config", "get", "//registry.npmjs.org/:_authToken"],
            ["npm", "config", "set", "//registry.npmjs.org/:_authToken", "placeholder-value"],
            ["npm", "config", "delete", "//registry.npmjs.org/:_authToken"],
            ["pnpm", "config", "get", "//registry.npmjs.org/:_authToken"],
            ["pnpm", "config", "set", "//registry.npmjs.org/:_authToken", "placeholder-value"],
            ["yarn", "config", "get", "npmAuthToken"],
            ["yarn", "config", "set", "npmAuthToken", "placeholder-value"],
            ["yarn", "config", "unset", "npmAuthToken"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve package credential access")
        for command in (
            ["npm", "config", "get", "registry"],
            ["pnpm", "config", "get", "store-dir"],
            ["yarn", "config", "get", "npmRegistryServer"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_credential_file_reads(self) -> None:
        # Exact-source behavior from #1242 plus one environment-file suffix ratchet.
        for command in (
            ["cat", "~/.aws/credentials"],
            ["cat", "~/.ssh/id_rsa"],
            ["head", "-n", "5", ".env"],
            ["head", "-n", "5", ".env.staging"],
            ["tail", "~/.docker/config.json"],
            ["grep", "token", "~/.npmrc"],
            ["rg", "client_secret", "~/.config/gcloud/application_default_credentials.json"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve local secret file reveal")
        for command in (
            ["cat", "README.md"],
            ["cat", ".env.example"],
            ["head", "-n", "5", "CHANGELOG.md"],
            ["grep", "token", "docs/security.md"],
            ["rg", "credential", "docs/"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_secret_decrypt_commands(self) -> None:
        # Exact-source behavior from #1257.
        for command in (
            ["sops", "-d", "secrets.enc.yaml"],
            ["sops", "--decrypt", "secrets.enc.yaml"],
            ["gpg", "--decrypt", "secrets.gpg"],
            ["gpg", "-d", "secrets.gpg"],
            ["age", "-d", "secrets.age"],
            ["age", "--decrypt", "secrets.age"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve secret decrypt")
        for command in (
            ["sops", "--encrypt", "secrets.yaml"],
            ["gpg", "--verify", "release.sig"],
            ["gpg", "--list-keys"],
            ["age", "--encrypt", "public.txt"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)


if __name__ == "__main__":
    unittest.main()
