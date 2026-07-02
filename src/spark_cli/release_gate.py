"""Binding release gate: capture persistence, waiver ledger, staleness, and gated-action refusal.

Item 0.3 ("bind the ship gate"): a red-gate deploy becomes structurally impossible.

Normative sources (research repo /Users/alchemistab/Desktop/spark-desktop-app-research):
- docs/33-RELEASE-AND-VERSIONING-POLICY.md §1 (the binding-gate rule: G1 pin-advance, G2 tag-push,
  G3 hosted-deploy, G4 installer-manifest change refuse without a green-or-per-check-waived capture),
  §2 (the waiver ledger), §3 (the d7fc1df gate/evidence separation rule; a gate-code edit invalidates
  prior captures), §4 (capture integrity: git asserted on PATH, chip gates in the recorded gates table,
  readiness audits without --allow-incomplete).
- docs/40-SYSTEM-SCHEMA-ATLAS.md §2 (ship-artifact family home: ~/.spark/release-artifacts/<train>/;
  waiver home: <train>/waivers.json) + §3.6 (spark-waiver.v1 machine form).
- docs/41-CLOCKWORK-INTEGRATION-SPEC.md IC-10 (the release gate is the estate-level escapement).

Design notes:
- Everything here is fail-closed: no capture, an unreadable capture, a stale capture (gate code edited
  since it was recorded), or a red check without a valid per-check waiver all REFUSE the gated action.
  There is no --force flag; the only escape hatch is a written spark-waiver.v1 entry.
- r30's ship harness was an uncommitted external script that recorded red and shipped anyway; this
  module is the committed, tested replacement for its capture half, plus the refusal half that never
  existed. Verdict language is "recorded, verdict-gated" — never signed/attested (pre-B5, docs 34 §1).
- stdlib-only; no import of spark_cli.cli (the verify payload arrives injected or via subprocess), so
  the pre-push hook can run this module without paying the 20.5k-line cli.py import.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

CAPTURE_SCHEMA_VERSION = "spark-release-gate-capture.v1"
WAIVER_SCHEMA_VERSION = "spark-waiver.v1"
WAIVER_REQUIRED_FIELDS = ("check", "release", "reason", "risk_accepted", "expiry", "signed_off_by")
WAIVER_MAX_DAYS = 30
CAPTURE_FILE_PREFIX = "release-gate-capture-"
LATEST_CAPTURE_LINK = "latest-gate-capture"
GATE_MAP_FILENAME = "gate-map.json"
UNKNOWN_RELEASE = "unknown-release"

# CARRY-FORWARD (docs/33 §2): "a waiver on a check MUST NOT be re-issued for the same reason on
# more than two consecutive trains; the third requires an ADR." This module evaluates one train's
# capture + that train's waivers in isolation, so the consecutive-train ADR rule is NOT enforced
# here — it needs cross-train state (a walk of prior trains' waivers.json). It does not affect the
# single-ship structural-impossibility DoD, and is recorded honestly in the design doc's
# carry-forward list rather than silently dropped. Enforce it when the r31 jury (§7) lands.

DEFAULT_SPARK_HOME = Path(os.environ.get("SPARK_HOME", Path.home() / ".spark")).expanduser()
DEFAULT_ARTIFACTS_ROOT = DEFAULT_SPARK_HOME / "release-artifacts"
DEFAULT_MODULES_ROOT = DEFAULT_SPARK_HOME / "modules"
DEFAULT_INSTALLED_PATH = DEFAULT_SPARK_HOME / "state" / "installed.json"
DEFAULT_SYSTEM_MAP_PATH = DEFAULT_SPARK_HOME / "state" / "system-map" / "system-map.json"

# G2: release tag families observed in this estate (rNN cut labels, dated public-installer tags,
# ship tags). A pushed tag matching any of these is a gated action.
GATED_TAG_PATTERNS = (
    # DoD names "r* tag push": r followed by a digit and any suffix (r31, r31rc1, r31.1, r31-hotfix).
    re.compile(r"^refs/tags/r\d"),
    re.compile(r"^refs/tags/spark-cli-public-installer-\d{4}-\d{2}-\d{2}-r\d+(?:-v\d+)?$"),
    re.compile(r"^refs/tags/spark-ship-\d{4}-\d{2}-\d{2}$"),
)
# G1 / G4: repo-relative paths whose change in a pushed range is a gated action.
G1_GATED_PATHS = ("registry.json",)
G4_GATED_PATHS = (
    "scripts/installer-manifest.json",
    "scripts/install.sh",
    "scripts/install.ps1",
)
ZERO_SHA = "0" * 40


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def run_command(
    args: list[str], *, cwd: Path | None = None, timeout: int = 120
) -> tuple[int, str, str]:
    """Run a subprocess without raising; a start failure is reported as rc 127 (fail-closed rows)."""
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", f"could not run {args[0]}: {exc}"
    return result.returncode, result.stdout, result.stderr


def _run_git(args: list[str], *, cwd: Path | None = None) -> tuple[int, str, str]:
    return run_command(["git", "-c", "core.longpaths=true", *args], cwd=cwd)


# ---------------------------------------------------------------------------
# gate-map + gate-code tree hash (doc 33 §3: a gate edit invalidates prior captures)
# ---------------------------------------------------------------------------


def load_gate_map(repo_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = repo_root / GATE_MAP_FILENAME
    if not path.exists():
        return None, f"{GATE_MAP_FILENAME} not found at {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{GATE_MAP_FILENAME} unreadable: {exc}"
    gates = payload.get("gates")
    if not isinstance(gates, dict) or not gates:
        return None, f"{GATE_MAP_FILENAME} has no gates mapping"
    for name, entry in gates.items():
        if not isinstance(entry, dict) or not entry.get("gate_code"):
            return None, f"gate {name!r} declares no gate_code files"
    return payload, None


def _expand_globs(repo_root: Path, patterns: list[str]) -> list[Path]:
    seen: set[Path] = set()
    for pattern in patterns:
        for match in sorted(repo_root.glob(pattern)):
            if match.is_file():
                seen.add(match)
    return sorted(seen)


def _hash_patterns(repo_root: Path, patterns: list[str]) -> dict[str, Any]:
    """sha256 over every file matching the patterns. Deterministic; missing files hash as MISSING."""
    files: dict[str, str] = {}
    for path in _expand_globs(repo_root, patterns):
        rel = path.relative_to(repo_root).as_posix()
        try:
            files[rel] = _sha256_bytes(path.read_bytes())
        except OSError:
            files[rel] = "UNREADABLE"
    for pattern in patterns:
        if not any(fnmatch.fnmatch(rel, pattern) for rel in files) and "*" not in pattern:
            files.setdefault(pattern, "MISSING")
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(f"{rel}\x00{files[rel]}\n".encode("utf-8"))
    return {"tree_hash": digest.hexdigest(), "file_count": len(files), "files": files}


def gate_code_tree_hash(repo_root: Path, gate_map: dict[str, Any]) -> dict[str, Any]:
    """sha256 over every registered gate-code file (+ the gate-map itself, 33 §3)."""
    patterns: list[str] = [GATE_MAP_FILENAME]
    for entry in gate_map.get("gates", {}).values():
        patterns.extend(entry.get("gate_code") or [])
    return _hash_patterns(repo_root, patterns)


def evidence_tree_hash(repo_root: Path, gate_map: dict[str, Any]) -> dict[str, Any]:
    """sha256 over every registered evidence/fixture file (registry.json, installer files, R30 docs).

    doc 33 §1 rule 1: a gated action is permitted only if "no gate code, gate manifest, or gate
    FIXTURE has changed since that capture." Editing registry.json (i.e. advancing a pin) after a
    green capture must therefore force a fresh capture — otherwise a stale green would keep
    permitting a state it never verified.
    """
    patterns: list[str] = []
    for entry in gate_map.get("gates", {}).values():
        patterns.extend(entry.get("evidence") or [])
    return _hash_patterns(repo_root, sorted(set(patterns)))


# ---------------------------------------------------------------------------
# capture integrity rows (doc 33 §4): git-state, chip gates, strict readiness
# ---------------------------------------------------------------------------


def collect_git_state(
    repo_root: Path,
    *,
    modules_root: Path = DEFAULT_MODULES_ROOT,
    installed: dict[str, Any] | None = None,
    git_runner: Callable[..., tuple[int, str, str]] = _run_git,
) -> dict[str, Any]:
    """Record git state for the CLI repo + every installed module source.

    r30 wrote 5 of 7 git-state files blank because git was missing from the harness PATH and the
    stderr was captured as if it were state (doc 21 §1.1). Here: git absent or erroring is a RED
    check with the error recorded — a blank/failed row can never read as a captured state.
    """
    rows: list[dict[str, Any]] = []
    rc, out, err = git_runner(["--version"])
    if rc != 0:
        return {
            "name": "git_state",
            "ok": False,
            "detail": f"git is not runnable on PATH: {err.strip() or out.strip() or rc}",
            "rows": rows,
        }
    targets: list[tuple[str, Path]] = [("spark-cli", repo_root)]
    installed_map = installed if isinstance(installed, dict) else {}
    for name in sorted(installed_map):
        source = modules_root / name / "source"
        if source.is_dir():
            targets.append((name, source))
    all_ok = True
    for name, path in targets:
        row: dict[str, Any] = {"repo": name, "path": str(path)}
        rc_head, head, err_head = git_runner(["-C", str(path), "rev-parse", "HEAD"])
        rc_branch, branch, _ = git_runner(["-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"])
        rc_status, status, err_status = git_runner(["-C", str(path), "status", "--porcelain"])
        if rc_head != 0 or rc_status != 0:
            row["error"] = (err_head or err_status).strip() or "git state capture failed"
            all_ok = False
        else:
            row["head"] = head.strip()
            row["branch"] = branch.strip() if rc_branch == 0 else "(detached)"
            row["dirty_count"] = len([line for line in status.splitlines() if line.strip()])
        rows.append(row)
    detail = f"{len(rows)} repos captured" if all_ok else "one or more repos failed git-state capture"
    return {"name": "git_state", "ok": all_ok, "detail": detail, "rows": rows}


def collect_chip_gates(
    *,
    modules_root: Path = DEFAULT_MODULES_ROOT,
    installed: dict[str, Any] | None = None,
    runner: Callable[..., tuple[int, str, str]] = run_command,
) -> list[dict[str, Any]]:
    """One gates-table row per installed chip-pack module, command taken from its own spark.toml.

    Doc 33 §4.3: every gate appears in the recorded gates table — chip gates included; a gate that
    errors is a red row, not an absent row. Commands come from each module's [healthcheck] block so
    the harness can never invoke a subcommand the module does not declare (the `evaluate-builtin`
    argparse-typo class dies here).
    """
    rows: list[dict[str, Any]] = []
    installed_map = installed if isinstance(installed, dict) else {}
    for name in sorted(installed_map):
        entry = installed_map.get(name) or {}
        if not isinstance(entry, dict) or entry.get("kind") != "chip-pack":
            continue
        row: dict[str, Any] = {"name": f"chip_gate:{name}", "ok": False}
        source = modules_root / name / "source"
        toml_path = source / "spark.toml"
        if not toml_path.is_file():
            row["detail"] = f"spark.toml missing at {toml_path}"
            rows.append(row)
            continue
        try:
            manifest = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            row["detail"] = f"spark.toml unreadable: {exc}"
            rows.append(row)
            continue
        healthcheck = manifest.get("healthcheck") or {}
        command = str(healthcheck.get("command") or "").strip()
        if not command:
            row["detail"] = "module declares no [healthcheck] command"
            rows.append(row)
            continue
        timeout = int(healthcheck.get("timeout_seconds") or 60)
        rc, out, err = runner(["/bin/sh", "-c", command], cwd=source, timeout=timeout)
        row["command"] = command
        row["exit"] = rc
        row["ok"] = rc == 0
        tail = (out or err).strip().splitlines()
        row["detail"] = tail[-1] if tail else f"exit {rc}"
        rows.append(row)
    return rows


def collect_readiness_audit(
    *,
    modules_root: Path = DEFAULT_MODULES_ROOT,
    runner: Callable[..., tuple[int, str, str]] = run_command,
    module_name: str = "spark-telegram-bot",
    strict_script: str = "r30:loop-readiness:strict",
) -> dict[str, Any]:
    """Run the STRICT readiness audit (no --allow-incomplete) and record it as a gate row.

    r30 shipped on the permissive variant (--allow-incomplete downgrades not-ready to exit 0,
    doc 21 §1.2). Doc 33 §4.5: readiness audits run without --allow-incomplete at ship; an
    incomplete audit is red or waived. A missing module/script is red (fail closed, waivable).
    """
    name = "readiness_audit_strict"
    source = modules_root / module_name / "source"
    package_json = source / "package.json"
    if not package_json.is_file():
        return {"name": name, "ok": False, "detail": f"{module_name} source not installed at {source}"}
    try:
        scripts = (json.loads(package_json.read_text(encoding="utf-8")) or {}).get("scripts") or {}
    except (OSError, json.JSONDecodeError) as exc:
        return {"name": name, "ok": False, "detail": f"package.json unreadable: {exc}"}
    script_body = str(scripts.get(strict_script) or "")
    if not script_body:
        return {"name": name, "ok": False, "detail": f"strict script {strict_script!r} not declared"}
    if "--allow-incomplete" in script_body:
        return {
            "name": name,
            "ok": False,
            "detail": f"{strict_script!r} carries --allow-incomplete; strict means strict",
        }
    rc, out, err = runner(["npm", "run", strict_script], cwd=source, timeout=600)
    tail = (out or err).strip().splitlines()
    return {
        "name": name,
        "ok": rc == 0,
        "exit": rc,
        "detail": tail[-1] if tail else f"exit {rc}",
    }


# ---------------------------------------------------------------------------
# capture write (the committed ship-harness half)
# ---------------------------------------------------------------------------


def _default_verify_runner(repo_root: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    src = repo_root / "src"
    if src.is_dir():
        env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "spark_cli.cli", "verify", "--r30", "--json"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", f"could not run verify --r30: {exc}"
    return result.returncode, result.stdout, result.stderr


def _canonical_builder_state_db(system_map_path: Path = DEFAULT_SYSTEM_MAP_PATH) -> str:
    """The estate has three files named state.db (env-forked homes); pin the canonical one."""
    try:
        payload = json.loads(system_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown (system-map.json unreadable)"
    node = payload.get("builder_state_db")
    if isinstance(node, dict) and node.get("path"):
        return str(node["path"])
    return "unknown (builder_state_db not in system-map)"


def write_release_gate_capture(
    *,
    repo_root: Path,
    artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT,
    installed_path: Path = DEFAULT_INSTALLED_PATH,
    modules_root: Path = DEFAULT_MODULES_ROOT,
    verify_runner: Callable[[Path], tuple[int, str, str]] = _default_verify_runner,
    git_runner: Callable[..., tuple[int, str, str]] = _run_git,
    command_runner: Callable[..., tuple[int, str, str]] = run_command,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the release gate and persist a hash-stamped capture into the ship artifact.

    Returns {"ok", "capture_path", "capture"} — "ok" is the capture's overall verdict, not
    whether writing succeeded (a write failure raises; silence is never success).
    """
    now = now or _utc_now()
    gate_map, gate_map_error = load_gate_map(repo_root)
    rc, out, err = verify_runner(repo_root)
    try:
        verify_payload = json.loads(out) if out.strip() else {}
    except json.JSONDecodeError:
        verify_payload = {}
    verify_row = {
        "name": "verify_r30",
        "ok": bool(verify_payload.get("ok")),
        "detail": f"exit {rc}; {sum(1 for c in verify_payload.get('checks', []) if not c.get('ok'))} red checks"
        if verify_payload
        else f"verify --r30 produced no parseable payload (exit {rc}): {err.strip()[:200]}",
    }
    # A present-but-corrupt installed.json must NOT degrade to {} — that would silently drop every
    # chip-gate and module git-state row from the table while overall_ok stays green (fail-open).
    installed_row: dict[str, Any] | None = None
    if not installed_path.exists():
        installed = {}
        installed_row = {"name": "installed_registry", "ok": False, "detail": f"installed.json absent at {installed_path} — no module registry to gate over", "source": "harness"}
    else:
        try:
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            if not isinstance(installed, dict):
                raise json.JSONDecodeError("installed.json is not an object", "", 0)
        except (OSError, json.JSONDecodeError) as exc:
            installed = {}
            installed_row = {"name": "installed_registry", "ok": False, "detail": f"installed.json unreadable ({exc}) — chip gates cannot be enumerated", "source": "harness"}

    git_state = collect_git_state(
        repo_root, modules_root=modules_root, installed=installed, git_runner=git_runner
    )
    chip_rows = collect_chip_gates(
        modules_root=modules_root, installed=installed, runner=command_runner
    )
    readiness = collect_readiness_audit(modules_root=modules_root, runner=command_runner)

    gates_table: list[dict[str, Any]] = [verify_row]
    for check in verify_payload.get("checks", []) or []:
        gates_table.append(
            {
                "name": str(check.get("name")),
                "ok": bool(check.get("ok")),
                "detail": str(check.get("detail", "")),
                "source": "verify_r30",
            }
        )
    if installed_row is not None:
        gates_table.append(installed_row)
    gates_table.append({"name": git_state["name"], "ok": git_state["ok"], "detail": git_state["detail"], "source": "harness"})
    for row in chip_rows:
        gates_table.append({**{k: row[k] for k in ("name", "ok", "detail") if k in row}, "source": "chip"})
    gates_table.append({"name": readiness["name"], "ok": readiness["ok"], "detail": readiness["detail"], "source": "harness"})

    if gate_map is None:
        gate_code = {"tree_hash": None, "error": gate_map_error, "file_count": 0}
        fixtures = {"tree_hash": None, "file_count": 0}
        gates_table.append({"name": "gate_map_present", "ok": False, "detail": gate_map_error, "source": "harness"})
    else:
        gate_code = gate_code_tree_hash(repo_root, gate_map)
        fixtures = evidence_tree_hash(repo_root, gate_map)
        gates_table.append(
            {
                "name": "gate_map_present",
                "ok": True,
                "detail": f"{gate_code['file_count']} gate-code + {fixtures['file_count']} evidence files hashed",
                "source": "harness",
            }
        )

    overall_ok = all(bool(row.get("ok")) for row in gates_table)
    release = str(verify_payload.get("release") or UNKNOWN_RELEASE)
    capture = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "provenance": "computed",
        "captured_at": _iso(now),
        "release": release,
        "overall_ok": overall_ok,
        "gates_table": gates_table,
        "verify": {"exit_code": rc, "payload": verify_payload},
        "git_state": git_state,
        "chip_gates": chip_rows,
        "readiness_audit": readiness,
        "gate_code": {k: v for k, v in gate_code.items() if k != "files"},
        "gate_code_files": gate_code.get("files", {}),
        "fixtures": {k: v for k, v in fixtures.items() if k != "files"},
        "fixture_files": fixtures.get("files", {}),
        "paths": {
            "repo_root": str(repo_root.resolve()),
            "artifacts_root": str(artifacts_root.resolve()),
            "registry_json": str((repo_root / "registry.json").resolve()),
            "installer_manifest": str((repo_root / "scripts" / "installer-manifest.json").resolve()),
            "builder_state_db": _canonical_builder_state_db(),
        },
    }

    train_dir = artifacts_root / release
    train_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%dT%H%M%SZ")
    capture_path = train_dir / f"{CAPTURE_FILE_PREFIX}{stamp}.json"
    capture_path.write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")

    link = artifacts_root / LATEST_CAPTURE_LINK
    tmp_link = artifacts_root / (LATEST_CAPTURE_LINK + ".tmp")
    try:
        if tmp_link.is_symlink() or tmp_link.exists():
            tmp_link.unlink()
        tmp_link.symlink_to(capture_path)
        tmp_link.replace(link)
    except OSError:
        (artifacts_root / (LATEST_CAPTURE_LINK + ".json")).write_text(
            json.dumps({"path": str(capture_path)}) + "\n", encoding="utf-8"
        )
    return {"ok": overall_ok, "capture_path": str(capture_path), "capture": capture}


# ---------------------------------------------------------------------------
# waiver ledger (doc 33 §2 / spark-waiver.v1, doc 40 §3.6)
# ---------------------------------------------------------------------------


def load_waivers(train_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Load waivers.json; malformed entries are reported and IGNORED (fail closed)."""
    path = train_dir / "waivers.json"
    if not path.exists():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"waivers.json unreadable: {exc}"]
    entries = payload if isinstance(payload, list) else payload.get("waivers") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return [], ["waivers.json must be a list of spark-waiver.v1 entries (or {waivers: [...]})"]
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"waiver[{index}] is not an object")
            continue
        extra = set(entry) - set(WAIVER_REQUIRED_FIELDS)
        missing = [f for f in WAIVER_REQUIRED_FIELDS if not str(entry.get(f) or "").strip()]
        if missing:
            errors.append(f"waiver[{index}] missing/empty fields: {', '.join(missing)}")
            continue
        if extra:
            errors.append(f"waiver[{index}] has undeclared fields: {', '.join(sorted(extra))} (additionalProperties: false)")
            continue
        try:
            date.fromisoformat(str(entry["expiry"]))
        except ValueError:
            errors.append(f"waiver[{index}] expiry is not an ISO date: {entry['expiry']!r}")
            continue
        valid.append(entry)
    return valid, errors


def _waiver_covers(
    waiver: dict[str, Any], *, check_name: str, release: str, captured_at: datetime, now: datetime
) -> tuple[bool, str]:
    if waiver["check"] != check_name:
        return False, "check name mismatch"
    if waiver["release"] != release:
        return False, f"waiver is for release {waiver['release']!r}, capture is {release!r} (never carries forward)"
    expiry = datetime.combine(date.fromisoformat(str(waiver["expiry"])), datetime.max.time(), tzinfo=timezone.utc)
    if expiry < now:
        return False, f"waiver expired {waiver['expiry']} (an expired waiver counts as red)"
    if expiry > captured_at + timedelta(days=WAIVER_MAX_DAYS):
        return False, f"waiver expiry exceeds {WAIVER_MAX_DAYS} days from capture (33 §2)"
    return True, "valid"


# ---------------------------------------------------------------------------
# the refusal (doc 33 §1: mechanically blocked, fail closed, no --force)
# ---------------------------------------------------------------------------


def _resolve_latest_capture(artifacts_root: Path) -> Path | None:
    link = artifacts_root / LATEST_CAPTURE_LINK
    if link.is_symlink() or link.exists():
        try:
            target = link.resolve()
            if target.is_file():
                return target
        except OSError:
            pass
    pointer = artifacts_root / (LATEST_CAPTURE_LINK + ".json")
    if pointer.is_file():
        try:
            candidate = Path(json.loads(pointer.read_text(encoding="utf-8"))["path"])
            if candidate.is_file():
                return candidate
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    # Fallback: newest by embedded timestamp (filename), NOT by full path — a later train
    # dirname must not shadow a chronologically newer capture in another train.
    candidates = sorted(artifacts_root.glob(f"*/{CAPTURE_FILE_PREFIX}*.json"), key=lambda p: p.name)
    return candidates[-1] if candidates else None


def evaluate_release_gate(
    *,
    repo_root: Path,
    artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT,
    capture_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decide whether the gated actions are permitted. Fail-closed on every uncertainty."""
    now = now or _utc_now()
    checks: list[dict[str, Any]] = []

    def refuse(reason: str) -> dict[str, Any]:
        return {"permitted": False, "reason": reason, "checks": checks, "summary": "release gate: REFUSED"}

    capture_file = capture_path or _resolve_latest_capture(artifacts_root)
    if capture_file is None:
        checks.append({"name": "capture_present", "ok": False, "detail": f"no {CAPTURE_FILE_PREFIX}*.json under {artifacts_root} — the hook fails closed without a capture"})
        return refuse("no verify capture found")
    checks.append({"name": "capture_present", "ok": True, "detail": str(capture_file)})

    try:
        capture = json.loads(capture_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        checks.append({"name": "capture_valid", "ok": False, "detail": f"capture unreadable: {exc}"})
        return refuse("capture unreadable")
    if capture.get("schema_version") != CAPTURE_SCHEMA_VERSION:
        checks.append({"name": "capture_valid", "ok": False, "detail": f"unexpected schema_version {capture.get('schema_version')!r}"})
        return refuse("capture schema mismatch")
    try:
        captured_at = datetime.strptime(str(capture.get("captured_at")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        checks.append({"name": "capture_valid", "ok": False, "detail": "captured_at is not an ISO-8601 UTC timestamp"})
        return refuse("capture timestamp invalid")
    checks.append({"name": "capture_valid", "ok": True, "detail": f"{CAPTURE_SCHEMA_VERSION} captured {capture.get('captured_at')}"})

    gate_map, gate_map_error = load_gate_map(repo_root)
    if gate_map is None:
        checks.append({"name": "gate_code_fresh", "ok": False, "detail": gate_map_error})
        return refuse("gate-map missing — cannot verify capture freshness")
    recorded_hash = (capture.get("gate_code") or {}).get("tree_hash")
    current_hash = gate_code_tree_hash(repo_root, gate_map)["tree_hash"]
    if not recorded_hash or recorded_hash != current_hash:
        checks.append({
            "name": "gate_code_fresh",
            "ok": False,
            "detail": "gate code changed since this capture (d7fc1df rule, 33 §3) — rerun capture"
            if recorded_hash
            else "capture carries no gate-code tree hash",
        })
        return refuse("capture is stale (gate code edited since capture)")
    checks.append({"name": "gate_code_fresh", "ok": True, "detail": f"tree hash {current_hash[:12]} unchanged"})

    # doc 33 §1 rule 1: a gate FIXTURE change since the capture invalidates it too. Advancing a pin
    # (editing registry.json) after a green capture must force a fresh capture, or a stale green
    # would keep permitting a state it never verified.
    recorded_fixture = (capture.get("fixtures") or {}).get("tree_hash")
    current_fixture = evidence_tree_hash(repo_root, gate_map)["tree_hash"]
    if not recorded_fixture or recorded_fixture != current_fixture:
        checks.append({
            "name": "fixtures_fresh",
            "ok": False,
            "detail": "release evidence (registry.json / installer manifest / R30 docs) changed since this capture (33 §1) — rerun capture"
            if recorded_fixture
            else "capture carries no evidence-fixture hash",
        })
        return refuse("capture is stale (release evidence changed since capture)")
    checks.append({"name": "fixtures_fresh", "ok": True, "detail": f"evidence hash {current_fixture[:12]} unchanged"})

    release = str(capture.get("release") or UNKNOWN_RELEASE)
    if release == UNKNOWN_RELEASE:
        # verify produced no determinable train (reddens verify_row already); an undeterminable
        # release can neither be shipped nor waived — a waiver must name a real train (33 §2).
        checks.append({"name": "release_determinable", "ok": False, "detail": "capture has no determinable release train"})
        return refuse("capture release is undeterminable — cannot ship or waive")
    gates_table = capture.get("gates_table") or []
    red_rows = [row for row in gates_table if not row.get("ok")]
    if not gates_table:
        checks.append({"name": "capture_verdict", "ok": False, "detail": "capture has an empty gates table — nothing was verified"})
        return refuse("capture records no gate results")
    if capture.get("overall_ok") and not red_rows:
        checks.append({"name": "capture_verdict", "ok": True, "detail": "capture green"})
        return {"permitted": True, "reason": "latest capture green", "checks": checks, "summary": "release gate: PERMITTED (green capture)"}
    if not capture.get("overall_ok") and not red_rows:
        checks.append({"name": "capture_verdict", "ok": False, "detail": "capture is internally inconsistent (overall_ok false but no red rows) — refusing"})
        return refuse("capture internally inconsistent")

    waivers, waiver_errors = load_waivers(capture_file.parent)
    for error in waiver_errors:
        checks.append({"name": "waiver_ledger", "ok": False, "detail": error})
    unwaived: list[str] = []
    for row in red_rows:
        name = str(row.get("name"))
        covered = False
        for waiver in waivers:
            ok, _ = _waiver_covers(waiver, check_name=name, release=release, captured_at=captured_at, now=now)
            if ok:
                covered = True
                break
        if covered:
            checks.append({"name": f"waived:{name}", "ok": True, "detail": "valid per-check waiver on record"})
        else:
            unwaived.append(name)
    if unwaived:
        checks.append({
            "name": "capture_verdict",
            "ok": False,
            "detail": "red without waiver: " + ", ".join(sorted(unwaived)),
        })
        return refuse(f"{len(unwaived)} red check(s) carry no valid waiver — fix and re-capture, or write per-check spark-waiver.v1 entries in {capture_file.parent / 'waivers.json'}")
    checks.append({"name": "capture_verdict", "ok": True, "detail": f"all {len(red_rows)} red checks carry valid waivers"})
    return {"permitted": True, "reason": "every red check waived per-check", "checks": checks, "summary": "release gate: PERMITTED (waived)"}


# ---------------------------------------------------------------------------
# push classification (the pre-push hook's brain)
# ---------------------------------------------------------------------------


def _pushed_changed_paths(
    repo_root: Path,
    local_sha: str,
    remote_sha: str,
    git_runner: Callable[..., tuple[int, str, str]],
) -> tuple[set[str] | None, str]:
    """The set of repo-relative paths this push introduces, or (None, error) if undiffable.

    - Existing ref update (remote_sha known): a full-tree `git diff remote_sha..local_sha`.
    - New ref (remote_sha == 0): enumerate the commits this push adds that are not already on any
      remote (`rev-list local_sha --not --remotes`), then diff EACH against its parent(s) with
      `git diff-tree -m` (per-parent). `-m` is essential: a merge that brings registry.json onto a
      fresh release branch verbatim from a feature parent shows NOTHING under `git show`'s combined
      diff, but IS changed relative to the other (main) parent — closing the merge-hides-pin bypass.
    """
    if remote_sha != ZERO_SHA:
        rc, out, err = git_runner(["-C", str(repo_root), "diff", "--name-only", f"{remote_sha}..{local_sha}"])
        if rc != 0:
            return None, err.strip()[:160]
        return {line.strip() for line in out.splitlines() if line.strip()}, ""

    rc, out, err = git_runner(["-C", str(repo_root), "rev-list", local_sha, "--not", "--remotes"])
    if rc != 0:
        return None, err.strip()[:160]
    changed: set[str] = set()
    for commit in [line.strip() for line in out.splitlines() if line.strip()]:
        rc_dt, out_dt, err_dt = git_runner(
            ["-C", str(repo_root), "diff-tree", "-r", "-m", "--name-only", "--no-commit-id", commit]
        )
        if rc_dt != 0:
            return None, err_dt.strip()[:160]
        changed.update(line.strip() for line in out_dt.splitlines() if line.strip())
    return changed, ""


def classify_push(
    lines: list[str],
    *,
    repo_root: Path,
    git_runner: Callable[..., tuple[int, str, str]] = _run_git,
) -> dict[str, Any]:
    """Classify a pre-push ref list into gated actions (G1/G2/G4). Unknowable diffs fail closed.

    Every ref (branch OR tag) is content-scanned for gated paths — a tag that advances a pin or
    changes an installer file is gated even if its name is not a release-tag pattern; a release
    tag is additionally G2 by name.
    """
    actions: list[dict[str, str]] = []
    errors: list[str] = []
    for raw in lines:
        parts = raw.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, remote_sha = parts
        if local_sha == ZERO_SHA:
            continue  # ref deletion: not a publication of new content
        if any(pattern.match(remote_ref) for pattern in GATED_TAG_PATTERNS):
            actions.append({"kind": "G2", "detail": f"release tag push {remote_ref}"})
        changed, diff_err = _pushed_changed_paths(repo_root, local_sha, remote_sha, git_runner)
        if changed is None:
            errors.append(f"could not diff {remote_ref}: {diff_err}")
            actions.append({"kind": "G1", "detail": f"{remote_ref}: change set unknowable — failing closed"})
            actions.append({"kind": "G4", "detail": f"{remote_ref}: change set unknowable — failing closed"})
            continue
        for path in sorted(changed & set(G1_GATED_PATHS)):
            actions.append({"kind": "G1", "detail": f"{remote_ref} touches {path} (registry pin advance)"})
        for path in sorted(changed & set(G4_GATED_PATHS)):
            actions.append({"kind": "G4", "detail": f"{remote_ref} touches {path} (installer manifest)"})
    return {"gated": bool(actions), "actions": actions, "errors": errors}


# ---------------------------------------------------------------------------
# CLI (runnable standalone: python -m spark_cli.release_gate ...)
# ---------------------------------------------------------------------------


def _print_checks(checks: list[dict[str, Any]]) -> None:
    for check in checks:
        marker = "[OK]" if check.get("ok") else "[FIX]"
        print(f"{marker} {check.get('name')}: {check.get('detail')}")


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "registry.json").exists() and (candidate / "scripts").is_dir():
            return candidate
    return here.parents[2]


def cmd_capture(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _discover_repo_root()
    artifacts_root = Path(args.artifacts_root) if args.artifacts_root else DEFAULT_ARTIFACTS_ROOT
    result = write_release_gate_capture(repo_root=repo_root, artifacts_root=artifacts_root)
    capture = result["capture"]
    if args.json:
        print(json.dumps({"ok": result["ok"], "capture_path": result["capture_path"], "release": capture["release"]}, indent=2))
    else:
        print(f"capture written: {result['capture_path']}")
        _print_checks(capture["gates_table"])
        print(f"overall: {'GREEN' if result['ok'] else 'RED'}")
    return 0 if result["ok"] else 1


def cmd_check(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _discover_repo_root()
    artifacts_root = Path(args.artifacts_root) if args.artifacts_root else DEFAULT_ARTIFACTS_ROOT
    verdict = evaluate_release_gate(repo_root=repo_root, artifacts_root=artifacts_root)
    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        _print_checks(verdict["checks"])
        print(verdict["summary"] + " — " + verdict["reason"])
    return 0 if verdict["permitted"] else 1


def cmd_hook_check(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _discover_repo_root()
    artifacts_root = Path(args.artifacts_root) if args.artifacts_root else DEFAULT_ARTIFACTS_ROOT
    lines = [line for line in sys.stdin.read().splitlines() if line.strip()]
    classification = classify_push(lines, repo_root=repo_root)
    if not classification["gated"]:
        return 0
    print("release-gate: this push performs gated action(s):", file=sys.stderr)
    for action in classification["actions"]:
        print(f"  [{action['kind']}] {action['detail']}", file=sys.stderr)
    verdict = evaluate_release_gate(repo_root=repo_root, artifacts_root=artifacts_root)
    if verdict["permitted"]:
        print(f"release-gate: {verdict['reason']} — push permitted", file=sys.stderr)
        return 0
    for check in verdict["checks"]:
        if not check.get("ok"):
            print(f"  [FIX] {check['name']}: {check['detail']}", file=sys.stderr)
    print(
        "release-gate: REFUSED — " + verdict["reason"] + "\n"
        "There is no --force. Fix and run `spark release-gate capture`, or write per-check\n"
        "spark-waiver.v1 entries (33 §2) in the train's waivers.json.",
        file=sys.stderr,
    )
    return 1


def cmd_install_hooks(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _discover_repo_root()
    hook = repo_root / "scripts" / "hooks" / "pre-push"
    if not hook.is_file():
        print(f"hook source missing: {hook}", file=sys.stderr)
        return 2
    rc, out, err = _run_git(["-C", str(repo_root), "config", "core.hooksPath", "scripts/hooks"])
    if rc != 0:
        print(f"could not set core.hooksPath: {err.strip()}", file=sys.stderr)
        return 2
    os.chmod(hook, 0o755)
    print(f"core.hooksPath -> scripts/hooks (pre-push armed) in {repo_root}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="spark release-gate", description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=None, help="spark-cli repo root (default: discovered)")
    parser.add_argument(
        "--artifacts-root", default=None, help=f"ship-artifact root (default: {DEFAULT_ARTIFACTS_ROOT})"
    )
    sub = parser.add_subparsers(dest="release_gate_command", required=True)
    capture_parser = sub.add_parser("capture", help="Run the release gate and persist a hash-stamped capture")
    capture_parser.add_argument("--json", action="store_true")
    capture_parser.set_defaults(func=cmd_capture)
    check_parser = sub.add_parser("check", help="Evaluate whether gated actions are permitted (fail-closed)")
    check_parser.add_argument("--json", action="store_true")
    check_parser.set_defaults(func=cmd_check)
    hook_parser = sub.add_parser("hook-check", help="pre-push entrypoint: classify stdin refs, refuse red-gate pushes")
    hook_parser.set_defaults(func=cmd_hook_check)
    install_parser = sub.add_parser("install-hooks", help="Deliberately arm the pre-push hook (sets core.hooksPath)")
    install_parser.set_defaults(func=cmd_install_hooks)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
