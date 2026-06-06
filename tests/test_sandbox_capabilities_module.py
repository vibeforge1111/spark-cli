from __future__ import annotations

from spark_cli.sandbox.capabilities import (
    ActionClassification,
    CapabilityManifest,
    toxic_flow_denied,
    toxic_flow_findings,
)


def test_capability_manifest_default_risk_badges_minimal() -> None:
    manifest = CapabilityManifest(backend="local")
    badges = manifest.risk_badges()
    assert badges == ["backend:local", "fs:none", "network:off"]


def test_capability_manifest_risk_badges_include_non_default_axes() -> None:
    manifest = CapabilityManifest(
        backend="docker",
        filesystem="workspace",
        network="allowlist",
        secrets="named-env",
        persistence="session",
        privilege="rootless-container",
        inbound="authenticated",
        cost="bounded-cloud",
    )
    badges = manifest.risk_badges()
    assert "backend:docker" in badges
    assert "fs:workspace" in badges
    assert "network:allowlist" in badges
    assert "secrets:named-env" in badges
    assert "persistence:session" in badges
    assert "privilege:rootless-container" in badges
    assert "inbound:authenticated" in badges
    assert "cost:bounded-cloud" in badges


def test_capability_manifest_to_dict_round_trip() -> None:
    manifest = CapabilityManifest(backend="modal", network="on")
    payload = manifest.to_dict()
    assert payload["backend"] == "modal"
    assert payload["network"] == "on"
    assert payload["filesystem"] == "none"


def test_toxic_flow_findings_flags_known_pairs() -> None:
    findings = toxic_flow_findings({"secret_access", "network_write"})
    assert any("exfiltrate credentials" in detail for detail in findings)


def test_toxic_flow_findings_returns_empty_for_safe_set() -> None:
    assert toxic_flow_findings({"read_only"}) == []


def test_toxic_flow_findings_accepts_list_and_tuple_inputs() -> None:
    assert toxic_flow_findings(["memory_write", "policy_change"]) != []
    assert toxic_flow_findings(("untrusted_artifact", "execute")) != []


def test_toxic_flow_denied_returns_true_when_any_pair_present() -> None:
    assert toxic_flow_denied({"deploy", "stale_doctor"}) is True
    assert toxic_flow_denied({"deploy"}) is False


def test_action_classification_to_dict_includes_sorted_operations() -> None:
    classification = ActionClassification(
        action_id="ssh.run",
        mode="mutating",
        capabilities=CapabilityManifest(backend="ssh", filesystem="host", network="on"),
        operations=frozenset({"deploy", "stale_doctor"}),
    )
    payload = classification.to_dict()
    assert payload["action_id"] == "ssh.run"
    assert payload["mode"] == "mutating"
    assert payload["operations"] == ["deploy", "stale_doctor"]
    assert payload["toxic_findings"] != []
    assert payload["capabilities"]["backend"] == "ssh"
