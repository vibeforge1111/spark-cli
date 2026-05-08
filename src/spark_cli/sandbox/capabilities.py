from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


FilesystemCapability = Literal["none", "temp", "workspace", "project", "host"]
NetworkCapability = Literal["off", "allowlist", "on"]
SecretsCapability = Literal["none", "named-env", "provider-secret", "host-env"]
PersistenceCapability = Literal["ephemeral", "session", "named-target"]
PrivilegeCapability = Literal["non-root", "rootless-container", "root", "sudo-gated"]
InboundCapability = Literal["none", "authenticated", "public"]
CostCapability = Literal["free-local", "bounded-cloud", "metered-cloud"]


TOXIC_CAPABILITY_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("secret_access", "network_write", "Secret access plus network write can exfiltrate credentials."),
    ("secret_access", "artifact_publish", "Secret access plus artifact publish can leak credentials."),
    ("memory_write", "policy_change", "Memory writes must not alter policy."),
    ("untrusted_artifact", "execute", "Untrusted artifacts must not become executable behavior."),
    ("deploy", "stale_doctor", "Deploy requires a fresh doctor result."),
)


@dataclass(frozen=True)
class CapabilityManifest:
    backend: str
    filesystem: FilesystemCapability = "none"
    network: NetworkCapability = "off"
    secrets: SecretsCapability = "none"
    persistence: PersistenceCapability = "ephemeral"
    privilege: PrivilegeCapability = "non-root"
    inbound: InboundCapability = "none"
    cost: CostCapability = "free-local"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def risk_badges(self) -> list[str]:
        badges = [f"backend:{self.backend}", f"fs:{self.filesystem}", f"network:{self.network}"]
        if self.secrets != "none":
            badges.append(f"secrets:{self.secrets}")
        if self.persistence != "ephemeral":
            badges.append(f"persistence:{self.persistence}")
        if self.privilege != "non-root":
            badges.append(f"privilege:{self.privilege}")
        if self.inbound != "none":
            badges.append(f"inbound:{self.inbound}")
        if self.cost != "free-local":
            badges.append(f"cost:{self.cost}")
        return badges


@dataclass(frozen=True)
class ActionClassification:
    action_id: str
    mode: Literal["read_only", "dry_run", "mutating"]
    capabilities: CapabilityManifest
    operations: frozenset[str] = field(default_factory=frozenset)

    def toxic_findings(self) -> list[str]:
        return toxic_flow_findings(self.operations)

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "mode": self.mode,
            "capabilities": self.capabilities.to_dict(),
            "operations": sorted(self.operations),
            "toxic_findings": self.toxic_findings(),
        }


def toxic_flow_findings(operations: frozenset[str] | set[str] | list[str] | tuple[str, ...]) -> list[str]:
    active = set(operations)
    findings: list[str] = []
    for left, right, detail in TOXIC_CAPABILITY_PAIRS:
        if left in active and right in active:
            findings.append(detail)
    return findings


def toxic_flow_denied(operations: frozenset[str] | set[str] | list[str] | tuple[str, ...]) -> bool:
    return bool(toxic_flow_findings(operations))
