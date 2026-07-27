from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GIT_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
RELEASE = "spark-r30-2026-07-27"
IMMUTABLE_REF = "refs/tags/spark-r30-2026-07-27"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_r30_merged_source_truth_status(
    *,
    registry_path: Path | None = None,
    manifest_path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or _repo_root()
    registry = _load_json(registry_path or (root / "registry.json"))
    modules = registry.get("modules") if isinstance(registry.get("modules"), dict) else {}
    manifest_ref = manifest_path or (root / "docs" / "r30" / "R30_MERGED_SOURCE_TRUTH_2026-07-27.json")
    manifest = _load_json(manifest_ref)
    issues: list[str] = []
    rows: list[dict[str, Any]] = []

    expected_scalars = {
        "schema": "spark.r30.merged-source-truth.v1",
        "release": RELEASE,
        "immutable_ref": IMMUTABLE_REF,
        "public_points_baseline": 24409,
        "proposed_points": 0,
        "source_overlap_count": 0,
    }
    for key, expected in expected_scalars.items():
        if manifest.get(key) != expected:
            issues.append(f"{key}_mismatch")

    expected_names = sorted(
        str(name)
        for name, metadata in modules.items()
        if isinstance(metadata, dict) and bool(metadata.get("blessed"))
    )
    manifest_rows = manifest.get("modules")
    if not isinstance(manifest_rows, list):
        manifest_rows = []
        issues.append("modules_missing")
    actual_names = sorted(str(row.get("name") or "") for row in manifest_rows if isinstance(row, dict))
    if actual_names != expected_names:
        issues.append("module_set_mismatch")

    seen_sources: set[str] = set()
    seen_commits: set[str] = set()
    for row in manifest_rows:
        if not isinstance(row, dict):
            issues.append("module_row_invalid")
            continue
        name = str(row.get("name") or "")
        metadata = modules.get(name)
        row_issues: list[str] = []
        if not isinstance(metadata, dict) or not bool(metadata.get("blessed")):
            row_issues.append("registry_module_missing")
            metadata = {}
        source = str(row.get("source") or "")
        commit = str(row.get("merge_commit") or "").lower()
        verify_ref = str(metadata.get("verify_ref") or "")
        immutable_ref = str(row.get("immutable_ref") or manifest.get("immutable_ref") or "")
        attestation = metadata.get("attestation") if isinstance(metadata.get("attestation"), dict) else {}
        if source != str(metadata.get("source") or ""):
            row_issues.append("source_mismatch")
        if not GIT_COMMIT_SHA_PATTERN.fullmatch(commit):
            row_issues.append("merge_commit_invalid")
        if commit != str(metadata.get("commit") or "").lower():
            row_issues.append("registry_commit_mismatch")
        if verify_ref != immutable_ref:
            row_issues.append("verify_ref_mismatch")
        for key in ("commit", "canonical_head", "runtime_mirror_head"):
            if str(attestation.get(key) or "").lower() != commit:
                row_issues.append(f"attestation_{key}_mismatch")
        if str(attestation.get("verify_ref") or "") != verify_ref:
            row_issues.append("attestation_verify_ref_mismatch")
        if not isinstance(row.get("pr_number"), int) or int(row.get("pr_number") or 0) <= 0:
            row_issues.append("pr_number_invalid")
        if row.get("disposition") not in {"adopt", "selectively_port"}:
            row_issues.append("disposition_invalid")
        receipt = str(row.get("receipt") or "")
        if not receipt or Path(receipt).name != receipt:
            row_issues.append("receipt_name_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("receipt_sha256") or "")):
            row_issues.append("receipt_sha256_invalid")
        if source in seen_sources:
            row_issues.append("duplicate_source")
        if commit in seen_commits:
            row_issues.append("duplicate_merge_commit")
        seen_sources.add(source)
        seen_commits.add(commit)
        if name == "spawner-ui":
            if row.get("disposition") != "selectively_port":
                row_issues.append("spawner_disposition_mismatch")
            if not GIT_COMMIT_SHA_PATTERN.fullmatch(str(row.get("supersedes") or "")):
                row_issues.append("spawner_supersedes_invalid")
            if not str(row.get("supersession_reason") or "").strip():
                row_issues.append("spawner_supersession_reason_missing")
        rows.append(
            {
                "name": name,
                "source": source,
                "commit": commit,
                "verify_ref": verify_ref,
                "immutable_ref": immutable_ref,
                "pr_number": row.get("pr_number"),
                "disposition": row.get("disposition"),
                "ok": not row_issues,
                "issues": row_issues,
            }
        )
        issues.extend(f"{name}:{issue}" for issue in row_issues)

    return {
        "ok": not issues,
        "detail": (
            f"R30 merged source truth binds {len(rows)} canonical modules to immutable refs with zero overlap and zero proposed points."
            if not issues
            else f"R30 merged source truth has issues: {', '.join(issues)}."
        ),
        "manifest": str(manifest_ref.relative_to(root)) if manifest_ref.is_relative_to(root) else str(manifest_ref),
        "release": manifest.get("release"),
        "immutable_ref": manifest.get("immutable_ref"),
        "public_points_baseline": manifest.get("public_points_baseline"),
        "proposed_points": manifest.get("proposed_points"),
        "source_overlap_count": manifest.get("source_overlap_count"),
        "module_count": len(rows),
        "issues": issues,
        "rows": rows,
    }


def evaluate_r30_source_truth(
    *,
    merged_source_truth: dict[str, Any],
    cli_owner_handoff_docs: dict[str, Any],
    local_runtime_handoff_docs: dict[str, Any],
    release_lane: dict[str, Any],
    registry_pins: dict[str, Any],
) -> tuple[bool, list[str], bool]:
    checks = (
        ("r30_merged_source_truth", merged_source_truth),
        ("r30_cli_owner_handoff_docs", cli_owner_handoff_docs),
        ("r30_local_runtime_handoff_docs", local_runtime_handoff_docs),
        ("release_lane", release_lane),
        ("registry_pins", registry_pins),
    )
    blockers = [name for name, payload in checks if not bool(payload.get("ok"))]
    return not blockers, blockers, bool(merged_source_truth.get("ok"))


def historical_handoff_presentation(
    payload: dict[str, Any],
    *,
    default_detail: str,
    superseded_detail: str,
    superseded: bool,
) -> dict[str, Any]:
    ok = bool(payload.get("ok"))
    return {
        "ok": ok or superseded,
        "detail": payload.get("detail", default_detail) if ok or not superseded else superseded_detail,
    }


def present_r30_historical_handoffs(
    *,
    superseded: bool,
    owner_manifest: dict[str, Any],
    runtime_artifacts: dict[str, Any],
    voice: dict[str, Any],
    owner_actions: dict[str, Any],
    patch_apply: dict[str, Any],
    builder_trace: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    specs = {
        "owner_manifest": (owner_manifest, "R30 owner handoff manifest", "Historical owner handoff manifest is preserved and superseded by exact merged-source truth."),
        "runtime_artifacts": (runtime_artifacts, "R30 local runtime artifacts handoff", "Historical local-runtime handoff is preserved and superseded by exact merged-source truth."),
        "voice": (voice, "R30 voice registry decision", "Historical Voice handoff is preserved; merged PR #266 and its immutable R30 ref are canonical."),
        "owner_actions": (owner_actions, "R30 owner action packet", "Historical owner action packet is preserved and superseded by exact merged-source truth."),
        "patch_apply": (patch_apply, "R30 owner handoff patch apply proof", "Historical patch-apply proof is preserved; merged commits and immutable refs are canonical."),
        "builder_trace": (builder_trace, "R30 Builder trace lifecycle decision", "Historical Builder trace handoff is preserved; merged PR #1008 and its immutable R30 ref are canonical."),
    }
    return {
        name: historical_handoff_presentation(
            payload,
            default_detail=default_detail,
            superseded_detail=superseded_detail,
            superseded=superseded,
        )
        for name, (payload, default_detail, superseded_detail) in specs.items()
    }
