from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class InfrastructureAuthorityTests(unittest.TestCase):
    def assert_blocked(self, command: list[str], action: str, risk: str, phrase: str) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.action_class, action, command)
        self.assertEqual(decision.risk, risk, command)
        self.assertEqual(decision.approval_mode, "blocked", command)
        self.assertEqual(decision.confirmation_phrase, phrase, command)

    def assert_allowed(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertFalse(decision.requires_approval, command)
        self.assertEqual(decision.action_class, "none", command)

    def test_terraform_credentials_and_workspace_routing(self) -> None:
        for command in (
            ["terraform", "login"],
            ["terraform", "-chdir=infra", "login", "app.terraform.io"],
            ["terraform", "logout"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve terraform credential change")
        for command in (
            ["terraform", "workspace", "select", "prod"],
            ["terraform", "-chdir", "infra", "workspace", "new", "prod"],
            ["terraform", "workspace", "delete", "prod"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve terraform workspace change")
        for command in (
            ["terraform", "workspace", "list"],
            ["terraform", "workspace", "show"],
            ["terraform", "plan"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_terraform_state_mutations(self) -> None:
        for command in (
            ["terraform", "import", "aws_instance.spark", "i-123"],
            ["terraform", "state", "push", "state.tfstate"],
            ["terraform", "state", "mv", "aws_instance.old", "aws_instance.new"],
            ["terraform", "state", "rm", "aws_instance.old"],
            ["terraform", "state", "replace-provider", "old/provider", "new/provider"],
            ["terraform", "taint", "aws_instance.spark"],
            ["terraform", "untaint", "aws_instance.spark"],
            ["terraform", "force-unlock", "lock-id"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve terraform state change")

    def test_terraform_secret_bearing_state_reads(self) -> None:
        for command in (
            ["terraform", "state", "pull"],
            ["terraform", "state", "show", "aws_db_instance.spark"],
            ["terraform", "show", "terraform.tfstate"],
            ["terraform", "output", "-raw", "api_token"],
            ["terraform", "output", "-json"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve terraform secret read")
        self.assert_allowed(["terraform", "state", "list"])
        self.assert_allowed(["terraform", "show", "plan.out"])

    def test_pulumi_credentials_and_stack_routing(self) -> None:
        for command in (
            ["pulumi", "login"],
            ["pulumi", "--cwd", "infra", "login", "s3://state-bucket"],
            ["pulumi", "logout"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve pulumi credential change")
        for command in (
            ["pulumi", "stack", "select", "prod"],
            ["pulumi", "stack", "init", "prod"],
            ["pulumi", "--cwd=infra", "stack", "rm", "prod"],
            ["pulumi", "stack", "rename", "production"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve pulumi stack change")
        for command in (
            ["pulumi", "stack", "ls"],
            ["pulumi", "stack", "history"],
            ["pulumi", "preview"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_pulumi_config_mutation_and_secret_reads(self) -> None:
        for command in (
            ["pulumi", "config", "set", "apiKey", "redacted"],
            ["pulumi", "config", "set-all", "apiKey=redacted"],
            ["pulumi", "config", "rm", "apiKey"],
            ["pulumi", "config", "rm-all", "apiKey"],
            ["pulumi", "config", "cp", "source", "target"],
            ["pulumi", "config", "refresh"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve pulumi config change")
        for command in (
            ["pulumi", "config", "get", "apiKey"],
            ["pulumi", "config", "--show-secrets"],
            ["pulumi", "stack", "output", "apiKey", "--show-secrets"],
            ["pulumi", "stack", "export", "--show-secrets"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve pulumi secret reveal")
        self.assert_allowed(["pulumi", "config"])
        self.assert_allowed(["pulumi", "stack", "output", "endpoint"])

    def test_ansible_execution_and_inspection(self) -> None:
        for command in (
            ["ansible-playbook", "site.yml"],
            ["ansible-playbook", "--check", "site.yml"],
            ["ansible", "all", "-m", "shell", "-a", "id"],
            ["ansible", "-i", "inventory.ini", "web", "-m", "ping"],
            ["ansible", "web", "-m=command", "-a", "uptime"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve ansible execution")
        for command in (
            ["ansible", "--version"],
            ["ansible", "--help"],
            ["ansible-playbook", "--syntax-check", "site.yml"],
            ["ansible-playbook", "--list-hosts", "site.yml"],
            ["ansible-playbook", "--list-tasks", "site.yml"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_ansible_inventory_and_vault_secrets(self) -> None:
        for command in (
            ["ansible-inventory", "--list"],
            ["ansible-inventory", "--host", "spark-prod"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve ansible inventory secret read")
        for command in (
            ["ansible-vault", "view", "group_vars/prod/vault.yml"],
            ["ansible-vault", "decrypt", "group_vars/prod/vault.yml"],
            ["ansible-vault", "edit", "group_vars/prod/vault.yml"],
            ["ansible-vault", "rekey", "group_vars/prod/vault.yml"],
            ["ansible-vault", "create", "group_vars/prod/vault.yml"],
            ["ansible-vault", "encrypt_string", "redacted"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve ansible vault secret access")
        self.assert_allowed(["ansible-vault", "--version"])
        self.assert_allowed(["ansible-vault", "--help"])


if __name__ == "__main__":
    unittest.main()
