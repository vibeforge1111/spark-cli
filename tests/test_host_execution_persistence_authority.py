from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class HostExecutionPersistenceAuthorityTests(unittest.TestCase):
    def assert_blocked(self, command: list[str], action_class: str, risk: str, phrase: str) -> None:
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

    def test_ssh_agent_and_private_key_mutations(self) -> None:
        for command in (
            ["ssh-add"],
            ["ssh-add", "/tmp/id_rsa"],
            ["ssh-add", "-D"],
            ["ssh-add", "-d", "/tmp/id_rsa"],
            ["ssh-add", "-x"],
            ["ssh-add", "-X"],
            ["ssh-add", "-l", "-D"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve ssh agent credential change")
        for command in (
            ["openssl", "genrsa", "-out", "private.pem", "2048"],
            ["openssl", "genpkey", "-algorithm", "RSA", "-out", "private.pem"],
            ["openssl", "ecparam", "-genkey", "-name", "prime256v1", "-out", "private.pem"],
            ["openssl", "req", "-newkey", "rsa:2048", "-keyout", "private.pem"],
            ["age-keygen", "-o", "key.txt"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve private key generation")
        for command in (["ssh-add", "-l"], ["ssh-add", "-L"], ["openssl", "version"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_package_installs_and_ephemeral_runners(self) -> None:
        for command in (
            ["pip", "install", "example-package"],
            ["pip3.12", "install", "example-package"],
            ["python3.12", "-m", "pip", "install", "example-package"],
            ["uv", "pip", "install", "example-package"],
            ["npm", "install", "example-package"],
            ["npm", "ci"],
            ["pnpm", "add", "example-package"],
            ["yarn", "install"],
            ["bun", "add", "example-package"],
            ["poetry", "install"],
            ["pipenv", "install"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve package install")
        for command in (
            ["pipx", "run", "cowsay", "hello"],
            ["uvx", "ruff", "--version"],
            ["uv", "tool", "run", "ruff", "--version"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve package runner execution")
        for command in (["pip", "show", "example-package"], ["npm", "view", "example-package"], ["pipx", "list"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_permission_disk_and_file_destruction(self) -> None:
        for command in (
            ["chmod", "600", "config.json"],
            ["chmod", "-R", "755", "project"],
            ["chown", "user:group", "file.txt"],
            ["chgrp", "-R", "staff", "project"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "high", "approve permission change")
        for command in (
            ["mkfs.ext4", "/dev/sdx1"],
            ["diskutil", "eraseDisk", "APFS", "Demo", "/dev/disk9"],
            ["parted", "/dev/sdx", "mklabel", "gpt"],
            ["fdisk", "/dev/sdx"],
            ["dd", "if=/dev/zero", "of=/dev/disk9", "bs=1m"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "critical", "approve disk destruction")
        for command in (["shred", "-u", "report.txt"], ["srm", "report.txt"], ["wipe", "-r", "workspace"]):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "critical", "approve file wipe")
        for command in (["diskutil", "list"], ["lsblk"], ["fdisk", "-l", "/dev/sdx"], ["parted", "/dev/sdx", "print"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_archive_execution_persistence_and_deno(self) -> None:
        for command in (
            ["tar", "-xf", "archive.tar", "--to-command", "sh -c echo ok"],
            ["tar", "--checkpoint-action=exec=sh hook.sh", "-cf", "archive.tar", "project"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve tar execution")
        for command in (["pm2", "startup"], ["pm2", "unstartup"], ["pm2", "save"], ["pm2", "resurrect"]):
            with self.subTest(command=command):
                self.assert_blocked(command, "process_autostart_mutation", "high", "approve pm2 startup change")
        for command in (
            ["deno", "run", "https://example.test/install.ts"],
            ["deno", "run", "jsr:@example/tool"],
            ["deno", "run", "npm:@example/tool"],
            ["deno", "run", "--allow-all", "script.ts"],
            ["deno", "run", "-A", "script.ts"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve deno execution")
        for command in (["tar", "-tf", "archive.tar"], ["pm2", "status"], ["deno", "fmt", "mod.ts"], ["deno", "run", "script.ts"]):
            with self.subTest(command=command):
                self.assert_allowed(command)


if __name__ == "__main__":
    unittest.main()
