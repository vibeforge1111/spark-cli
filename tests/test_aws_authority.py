from __future__ import annotations

import unittest

from spark_cli.security.approval import CommandContext, approval_required_for_command


class AwsAuthorityTests(unittest.TestCase):
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

    def test_aws_credentials_and_default_routing(self) -> None:
        for command in (
            ["aws", "configure", "set", "aws_access_key_id", "placeholder"],
            ["aws", "--profile", "qa", "configure", "set", "aws_session_token", "placeholder"],
            ["aws", "configure", "import-sso", "--sso-session", "demo"],
            ["aws", "sso", "login", "--sso-session", "demo"],
            ["aws", "sso", "logout"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "credential_mutation", "high", "approve cloud credential change")
        for command in (
            ["aws", "configure", "set", "region", "us-east-1"],
            ["aws", "configure", "set", "profile", "production"],
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "identity_access_mutation", "high", "approve aws default routing change")
        self.assert_allowed(["aws", "configure", "list"])
        self.assert_allowed(["aws", "configure", "get", "region"])

    def test_cloudformation_authority(self) -> None:
        for command, risk in (
            (["aws", "cloudformation", "deploy", "--stack-name", "spark"], "high"),
            (["aws", "--region", "us-east-1", "cloudformation", "execute-change-set", "--change-set-name", "spark"], "high"),
            (["aws", "cloudformation", "delete-stack", "--stack-name", "spark"], "critical"),
        ):
            with self.subTest(command=command):
                self.assert_blocked(command, "external_publish", risk, "approve cloudformation change")
        self.assert_allowed(["aws", "cloudformation", "describe-stacks"])
        self.assert_allowed(["aws", "cloudformation", "validate-template", "--template-body", "file://template.yml"])

    def test_cdk_executes_apps_and_mutates_infrastructure(self) -> None:
        self.assert_blocked(["cdk", "deploy", "SparkStack"], "external_publish", "high", "approve cdk infrastructure change")
        self.assert_blocked(["aws-cdk", "deploy", "SparkStack"], "external_publish", "high", "approve cdk infrastructure change")
        self.assert_blocked(["cdk", "destroy", "SparkStack"], "external_publish", "critical", "approve cdk infrastructure change")
        self.assert_blocked(["cdk", "bootstrap"], "external_publish", "high", "approve cdk infrastructure change")
        for command in (["cdk", "synth"], ["cdk", "diff"], ["cdk", "--app", "python app.py", "list"]):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve cdk app execution")
        self.assert_allowed(["cdk", "--version"])

    def test_sam_local_execution_and_remote_mutations(self) -> None:
        self.assert_blocked(["sam", "deploy", "--stack-name", "spark"], "external_publish", "high", "approve sam infrastructure change")
        self.assert_blocked(["sam", "delete", "--stack-name", "spark"], "external_publish", "critical", "approve sam infrastructure change")
        self.assert_blocked(["sam", "package", "--s3-bucket", "spark"], "external_publish", "high", "approve sam infrastructure change")
        for command in (["sam", "build"], ["sam", "local", "invoke"], ["sam", "local", "start-api"]):
            with self.subTest(command=command):
                self.assert_blocked(command, "remote_code_execution", "high", "approve sam local execution")
        self.assert_allowed(["sam", "validate"])

    def test_ecs_runtime_authority(self) -> None:
        for operation in ("run-task", "start-task", "execute-command"):
            with self.subTest(operation=operation):
                self.assert_blocked(["aws", "ecs", operation, "--cluster", "spark"], "remote_code_execution", "high", "approve ecs runtime change")
        self.assert_blocked(["aws", "ecs", "update-service", "--cluster", "spark"], "external_publish", "high", "approve ecs runtime change")
        self.assert_blocked(["aws", "ecs", "stop-task", "--cluster", "spark"], "external_publish", "high", "approve ecs runtime change")
        self.assert_allowed(["aws", "ecs", "describe-services", "--cluster", "spark"])

    def test_lambda_runtime_authority(self) -> None:
        self.assert_blocked(["aws", "lambda", "invoke", "--function-name", "spark", "out.json"], "remote_code_execution", "high", "approve lambda runtime change")
        self.assert_blocked(["aws", "lambda", "update-function-code", "--function-name", "spark"], "external_publish", "high", "approve lambda runtime change")
        self.assert_blocked(["aws", "lambda", "delete-function", "--function-name", "spark"], "external_publish", "critical", "approve lambda runtime change")
        self.assert_allowed(["aws", "lambda", "get-function-configuration", "--function-name", "spark"])

    def test_ssm_remote_session_authority(self) -> None:
        for operation in ("send-command", "start-session", "resume-session"):
            with self.subTest(operation=operation):
                self.assert_blocked(["aws", "ssm", operation, "--target", "i-123"], "remote_code_execution", "high", "approve ssm remote execution")
        self.assert_blocked(["aws", "ssm", "terminate-session", "--session-id", "demo"], "external_publish", "high", "approve ssm session termination")
        self.assert_allowed(["aws", "ssm", "get-command-invocation", "--command-id", "demo"])

    def test_eks_cluster_and_local_identity_authority(self) -> None:
        self.assert_blocked(["aws", "eks", "create-cluster", "--name", "spark"], "external_publish", "high", "approve eks infrastructure change")
        self.assert_blocked(["aws", "eks", "delete-nodegroup", "--cluster-name", "spark"], "external_publish", "critical", "approve eks infrastructure change")
        self.assert_blocked(["aws", "eks", "update-kubeconfig", "--name", "spark"], "identity_access_mutation", "high", "approve eks kubeconfig change")
        self.assert_blocked(["aws", "eks", "get-token", "--cluster-name", "spark"], "credential_mutation", "critical", "approve aws credential reveal")
        self.assert_allowed(["aws", "eks", "describe-cluster", "--name", "spark"])

    def test_iam_identity_and_credential_authority(self) -> None:
        self.assert_blocked(["aws", "iam", "create-user", "--user-name", "spark"], "identity_access_mutation", "high", "approve iam identity change")
        self.assert_blocked(["aws", "iam", "delete-user", "--user-name", "spark"], "identity_access_mutation", "critical", "approve iam identity change")
        self.assert_blocked(["aws", "iam", "attach-user-policy", "--user-name", "spark"], "identity_access_mutation", "high", "approve iam identity change")
        self.assert_blocked(["aws", "iam", "create-access-key", "--user-name", "spark"], "credential_mutation", "critical", "approve iam identity change")
        self.assert_allowed(["aws", "iam", "simulate-principal-policy", "--policy-source-arn", "arn:aws:iam::123:user/spark"])

    def test_s3_storage_authority_and_transfer_direction(self) -> None:
        self.assert_blocked(["aws", "s3", "rb", "s3://example-bucket", "--force"], "external_publish", "critical", "approve s3 storage change")
        self.assert_blocked(["aws", "s3api", "put-object", "--bucket", "example-bucket"], "external_publish", "high", "approve s3 storage change")
        self.assert_blocked(["aws", "s3api", "put-bucket-policy", "--bucket", "example-bucket"], "external_publish", "critical", "approve s3 storage change")
        self.assert_blocked(["aws", "s3", "cp", "report.txt", "s3://example-bucket/report.txt"], "network_exfiltration", "medium", "approve network upload")
        self.assert_allowed(["aws", "s3", "cp", "s3://example-bucket/report.txt", "report.txt"])
        self.assert_allowed(["aws", "s3", "ls", "s3://example-bucket"])
        self.assert_allowed(["aws", "s3api", "head-object", "--bucket", "example-bucket"])

    def test_rds_database_authority(self) -> None:
        self.assert_blocked(["aws", "rds", "create-db-instance", "--db-instance-identifier", "spark"], "external_publish", "high", "approve rds database change")
        self.assert_blocked(["aws", "rds", "stop-db-instance", "--db-instance-identifier", "spark"], "external_publish", "high", "approve rds database change")
        self.assert_blocked(["aws", "rds", "failover-db-cluster", "--db-cluster-identifier", "spark"], "external_publish", "critical", "approve rds database change")
        self.assert_blocked(["aws", "rds", "delete-db-instance", "--db-instance-identifier", "spark"], "external_publish", "critical", "approve rds database change")
        self.assert_allowed(["aws", "rds", "describe-db-instances"])

    def test_ec2_infrastructure_authority(self) -> None:
        self.assert_blocked(["aws", "ec2", "run-instances", "--image-id", "ami-synthetic"], "external_publish", "high", "approve ec2 infrastructure change")
        self.assert_blocked(["aws", "ec2", "terminate-instances", "--instance-ids", "i-synthetic"], "external_publish", "critical", "approve ec2 infrastructure change")
        self.assert_blocked(["aws", "ec2", "authorize-security-group-ingress", "--group-id", "sg-synthetic"], "external_publish", "critical", "approve ec2 infrastructure change")
        self.assert_blocked(["aws", "ec2", "create-vpc", "--cidr-block", "10.0.0.0/16"], "external_publish", "critical", "approve ec2 infrastructure change")
        self.assert_allowed(["aws", "ec2", "get-console-output", "--instance-id", "i-synthetic"])

    def test_ecr_registry_and_login_authority(self) -> None:
        self.assert_blocked(["aws", "ecr", "create-repository", "--repository-name", "spark"], "external_publish", "high", "approve ecr registry change")
        self.assert_blocked(["aws", "ecr", "delete-repository", "--repository-name", "spark"], "external_publish", "critical", "approve ecr registry change")
        self.assert_blocked(["aws", "ecr", "set-repository-policy", "--repository-name", "spark"], "external_publish", "critical", "approve ecr registry change")
        self.assert_blocked(["aws", "--region", "us-east-1", "ecr", "get-login-password"], "credential_mutation", "critical", "approve aws credential reveal")
        self.assert_allowed(["aws", "ecr", "describe-repositories"])


if __name__ == "__main__":
    unittest.main()
