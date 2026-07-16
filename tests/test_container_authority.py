from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class ContainerAuthorityTests(unittest.TestCase):
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

    def test_approval_classifier_flags_docker_prune_commands(self) -> None:
        cases = (
            (["docker", "system", "prune", "-af"], "critical"),
            (["docker", "image", "prune", "-af"], "high"),
            (["docker", "container", "prune", "-f"], "high"),
            (["docker", "volume", "prune", "-f"], "critical"),
            (["docker", "network", "prune", "-f"], "high"),
            (["docker", "builder", "prune", "-af"], "high"),
            (["docker", "buildx", "prune", "-af"], "high"),
            (["docker", "--context", "local", "system", "prune", "--volumes"], "critical"),
        )
        for command, risk in cases:
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", risk, "approve docker prune")
        for command in (["docker", "ps"], ["docker", "images"], ["docker", "system", "df"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_docker_image_removal(self) -> None:
        for command in (
            ["docker", "rmi", "example/spark:old"],
            ["docker", "image", "rm", "example/spark:old"],
            ["docker", "image", "remove", "example/spark:old"],
            ["docker", "compose", "down", "--rmi", "all"],
            ["docker", "compose", "down", "--rmi=local"],
            ["docker-compose", "-f", "compose.yml", "down", "--rmi", "all"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "high", "approve docker image removal")
        for command in (["docker", "images"], ["docker", "image", "ls"], ["docker", "compose", "ps"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_podman_privilege_escalation(self) -> None:
        for command in (
            ["podman", "run", "--privileged", "alpine"],
            ["podman", "run", "--network=host", "alpine"],
            ["podman", "run", "--pid", "host", "alpine"],
            ["podman", "run", "-v", "/:/host", "alpine"],
            ["podman", "run", "--mount", "type=bind,source=/home,target=/host-home", "alpine"],
            ["podman", "run", "--device=/dev/kvm", "alpine"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "container_privilege_escalation", "critical", "approve container privilege")
        for command in (["podman", "ps"], ["podman", "images"], ["podman", "run", "--rm", "alpine", "echo", "ok"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_podman_registry_login(self) -> None:
        for command in (
            ["podman", "login", "registry.example.test"],
            ["podman", "login", "--username", "demo", "registry.example.test"],
            ["podman", "logout", "registry.example.test"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve docker credential change")
        self.assert_allowed(["podman", "info"])

    def test_approval_classifier_flags_podman_image_push(self) -> None:
        for command in (
            ["podman", "push", "example/spark:latest"],
            ["podman", "push", "example/spark:latest", "registry.example.test/spark:latest"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve publish")
        for command in (["podman", "pull", "example/spark:latest"], ["podman", "images"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_podman_prune_commands(self) -> None:
        cases = (
            (["podman", "system", "prune", "-af"], "critical"),
            (["podman", "image", "prune", "-a"], "high"),
            (["podman", "container", "prune", "-f"], "high"),
            (["podman", "volume", "prune", "-f"], "critical"),
            (["podman", "builder", "prune", "-f"], "high"),
            (["podman", "--connection", "local", "network", "prune", "-f"], "high"),
        )
        for command, risk in cases:
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", risk, "approve podman prune")
        for command in (["podman", "system", "df"], ["podman", "images"], ["podman", "volume", "ls"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_podman_image_removal(self) -> None:
        for command in (
            ["podman", "rmi", "example/spark:old"],
            ["podman", "image", "rm", "example/spark:old"],
            ["podman", "image", "remove", "example/spark:old"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "high", "approve podman image removal")
        for command in (["podman", "images"], ["podman", "image", "ls"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_docker_compose_command_execution(self) -> None:
        for command in (
            ["docker", "compose", "exec", "app", "sh"],
            ["docker", "compose", "-f", "compose.yml", "run", "--rm", "app", "sh"],
            ["docker-compose", "exec", "app", "sh"],
            ["docker-compose", "-f", "compose.yml", "run", "--rm", "app", "sh"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve compose command execution")
        self.assert_allowed(["docker", "compose", "ps"])

    def test_approval_classifier_flags_docker_container_copy_uploads(self) -> None:
        for command in (
            ["docker", "cp", "report.txt", "spark-container:/tmp/report.txt"],
            ["docker", "container", "cp", "-a", "payload", "spark-container:tmp/payload"],
            ["docker", "compose", "cp", "report.txt", "app:/tmp/report.txt"],
            ["docker", "compose", "cp", "--index", "1", "payload", "app:tmp/payload"],
            ["docker-compose", "cp", "report.txt", "app:/tmp/report.txt"],
            ["podman", "cp", "report.txt", "spark-container:/tmp/report.txt"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve container file upload")
        for command in (
            ["docker", "cp", "spark-container:/tmp/report.txt", "report.txt"],
            ["docker", "compose", "cp", "app:/tmp/report.txt", "report.txt"],
            ["podman", "cp", "spark-container:/tmp/report.txt", "report.txt"],
            ["docker", "cp", "report.txt", r"C:\backup\report.txt"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_docker_build_credential_forwarding(self) -> None:
        for command in (
            ["docker", "build", "--secret", "id=demo,src=demo.env", "."],
            ["docker", "build", "--secret=id=demo,src=demo.env", "."],
            ["docker", "buildx", "build", "--ssh", "default", "."],
            ["docker", "--context", "local", "buildx", "build", "--secret", "id=demo,env=DEMO_TOKEN", "."],
            ["docker", "builder", "build", "--ssh=default", "."],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve docker build credential forwarding")
        for command in (["docker", "build", "."], ["docker", "buildx", "build", "."], ["docker", "buildx", "ls"]):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_docker_buildx_publish(self) -> None:
        for command in (
            ["docker", "buildx", "build", "--push", "-t", "registry.example.test/spark:latest", "."],
            ["docker", "buildx", "build", "--push=true", "."],
            ["docker", "buildx", "build", "--output", "type=registry", "."],
            ["docker", "builder", "build", "-o", "type=image,push=true", "."],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve docker build publish")
        for command in (
            ["docker", "buildx", "build", "."],
            ["docker", "buildx", "build", "--load", "."],
            ["docker", "buildx", "build", "--push=false", "."],
            ["docker", "builder", "build", "--output", "type=docker", "."],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_docker_context_routing_mutations(self) -> None:
        for command in (
            ["docker", "context", "use", "prod"],
            ["docker", "context", "create", "prod", "--docker", "host=ssh://user@example.test"],
            ["docker", "context", "update", "prod", "--docker", "host=tcp://example.test:2376"],
            ["docker", "context", "rm", "prod"],
            ["docker", "context", "remove", "prod"],
            ["docker", "context", "import", "prod", "context.tar"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve docker context change")
        for command in (
            ["docker", "context", "ls"],
            ["docker", "context", "show"],
            ["docker", "context", "inspect", "default"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_approval_classifier_flags_docker_compose_service_startup(self) -> None:
        for command in (
            ["docker", "compose", "up"],
            ["docker", "compose", "-f", "compose.yml", "up", "-d", "app"],
            ["docker", "compose", "start", "app"],
            ["docker", "compose", "restart", "app"],
            ["docker-compose", "up", "--build"],
            ["docker-compose", "-p", "demo", "restart", "app"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve compose service start")
        for command in (
            ["docker", "compose", "stop", "app"],
            ["docker", "compose", "down"],
            ["docker-compose", "kill", "app"],
            ["docker-compose", "rm", "-f", "app"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "destructive_filesystem", "high", "approve compose service change")
        for command in (
            ["docker", "compose", "ps"],
            ["docker", "compose", "config"],
            ["docker", "compose", "logs", "app"],
            ["docker-compose", "ps"],
        ):
            with self.subTest(command=command):
                self.assert_allowed(command)


if __name__ == "__main__":
    unittest.main()
