from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class GitAuthorityTests(unittest.TestCase):
    def assert_blocked(
        self,
        command: list[str],
        action_class: str,
        risk: str,
        phrase: str,
    ) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.approval_mode, "blocked", command)
        self.assertEqual(decision.action_class, action_class, command)
        self.assertEqual(decision.risk, risk, command)
        self.assertEqual(decision.confirmation_phrase, phrase, command)

    def assert_allowed(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertFalse(decision.requires_approval, command)
        self.assertEqual(decision.action_class, "none", command)

    def test_destructive_worktree_operations(self) -> None:
        # Exact-source behavior from spark-compete PRs #1053-#1055 and #1057.
        cases = (
            (["git", "clean", "-fdx"], "destructive_filesystem", "critical", "approve git clean"),
            (["git", "clean", "-f"], "destructive_filesystem", "high", "approve git clean"),
            (["git", "restore", "."], "destructive_filesystem", "high", "approve git worktree discard"),
            (["git", "restore", "--staged", "src/app.py"], "destructive_filesystem", "high", "approve git worktree discard"),
            (["git", "checkout", "--", "src/app.py"], "destructive_filesystem", "high", "approve git worktree discard"),
            (["git", "checkout", "."], "destructive_filesystem", "high", "approve git worktree discard"),
            (["git", "stash", "clear"], "destructive_filesystem", "high", "approve git stash mutation"),
            (["git", "stash", "drop"], "destructive_filesystem", "high", "approve git stash mutation"),
            (["git", "stash", "pop"], "destructive_filesystem", "high", "approve git stash mutation"),
            (["git", "worktree", "remove", "../old-worktree"], "destructive_filesystem", "critical", "delete ../old-worktree"),
        )
        for command, action_class, risk, phrase in cases:
            with self.subTest(command=command):
                self.assert_blocked(command, action_class, risk, phrase)

    def test_history_and_recovery_mutations(self) -> None:
        # Exact-source behavior from #1056, #1067-#1068, #1070-#1075, and #1233.
        commands = (
            ["git", "branch", "-D", "feature"],
            ["git", "tag", "--delete", "v1.0.0"],
            ["git", "reflog", "expire", "--expire=now", "--all"],
            ["git", "reflog", "delete", "HEAD@{0}"],
            ["git", "gc", "--prune=now"],
            ["git", "gc", "--prune", "now"],
            ["git", "prune"],
            ["git", "update-ref", "-d", "refs/heads/feature"],
            ["git", "update-ref", "refs/heads/feature", "abc123"],
            ["git", "replace", "-d", "abc123"],
            ["git", "notes", "remove", "HEAD"],
            ["git", "notes", "prune"],
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            ["git", "symbolic-ref", "-m", "switch head", "HEAD", "refs/heads/main"],
            ["git", "symbolic-ref", "--delete", "HEAD"],
            ["git", "commit", "--amend", "--no-edit"],
            ["git", "branch", "-f", "feature", "HEAD~1"],
            ["git", "branch", "--force", "feature", "HEAD~1"],
            ["git", "checkout", "-B", "feature", "HEAD~1"],
            ["git", "switch", "-C", "feature", "HEAD~1"],
            ["git", "switch", "--force-create", "feature", "HEAD~1"],
            ["git", "merge", "--abort"],
            ["git", "cherry-pick", "--abort"],
            ["git", "revert", "--abort"],
            ["git", "am", "--abort"],
            ["git", "lfs", "migrate", "import", "--everything"],
            ["git", "lfs", "migrate", "export", "--include", "*.bin"],
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "git_history_mutation", "critical", "approve git history mutation")

    def test_identity_and_credential_mutations(self) -> None:
        # Exact-source behavior from #1076-#1078.
        identity_commands = (
            ["git", "remote", "add", "origin", "https://example.test/repo.git"],
            ["git", "remote", "set-url", "origin", "https://example.test/repo.git"],
            ["git", "remote", "remove", "origin"],
            ["git", "remote", "rename", "origin", "upstream"],
            ["git", "config", "--global", "credential.helper", "store"],
            ["git", "config", "user.email", "dev@example.test"],
            ["git", "config", "--unset", "credential.helper"],
            ["git", "config", "--rename-section", "alias", "alias2"],
        )
        for command in identity_commands[:4]:
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve git remote routing")
        for command in identity_commands[4:]:
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve git config mutation")

        self.assert_blocked(
            ["git", "credential", "fill"],
            "credential_mutation",
            "critical",
            "approve git credential access",
        )
        for action in ("approve", "reject"):
            with self.subTest(action=action):
                self.assert_blocked(
                    ["git", "credential", action],
                    "credential_mutation",
                    "high",
                    "approve git credential access",
                )

    def test_read_only_and_nondestructive_git_commands_remain_allowed(self) -> None:
        commands = (
            ["git", "status"],
            ["git", "clean", "--dry-run"],
            ["git", "clean", "-ndx"],
            ["git", "stash", "list"],
            ["git", "worktree", "list"],
            ["git", "branch", "--list"],
            ["git", "tag", "--list"],
            ["git", "reflog"],
            ["git", "reflog", "show"],
            ["git", "fsck"],
            ["git", "gc"],
            ["git", "gc", "--dry-run", "--prune=now"],
            ["git", "replace"],
            ["git", "replace", "--list"],
            ["git", "notes", "show", "HEAD"],
            ["git", "symbolic-ref", "HEAD"],
            ["git", "symbolic-ref", "-q", "HEAD"],
            ["git", "commit", "-m", "safe local commit"],
            ["git", "branch", "feature"],
            ["git", "checkout", "-b", "feature"],
            ["git", "switch", "-c", "feature"],
            ["git", "merge", "--continue"],
            ["git", "cherry-pick", "--continue"],
            ["git", "revert", "--continue"],
            ["git", "am", "--show-current-patch"],
            ["git", "lfs", "migrate", "info"],
            ["git", "remote"],
            ["git", "remote", "-v"],
            ["git", "remote", "show", "origin"],
            ["git", "config", "--get", "user.email"],
            ["git", "config", "user.email"],
            ["git", "config", "--file", "repo-config", "user.email"],
            ["git", "config", "--list"],
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_git_global_options_do_not_bypass_authority(self) -> None:
        self.assert_blocked(
            ["git", "-C", "repo", "clean", "-fd"],
            "destructive_filesystem",
            "critical",
            "approve git clean",
        )
        self.assert_blocked(
            ["git", "--git-dir=.git", "config", "user.email", "dev@example.test"],
            "identity_access_mutation",
            "high",
            "approve git config mutation",
        )


if __name__ == "__main__":
    unittest.main()
