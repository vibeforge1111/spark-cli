from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


AwsActionClass = Literal[
    "credential_mutation",
    "external_publish",
    "identity_access_mutation",
    "remote_code_execution",
]
AwsRisk = Literal["high", "critical"]


@dataclass(frozen=True)
class AwsAuthority:
    action_class: AwsActionClass
    risk: AwsRisk
    reason: str
    target_display: str
    confirmation_phrase: str


@dataclass(frozen=True)
class CloudCommand:
    executable: Literal["aws", "cdk", "sam"]
    service: str
    operation: str
    arguments: tuple[str, ...]


AWS_SERVICES = frozenset(
    {
        "acm", "apigateway", "apigatewayv2", "batch", "cloudformation", "cloudfront", "cloudtrail",
        "cloudwatch", "cognito-identity", "cognito-idp", "configservice", "configure", "dynamodb", "ec2", "ecr",
        "ecr-public", "ecs", "eks", "events", "guardduty", "iam", "kms", "lambda", "logs", "rds", "route53",
        "s3", "s3api", "secretsmanager", "sns", "sqs", "ssm", "sso", "states", "stepfunctions", "sts", "wafv2",
    }
)
AWS_GLOBAL_VALUE_OPTIONS = frozenset(
    {
        "--ca-bundle", "--cli-connect-timeout", "--cli-read-timeout", "--color", "--endpoint-url", "--output",
        "--profile", "--query", "--region",
    }
)
CDK_COMMANDS = frozenset(
    {"acknowledge", "bootstrap", "context", "deploy", "destroy", "diff", "doctor", "docs", "gc", "import", "init", "list", "migrate", "notices", "refactor", "rollback", "synth", "watch"}
)
CDK_GLOBAL_VALUE_OPTIONS = frozenset(
    {"--app", "-a", "--build", "--ca-bundle-path", "--ci", "--context", "-c", "--output", "-o", "--plugin", "--profile", "--proxy", "--role-arn", "--toolkit-stack-name"}
)
SAM_COMMANDS = frozenset(
    {"build", "delete", "deploy", "init", "list", "local", "logs", "package", "pipeline", "publish", "remote", "sync", "traces", "validate"}
)
SAM_GLOBAL_VALUE_OPTIONS = frozenset(
    {"--config-env", "--config-file", "--debug", "--profile", "--region", "--template-file", "-t"}
)
READ_ONLY_PREFIXES = (
    "check-", "decode-", "describe-", "download-", "filter-", "get-", "head-", "list-", "lookup-",
    "query", "scan", "search-", "select-", "simulate-", "validate-", "wait",
)
CONTROL_PLANE_SERVICES = frozenset(
    {"cloudformation", "ecs", "eks", "lambda", "rds", "ec2", "ecr", "ecr-public", "s3", "s3api"}
)
SERVICE_PHRASES = {
    "cloudformation": "approve cloudformation change",
    "ecs": "approve ecs runtime change",
    "lambda": "approve lambda runtime change",
    "eks": "approve eks infrastructure change",
    "s3": "approve s3 storage change",
    "s3api": "approve s3 storage change",
    "rds": "approve rds database change",
    "ec2": "approve ec2 infrastructure change",
    "ecr": "approve ecr registry change",
    "ecr-public": "approve ecr registry change",
    "ssm": "approve ssm remote execution",
}
REMOTE_EXECUTION = {
    "ecs": frozenset({"execute-command", "run-task", "start-task"}),
    "lambda": frozenset({"invoke"}),
    "ssm": frozenset({"resume-session", "send-command", "start-session"}),
}
IAM_CREDENTIAL_OPERATIONS = frozenset(
    {
        "create-access-key", "create-login-profile", "create-service-specific-credential", "deactivate-mfa-device",
        "delete-access-key", "delete-login-profile", "delete-server-certificate", "delete-service-specific-credential",
        "delete-signing-certificate", "delete-ssh-public-key", "enable-mfa-device", "reset-service-specific-credential",
        "update-access-key", "update-login-profile", "update-service-specific-credential", "update-signing-certificate",
        "update-ssh-public-key", "upload-server-certificate", "upload-signing-certificate", "upload-ssh-public-key",
    }
)
IAM_CRITICAL_IDENTITY_PREFIXES = (
    "delete-", "detach-", "remove-", "deactivate-", "disable-", "revoke-",
)
SERVICE_CRITICAL_OPERATIONS = {
    "cloudformation": frozenset({"delete-stack"}),
    "ecs": frozenset(),
    "lambda": frozenset({"delete-function"}),
    "eks": frozenset({"delete-addon", "delete-cluster", "delete-nodegroup", "deregister-cluster"}),
    "s3": frozenset({"rb", "rm"}),
    "s3api": frozenset(
        {"delete-bucket", "delete-object", "delete-public-access-block", "put-bucket-acl", "put-bucket-policy"}
    ),
    "rds": frozenset(
        {"delete-db-cluster", "delete-db-instance", "failover-db-cluster", "remove-role-from-db-cluster", "reset-db-parameter-group"}
    ),
    "ec2": frozenset(
        {"authorize-security-group-egress", "authorize-security-group-ingress", "create-vpc", "delete-subnet", "revoke-security-group-egress", "revoke-security-group-ingress", "terminate-instances"}
    ),
    "ecr": frozenset(
        {"batch-delete-image", "delete-repository", "delete-repository-policy", "put-lifecycle-policy", "set-repository-policy"}
    ),
    "ecr-public": frozenset({"batch-delete-image", "delete-repository", "delete-repository-policy", "set-repository-policy"}),
}


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    match = re.match(r"[a-z][a-z0-9_.-]*", normalized)
    if not match:
        return ""
    return re.sub(r"\.(?:exe|cmd|bat)$", "", match.group(0))


def _split_option(value: str) -> tuple[str, str]:
    if "=" in value:
        return value.split("=", 1)
    return value, ""


def _locate_word(
    arguments: list[str], words: frozenset[str], value_options: frozenset[str]
) -> tuple[str, tuple[str, ...]]:
    index = 0
    while index < len(arguments):
        lowered = arguments[index].lower()
        if lowered == "--":
            index += 1
            continue
        name, attached = _split_option(lowered)
        if name in value_options:
            index += 1 if attached else 2
            continue
        if lowered.startswith("-"):
            index += 1
            continue
        if lowered in words:
            return lowered, tuple(arguments[index + 1 :])
        index += 1
    return "", ()


def _first_positional(arguments: tuple[str, ...], value_options: frozenset[str]) -> tuple[str, tuple[str, ...]]:
    command, rest = _locate_word(list(arguments), frozenset(value.lower() for value in arguments if not value.startswith("-")), value_options)
    return command, rest


def _cloud_command(parts: list[str]) -> CloudCommand | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    if executable == "aws":
        service, remainder = _locate_word(parts[1:], AWS_SERVICES, AWS_GLOBAL_VALUE_OPTIONS)
        if not service:
            return CloudCommand("aws", "", "", ())
        operation, arguments = _first_positional(remainder, AWS_GLOBAL_VALUE_OPTIONS)
        return CloudCommand("aws", service, operation, arguments)
    if executable == "cdk":
        operation, arguments = _locate_word(parts[1:], CDK_COMMANDS, CDK_GLOBAL_VALUE_OPTIONS)
        return CloudCommand("cdk", "cdk", operation, arguments)
    if executable == "sam":
        operation, arguments = _locate_word(parts[1:], SAM_COMMANDS, SAM_GLOBAL_VALUE_OPTIONS)
        return CloudCommand("sam", "sam", operation, arguments)
    return None


def _authority(
    action_class: AwsActionClass, risk: AwsRisk, reason: str, target: str, phrase: str
) -> AwsAuthority:
    return AwsAuthority(action_class, risk, reason, target, phrase)


def _is_read_only(operation: str) -> bool:
    return operation in {"help", "version"} or operation.startswith(READ_ONLY_PREFIXES)


def _configure_authority(command: CloudCommand) -> AwsAuthority | None:
    operation = command.operation
    arguments = [argument.lower() for argument in command.arguments]
    key = arguments[0] if arguments else ""
    if operation in {"import-sso", "sso"}:
        return _authority(
            "credential_mutation", "high", "AWS configure can import or establish SSO credentials.",
            f"aws configure {operation}", "approve cloud credential change",
        )
    if operation == "export-credentials":
        return _authority(
            "credential_mutation", "critical", "AWS configure can export active credentials.",
            "aws configure export-credentials", "approve aws credential reveal",
        )
    if operation == "get" and any(marker in key for marker in {"access_key", "credential", "secret", "session_token", "security_token"}):
        return _authority(
            "credential_mutation", "critical", "AWS configure can reveal stored cloud credentials.",
            "aws configure get", "approve aws credential reveal",
        )
    if operation == "set":
        credential = any(marker in key for marker in {"access_key", "credential", "secret", "session_token", "security_token"})
        if credential:
            return _authority(
                "credential_mutation", "high", "AWS configure can store or rotate cloud credentials.",
                "aws configure set", "approve cloud credential change",
            )
        return _authority(
            "identity_access_mutation", "high", "AWS configure can change the profile or region targeted by future commands.",
            "aws configure set", "approve aws default routing change",
        )
    return None


def _cdk_authority(command: CloudCommand) -> AwsAuthority | None:
    operation = command.operation
    if not operation:
        return None
    if operation in {"diff", "list", "synth"}:
        return _authority(
            "remote_code_execution", "high", "AWS CDK report commands execute the configured application to synthesize its cloud model.",
            f"cdk {operation}", "approve cdk app execution",
        )
    if operation in {"deploy", "bootstrap", "destroy", "import", "refactor", "rollback", "watch"}:
        return _authority(
            "external_publish", "critical" if operation == "destroy" else "high",
            "AWS CDK can mutate live cloud infrastructure.", f"cdk {operation}", "approve cdk infrastructure change",
        )
    return None


def _sam_authority(command: CloudCommand) -> AwsAuthority | None:
    operation = command.operation
    arguments = [argument.lower() for argument in command.arguments]
    if operation == "local" or operation == "build":
        return _authority(
            "remote_code_execution", "high", "AWS SAM can execute project build hooks or function code locally.",
            f"sam {operation}", "approve sam local execution",
        )
    if operation in {"delete", "deploy", "package", "publish", "sync"}:
        return _authority(
            "external_publish", "critical" if operation == "delete" else "high",
            "AWS SAM can upload artifacts or mutate live serverless infrastructure.",
            f"sam {operation}", "approve sam infrastructure change",
        )
    if operation == "remote" and arguments and arguments[0] in {"invoke", "test-event"}:
        return _authority(
            "remote_code_execution", "high", "AWS SAM can invoke a remote serverless function.",
            "sam remote invoke", "approve sam local execution",
        )
    return None


def _aws_secret_authority(command: CloudCommand) -> AwsAuthority | None:
    service, operation = command.service, command.operation
    arguments = [argument.lower() for argument in command.arguments]
    if service == "ecr" and operation == "get-login-password":
        return _authority(
            "credential_mutation", "critical", "AWS ECR can reveal a live registry password.",
            "aws ecr get-login-password", "approve aws credential reveal",
        )
    if service == "eks" and operation == "get-token":
        return _authority(
            "credential_mutation", "critical", "AWS EKS can issue a live cluster authentication token.",
            "aws eks get-token", "approve aws credential reveal",
        )
    if service == "sts" and operation in {"assume-role", "assume-role-with-saml", "assume-role-with-web-identity", "get-federation-token", "get-session-token"}:
        return _authority(
            "credential_mutation", "critical", "AWS STS can issue live temporary cloud credentials.",
            f"aws sts {operation}", "approve aws credential reveal",
        )
    if service == "secretsmanager" and operation in {"batch-get-secret-value", "get-secret-value"}:
        return _authority(
            "credential_mutation", "critical", "AWS Secrets Manager can reveal stored secret values.",
            f"aws secretsmanager {operation}", "approve aws credential reveal",
        )
    if service == "ssm" and operation in {"get-parameter", "get-parameters", "get-parameters-by-path", "get-parameter-history"}:
        if operation == "get-parameter" or "--with-decryption" in arguments:
            return _authority(
                "credential_mutation", "critical", "AWS SSM can reveal stored parameter secrets.",
                f"aws ssm {operation}", "approve aws credential reveal",
            )
    return None


def _iam_authority(command: CloudCommand) -> AwsAuthority | None:
    operation = command.operation
    if not operation or _is_read_only(operation):
        return None
    credential = operation in IAM_CREDENTIAL_OPERATIONS
    critical = credential or operation.startswith(IAM_CRITICAL_IDENTITY_PREFIXES)
    return _authority(
        "credential_mutation" if credential else "identity_access_mutation",
        "critical" if critical else "high",
        "AWS IAM can mutate identities, access policy, or authentication credentials.",
        f"aws iam {operation}", "approve iam identity change",
    )


def _control_plane_authority(command: CloudCommand) -> AwsAuthority | None:
    service, operation = command.service, command.operation
    if not operation or _is_read_only(operation):
        return None
    if service == "s3" and operation in {"cp", "sync"}:
        return None
    if service == "eks" and operation == "update-kubeconfig":
        return _authority(
            "identity_access_mutation", "high", "AWS EKS can write kubeconfig and change cluster identity routing.",
            "aws eks update-kubeconfig", "approve eks kubeconfig change",
        )
    if operation in REMOTE_EXECUTION.get(service, frozenset()):
        return _authority(
            "remote_code_execution", "high", f"AWS {service.upper()} can start or enter remotely executing workloads.",
            f"aws {service} {operation}", SERVICE_PHRASES.get(service, "approve aws remote execution"),
        )
    if service == "ssm" and operation == "terminate-session":
        return _authority(
            "external_publish", "high", "AWS SSM can terminate a live remote command session.",
            "aws ssm terminate-session", "approve ssm session termination",
        )
    critical = operation in SERVICE_CRITICAL_OPERATIONS.get(service, frozenset())
    return _authority(
        "external_publish", "critical" if critical else "high",
        f"AWS {service.upper()} can mutate live cloud resources or runtime state.",
        f"aws {service} {operation}", SERVICE_PHRASES.get(service, "approve aws cloud change"),
    )


def _aws_authority(command: CloudCommand) -> AwsAuthority | None:
    if not command.service or not command.operation:
        return None
    if command.service == "configure":
        return _configure_authority(command)
    if command.service == "sso" and command.operation in {"login", "logout"}:
        return _authority(
            "credential_mutation", "high", "AWS SSO can establish or remove cached cloud credentials.",
            f"aws sso {command.operation}", "approve cloud credential change",
        )
    if secret := _aws_secret_authority(command):
        return secret
    if command.service == "iam":
        return _iam_authority(command)
    if command.service in CONTROL_PLANE_SERVICES or command.service == "ssm":
        return _control_plane_authority(command)
    return None


def decide_aws_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    command = _cloud_command(parts)
    if command is None:
        return None
    if command.executable == "cdk":
        authority = _cdk_authority(command)
    elif command.executable == "sam":
        authority = _sam_authority(command)
    else:
        authority = _aws_authority(command)
    if authority is None:
        return None
    return decision_factory(
        parts,
        context,
        authority.action_class,
        authority.risk,
        authority.reason,
        target_display=authority.target_display,
        confirmation_phrase=authority.confirmation_phrase,
    )
