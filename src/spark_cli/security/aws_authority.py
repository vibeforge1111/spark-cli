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


@dataclass(frozen=True)
class AwsServicePolicy:
    action_class: AwsActionClass
    reason: str
    confirmation_phrase: str
    mutation_prefixes: tuple[str, ...] = ()
    mutation_operations: frozenset[str] = frozenset()
    critical_prefixes: tuple[str, ...] = ()
    critical_operations: frozenset[str] = frozenset()
    remote_prefixes: tuple[str, ...] = ()
    remote_operations: frozenset[str] = frozenset()


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
STEP_FUNCTIONS_POLICY = AwsServicePolicy(
    "external_publish",
    "AWS Step Functions can start workflow executions or mutate live state machines and aliases.",
    "approve step functions change",
    ("create-", "delete-", "publish-", "redrive-", "start-", "stop-", "tag-", "untag-", "update-"),
    critical_prefixes=("delete-", "stop-"),
    remote_prefixes=("redrive-", "start-"),
)
AWS_SERVICE_POLICIES = {
    "batch": AwsServicePolicy(
        "external_publish",
        "AWS Batch can submit remote jobs or mutate live compute environments, queues, and job definitions.",
        "approve batch job change",
        ("cancel-", "create-", "delete-", "deregister-", "register-", "submit-", "terminate-", "update-"),
        critical_prefixes=("cancel-", "delete-", "deregister-", "terminate-"),
        remote_operations=frozenset({"submit-job"}),
    ),
    "stepfunctions": STEP_FUNCTIONS_POLICY,
    "states": STEP_FUNCTIONS_POLICY,
    "events": AwsServicePolicy(
        "external_publish",
        "AWS EventBridge can publish events or mutate event buses, rules, targets, permissions, archives, or replays.",
        "approve eventbridge change",
        ("activate-", "cancel-", "create-", "deactivate-", "delete-", "disable-", "enable-", "put-", "remove-", "start-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-", "remove-"),
    ),
    "sqs": AwsServicePolicy(
        "external_publish",
        "AWS SQS can publish messages or mutate queues, policies, attributes, visibility, tags, or message state.",
        "approve sqs change",
        ("add-", "cancel-", "change-", "create-", "delete-", "purge-", "remove-", "send-", "set-", "start-", "tag-", "untag-"),
        critical_prefixes=("delete-", "purge-", "remove-"),
    ),
    "sns": AwsServicePolicy(
        "external_publish",
        "AWS SNS can publish notifications or mutate topics, subscriptions, attributes, permissions, SMS settings, or tags.",
        "approve sns change",
        ("add-", "confirm-", "create-", "delete-", "opt-", "publish", "remove-", "set-", "subscribe", "tag-", "unsubscribe", "untag-", "verify-"),
        critical_prefixes=("delete-", "remove-", "unsubscribe"),
    ),
    "secretsmanager": AwsServicePolicy(
        "credential_mutation",
        "AWS Secrets Manager can create, rotate, delete, restore, tag, or overwrite managed secret material and metadata.",
        "approve secretsmanager change",
        ("cancel-", "create-", "delete-", "put-", "remove-", "restore-", "rotate-", "stop-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-", "remove-"),
    ),
    "ssm": AwsServicePolicy(
        "credential_mutation",
        "AWS SSM Parameter Store can create, overwrite, delete, label, or retag stored configuration and secret-like values.",
        "approve ssm parameter change",
        mutation_operations=frozenset(
            {"add-tags-to-resource", "delete-parameter", "delete-parameters", "label-parameter-version", "put-parameter", "remove-tags-from-resource"}
        ),
        critical_operations=frozenset({"delete-parameter", "delete-parameters", "remove-tags-from-resource"}),
    ),
    "kms": AwsServicePolicy(
        "credential_mutation",
        "AWS KMS can decrypt data, generate plaintext key material, or mutate key lifecycle, policy, grants, aliases, rotation, or tags.",
        "approve kms change",
        ("cancel-", "connect-", "create-", "delete-", "disable-", "disconnect-", "enable-", "import-", "put-", "replicate-", "retire-", "revoke-", "rotate-", "schedule-", "tag-", "untag-", "update-"),
        frozenset({"decrypt", "generate-data-key", "generate-data-key-pair", "generate-mac", "sign"}),
        ("delete-", "disable-", "revoke-"),
        frozenset({"decrypt", "put-key-policy", "schedule-key-deletion"}),
    ),
    "acm": AwsServicePolicy(
        "credential_mutation",
        "AWS ACM can export or import certificate material and mutate certificate lifecycle, validation, options, or tags.",
        "approve acm change",
        mutation_operations=frozenset(
            {"add-tags-to-certificate", "delete-certificate", "export-certificate", "import-certificate", "put-account-configuration", "remove-tags-from-certificate", "renew-certificate", "request-certificate", "resend-validation-email", "update-certificate-options"}
        ),
        critical_operations=frozenset({"delete-certificate", "export-certificate", "import-certificate", "remove-tags-from-certificate"}),
    ),
    "route53": AwsServicePolicy(
        "external_publish",
        "AWS Route 53 can mutate public DNS records, hosted zones, health checks, domain routing, or zone associations.",
        "approve route53 change",
        ("associate-", "change-", "create-", "delete-", "disable-", "disassociate-", "enable-", "update-"),
        critical_prefixes=("delete-", "disable-", "disassociate-"),
    ),
    "cloudfront": AwsServicePolicy(
        "external_publish",
        "AWS CloudFront can change distributions, cache state, edge functions, origins, policies, aliases, or tags.",
        "approve cloudfront change",
        ("associate-", "copy-", "create-", "delete-", "disable-", "enable-", "publish-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-", "disable-"),
    ),
    "apigateway": AwsServicePolicy(
        "external_publish",
        "AWS API Gateway can deploy, route, expose, delete, or reconfigure public APIs and integrations.",
        "approve api gateway change",
        ("create-", "delete-", "flush-", "import-", "put-", "reset-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-",),
    ),
    "apigatewayv2": AwsServicePolicy(
        "external_publish",
        "AWS API Gateway can deploy, route, expose, delete, or reconfigure public APIs and integrations.",
        "approve api gateway change",
        ("create-", "delete-", "flush-", "import-", "put-", "reset-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-",),
    ),
    "cognito-idp": AwsServicePolicy(
        "identity_access_mutation",
        "AWS Cognito can create users, change passwords or groups, mutate pools, route roles, or revoke sessions.",
        "approve cognito access change",
        ("admin-", "associate-", "change-", "confirm-", "create-", "delete-", "disable-", "enable-", "global-sign-out", "revoke-", "set-", "sign-up", "tag-", "unlink-", "untag-", "update-"),
        critical_prefixes=("admin-set-", "delete-", "disable-", "global-sign-out", "revoke-", "set-"),
    ),
    "cognito-identity": AwsServicePolicy(
        "identity_access_mutation",
        "AWS Cognito can create users, change passwords or groups, mutate pools, route roles, or revoke sessions.",
        "approve cognito access change",
        ("admin-", "associate-", "change-", "confirm-", "create-", "delete-", "disable-", "enable-", "global-sign-out", "revoke-", "set-", "sign-up", "tag-", "unlink-", "untag-", "update-"),
        critical_prefixes=("admin-set-", "delete-", "disable-", "global-sign-out", "revoke-", "set-"),
    ),
    "dynamodb": AwsServicePolicy(
        "external_publish",
        "AWS DynamoDB can write items, mutate tables, restore or import data, change tags, or delete resources.",
        "approve dynamodb change",
        ("batch-write", "create-", "delete-", "disable-", "enable-", "import-", "put-", "restore-", "tag-", "transact-write", "untag-", "update-"),
        critical_prefixes=("delete-", "disable-"),
    ),
    "logs": AwsServicePolicy(
        "external_publish",
        "AWS CloudWatch Logs can write events, mutate logs, change retention or policies, export data, or retag resources.",
        "approve cloudwatch logs change",
        ("associate-", "cancel-", "create-", "delete-", "disassociate-", "put-", "start-", "stop-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-", "disassociate-"),
    ),
    "cloudwatch": AwsServicePolicy(
        "external_publish",
        "AWS CloudWatch can mutate alarms, dashboards, actions, metric data, tags, or monitoring state.",
        "approve cloudwatch change",
        ("delete-", "disable-", "enable-", "put-", "set-", "tag-", "untag-"),
        critical_prefixes=("delete-", "disable-", "set-"),
    ),
    "cloudtrail": AwsServicePolicy(
        "external_publish",
        "AWS CloudTrail can create or delete trails, stop audit logging, or mutate audit configuration and storage.",
        "approve cloudtrail change",
        ("add-", "create-", "delete-", "put-", "remove-", "restore-", "start-", "stop-", "update-"),
        critical_prefixes=("delete-", "remove-", "stop-"),
    ),
    "configservice": AwsServicePolicy(
        "external_publish",
        "AWS Config can change recording, delivery, compliance rules, remediation, or resource tags.",
        "approve aws config change",
        ("batch-delete-", "batch-put-", "delete-", "deliver-", "put-", "start-", "stop-", "tag-", "untag-"),
        critical_prefixes=("batch-delete-", "delete-", "stop-"),
    ),
    "guardduty": AwsServicePolicy(
        "external_publish",
        "AWS GuardDuty can change threat detection, finding state, members, destinations, or resource tags.",
        "approve guardduty change",
        ("accept-", "archive-", "create-", "decline-", "delete-", "disable-", "disassociate-", "enable-", "invite-", "start-", "stop-", "tag-", "unarchive-", "untag-", "update-"),
        critical_prefixes=("delete-", "disable-", "stop-"),
    ),
    "wafv2": AwsServicePolicy(
        "external_publish",
        "AWS WAFv2 can change web ACLs, request filtering, logging, permissions, associations, or tags.",
        "approve wafv2 change",
        ("associate-", "create-", "delete-", "disassociate-", "put-", "tag-", "untag-", "update-"),
        critical_prefixes=("delete-", "disassociate-"),
    ),
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
    if executable in {"aws-cdk", "cdk"}:
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
    return operation in {"help", "ls", "version"} or operation.startswith(READ_ONLY_PREFIXES)


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


def _service_policy_authority(command: CloudCommand) -> AwsAuthority | None:
    policy = AWS_SERVICE_POLICIES.get(command.service)
    if policy is None:
        return None
    operation = command.operation
    mutating = operation in policy.mutation_operations or operation.startswith(policy.mutation_prefixes)
    if not mutating:
        return None
    remote = operation in policy.remote_operations or operation.startswith(policy.remote_prefixes)
    critical = operation in policy.critical_operations or operation.startswith(policy.critical_prefixes)
    return _authority(
        "remote_code_execution" if remote else policy.action_class,
        "critical" if critical else "high",
        policy.reason,
        f"aws {command.service} {operation}",
        policy.confirmation_phrase,
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
    if authority := _service_policy_authority(command):
        return authority
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
