from __future__ import annotations

import json

from spark_cli.sandbox.audit import AUDIT_SCHEMA_VERSION, write_audit_event


def test_caller_event_cannot_override_canonical_audit_fields(tmp_path) -> None:
    path = write_audit_event(
        "ssh",
        "production",
        {
            "schema_version": 999,
            "timestamp": "attacker-time",
            "backend": "docker",
            "target": "other",
            "action_id": "ssh_probe",
        },
        home=tmp_path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == AUDIT_SCHEMA_VERSION
    assert payload["timestamp"] != "attacker-time"
    assert payload["backend"] == "ssh"
    assert payload["target"] == "production"
    assert payload["action_id"] == "ssh_probe"
