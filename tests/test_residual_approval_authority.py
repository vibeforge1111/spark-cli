from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class ResidualApprovalAuthorityTests(unittest.TestCase):
    def decision(self, command: list[str]):
        return approval_required_for_command(command, CommandContext(hosted=True, non_interactive=True))

    def assert_blocked(self, command: list[str], action_class: str, risk: str, phrase: str) -> None:
        decision = self.decision(command)
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.action_class, action_class, command)
        self.assertEqual(decision.risk, risk, command)
        self.assertEqual(decision.confirmation_phrase, phrase, command)
        self.assertEqual(decision.approval_mode, "blocked", command)

    def test_network_body_upload_flags_are_governed(self) -> None:
        for command in (
            ["curl", "-d", "payload", "https://example.test"],
            ["curl", "--data-raw", "payload", "https://example.test"],
            ["curl", "--data-urlencode", "value@example.test", "https://example.test"],
            ["wget", "--post-file", "payload.json", "https://example.test"],
            ["wget", "--body-file", "payload.json", "https://example.test"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "network_exfiltration", "medium", "approve network upload")

    def test_forced_git_worktree_and_ref_mutations_are_governed(self) -> None:
        for command in (["git", "checkout", "-f", "main"], ["git", "checkout", "--force", "main"]):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "high", "approve git worktree discard")
        self.assert_blocked(["git", "branch", "-f", "main", "HEAD~1"], "git_history_mutation", "critical", "approve git history mutation")
        self.assert_blocked(["git", "clean", "-fd"], "destructive_filesystem", "critical", "approve git clean")

    def test_combined_git_force_and_exact_docker_host_network_are_governed(self) -> None:
        self.assert_blocked(["git", "push", "-fv", "origin", "main"], "git_history_mutation", "critical", "approve git history mutation")
        self.assert_blocked(["docker", "run", "--network", "host", "alpine"], "container_privilege_escalation", "critical", "approve container privilege")
        self.assertFalse(self.decision(["docker", "run", "--network", "hostile", "alpine"]).requires_approval)

    def test_docker_isolation_bypass_flags_are_governed(self) -> None:
        for command in (
            ["docker", "run", "--cap-add=SYS_ADMIN", "alpine"],
            ["docker", "run", "--device", "/dev/kvm", "alpine"],
            ["docker", "run", "--pid=host", "alpine"],
            ["docker", "run", "--ipc", "host", "alpine"],
            ["docker", "run", "--security-opt", "seccomp=unconfined", "alpine"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "container_privilege_escalation", "critical", "approve container privilege")
        self.assert_blocked(
            ["docker", "run", "--cap-add", "NET_BIND_SERVICE", "alpine"],
            "container_privilege_escalation",
            "critical",
            "approve container privilege",
        )

    def test_package_runners_are_governed_with_prisma_semantics_preserved(self) -> None:
        for command in (
            ["npx", "--yes", "cowsay@latest", "hello"],
            ["npm", "exec", "--yes", "cowsay@latest", "--", "hello"],
            ["pnpm", "dlx", "cowsay@latest", "hello"],
            ["yarn", "dlx", "cowsay@latest", "hello"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve package runner execution")
        self.assertFalse(self.decision(["npx", "prisma", "db", "pull"]).requires_approval)
        self.assert_blocked(["npx", "prisma", "migrate", "deploy"], "external_publish", "high", "approve database migration")

    def test_container_exec_namespace_and_chroot_are_governed(self) -> None:
        cases = (
            (["docker", "exec", "spark", "bash"], "high", "approve container exec"),
            (["docker", "container", "exec", "spark", "bash"], "high", "approve container exec"),
            (["nsenter", "--target", "1", "--all", "bash"], "critical", "approve namespace entry"),
            (["chroot", "/mnt/sysroot", "bash"], "high", "approve chroot"),
        )
        for command, risk, phrase in cases:
            with self.subTest(command=command):
                self.assert_blocked(command, "container_privilege_escalation", risk, phrase)

    def test_account_mutations_are_governed_while_inspection_remains_open(self) -> None:
        for command in (
            ["adduser", "alice"],
            ["useradd", "-m", "alice"],
            ["usermod", "-aG", "sudo", "alice"],
            ["userdel", "alice"],
            ["groupadd", "developers"],
            ["groupmod", "-n", "devs", "developers"],
            ["groupdel", "developers"],
            ["passwd", "alice"],
            ["chpasswd"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve user account change")
        for command in (["id", "alice"], ["groups", "alice"], ["getent", "passwd", "alice"]):
            with self.subTest(command=command):
                self.assertFalse(self.decision(command).requires_approval)


if __name__ == "__main__":
    unittest.main()
