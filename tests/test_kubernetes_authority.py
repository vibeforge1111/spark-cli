from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class KubernetesAuthorityTests(unittest.TestCase):
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

    def test_kubectl_cp_upload_direction(self) -> None:
        for command in (
            ["kubectl", "cp", "report.txt", "spark-pod:/tmp/report.txt"],
            ["kubectl", "-n", "default", "cp", "report.txt", "spark-pod:/tmp/report.txt"],
            ["kubectl", "--context=prod", "cp", "--container=app", "payload", "default/spark-pod:tmp/payload"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve kubernetes file upload")
        self.assert_allowed(["kubectl", "cp", "spark-pod:/tmp/report.txt", "report.txt"])

    def test_kubectl_exec(self) -> None:
        for command in (
            ["kubectl", "exec", "spark-pod", "--", "sh"],
            ["kubectl", "-n", "default", "exec", "spark-pod", "--", "python", "-V"],
            ["kubectl", "--context", "prod", "exec", "-it", "spark-pod", "--", "bash"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve kubernetes exec")
        self.assert_allowed(["kubectl", "-n", "default", "logs", "spark-pod"])

    def test_kubeconfig_mutations_and_secret_reads(self) -> None:
        self.assert_blocked(
            ["kubectl", "config", "set-credentials", "prod-user", "--token", "redacted"],
            "credential_mutation",
            "high",
            "approve kubernetes credential change",
        )
        self.assert_blocked(
            ["kubectl", "config", "delete-user", "retired-user"],
            "credential_mutation",
            "high",
            "approve kubernetes credential change",
        )
        for command in (
            ["kubectl", "config", "use-context", "prod"],
            ["kubectl", "config", "set-cluster", "prod", "--server", "https://example.test"],
            ["kubectl", "config", "delete-context", "prod"],
            ["kubectl", "--kubeconfig", "demo", "config", "rename-context", "old", "prod"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve kubernetes context change")
        for command in (
            ["kubectl", "config", "view", "--raw"],
            ["kubectl", "--context", "prod", "get", "secret", "spark-token"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve kubernetes secret read")
        self.assert_allowed(["kubectl", "config", "current-context"])

    def test_kubectl_network_exposure(self) -> None:
        for command in (
            ["kubectl", "port-forward", "pod/spark", "8080:80"],
            ["kubectl", "-n", "default", "port-forward", "svc/spark", "8080:80", "--address", "0.0.0.0"],
            ["kubectl", "--context=prod", "proxy", "--address", "0.0.0.0", "--port", "8001"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "network_exfiltration", "high", "approve kubernetes network exposure")
        self.assert_allowed(["kubectl", "get", "services"])

    def test_helm_repository_and_registry_authority(self) -> None:
        for command in (
            ["helm", "repo", "add", "spark", "https://charts.example.test"],
            ["helm", "repo", "remove", "spark"],
            ["helm", "repo", "update"],
            ["helm", "--repository-config", "repositories.yaml", "repo", "rm", "spark"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve helm repo change")
        for action in ("login", "logout"):
            with self.subTest(action=action):
                self.assert_blocked(
                    ["helm", "registry", action, "registry.example.test"],
                    "credential_mutation",
                    "high",
                    "approve helm registry credential change",
                )
        self.assert_blocked(
            ["helm", "repo", "add", "private", "https://charts.example.test", "--username", "demo", "--password", "redacted"],
            "credential_mutation",
            "high",
            "approve helm repo credential change",
        )
        self.assert_allowed(["helm", "repo", "list"])

    def test_kubectl_workload_mutations(self) -> None:
        for command in (
            ["kubectl", "scale", "deployment/spark", "--replicas=3"],
            ["kubectl", "patch", "deployment/spark", "-p", "{}"],
            ["kubectl", "rollout", "restart", "deployment/spark"],
            ["kubectl", "rollout", "undo", "deployment/spark"],
            ["kubectl", "set", "image", "deployment/spark", "app=spark:next"],
            ["kubectl", "annotate", "deployment/spark", "owner=spark"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve kubernetes workload change")
        self.assert_allowed(["kubectl", "rollout", "status", "deployment/spark"])

    def test_kubectl_node_mutations(self) -> None:
        for command in (
            ["kubectl", "drain", "node/spark-worker", "--ignore-daemonsets"],
            ["kubectl", "cordon", "node/spark-worker"],
            ["kubectl", "uncordon", "node/spark-worker"],
            ["kubectl", "taint", "nodes", "spark-worker", "dedicated=spark:NoSchedule"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve kubernetes node change")
        self.assert_allowed(["kubectl", "top", "nodes"])

    def test_kubectl_create_dry_run_authority(self) -> None:
        for command in (
            ["kubectl", "create", "namespace", "spark"],
            ["kubectl", "create", "deployment", "spark", "--image=spark:latest"],
            ["kubectl", "create", "deployment", "spark", "--image=spark:latest", "--dry-run=server"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve kubernetes create")
        for command in (
            ["kubectl", "create", "secret", "generic", "spark-token", "--from-literal=token=redacted"],
            ["kubectl", "create", "secret", "generic", "spark-token", "--dry-run=client", "-o", "yaml"],
            ["kubectl", "create", "token", "spark-service-account"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "critical", "approve kubernetes create")
        self.assert_allowed(["kubectl", "create", "namespace", "spark", "--dry-run=client", "-o", "yaml"])

    def test_kubectl_resource_mutations_and_dry_run(self) -> None:
        for command in (
            ["kubectl", "replace", "-f", "deployment.yml"],
            ["kubectl", "edit", "deployment/spark"],
            ["kubectl", "expose", "deployment", "spark", "--port=80"],
            ["kubectl", "autoscale", "deployment", "spark", "--dry-run=server"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", "high", "approve kubernetes resource change")
        self.assert_allowed(["kubectl", "replace", "-f", "deployment.yml", "--dry-run=client", "-o", "yaml"])

    def test_kubectl_access_mutations(self) -> None:
        for command in (
            ["kubectl", "auth", "reconcile", "-f", "rbac.yml"],
            ["kubectl", "certificate", "approve", "spark-csr"],
            ["kubectl", "certificate", "deny", "spark-csr"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve kubernetes access change")
        self.assert_allowed(["kubectl", "auth", "can-i", "get", "pods"])

    def test_kubectl_debug_and_attach(self) -> None:
        for command in (
            ["kubectl", "debug", "pod/spark", "--image=busybox", "--target=app"],
            ["kubectl", "debug", "node/spark-worker", "-it", "--image=busybox"],
            ["kubectl", "attach", "pod/spark", "-c", "app", "-i"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve kubernetes remote process")
        self.assert_allowed(["kubectl", "describe", "pod/spark"])

    def test_kubectl_run_dry_run_authority(self) -> None:
        for command in (
            ["kubectl", "run", "spark-shell", "--image=busybox", "--", "sh"],
            ["kubectl", "run", "spark-job", "--image=spark:latest", "--dry-run=server"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve kubernetes run")
        self.assert_allowed(["kubectl", "run", "spark-job", "--image=spark:latest", "--dry-run=client", "-o", "yaml"])


if __name__ == "__main__":
    unittest.main()
