"""gate_evidence_separation — the d7fc1df rule as a CI check (item 0.3; docs/33 §3).

No commit may modify a gate's code and the evidence/fixtures/manifests that gate evaluates
together. r30's commit d7fc1df relaxed a gate check together with its authored input manifest
and its tests, mid-ship (research-repo docs/21 §1.1); this check makes that class of commit
fail CI instead of landing silently.

The registration lives in gate-map.json at the repo root: per gate, `gate_code` globs
(the code that decides) and `evidence` globs (the inputs it judges). A commit whose diff
touches both sides of the SAME gate is a violation. Legitimate co-evolution is done as two
commits — gate first, evidence second (33 §3).

Exit codes (mirrors line_count_gate.py): 0 pass · 1 violation · 2 operational error.
Fails closed: an unreadable gate-map or an undiffable commit is an error, never a pass.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

GATE_MAP_FILENAME = "gate-map.json"


def load_gate_map(root: Path) -> dict:
    path = root / GATE_MAP_FILENAME
    if not path.is_file():
        raise SystemExit(f"ERROR: {path} not found (a gate without a gate-map entry fails the binding gate)")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {GATE_MAP_FILENAME} unreadable: {exc}", file=sys.stderr)
        sys.exit(2)
    gates = payload.get("gates")
    if not isinstance(gates, dict) or not gates:
        print(f"ERROR: {GATE_MAP_FILENAME} declares no gates", file=sys.stderr)
        sys.exit(2)
    return gates


def run_git(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR: git {' '.join(args)} failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return result.stdout


def commit_files(root: Path, commit: str) -> list[str]:
    out = run_git(root, ["show", "--name-only", "--pretty=format:", commit])
    return [line.strip() for line in out.splitlines() if line.strip()]


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def check_commit(commit: str, files: list[str], gates: dict) -> list[str]:
    violations: list[str] = []
    for gate_name, entry in gates.items():
        gate_code = entry.get("gate_code") or []
        evidence = entry.get("evidence") or []
        touched_code = sorted(p for p in files if matches(p, gate_code))
        touched_evidence = sorted(p for p in files if matches(p, evidence))
        if touched_code and touched_evidence:
            violations.append(
                f"{commit[:12]} touches gate {gate_name!r} code ({', '.join(touched_code)}) "
                f"AND its evidence ({', '.join(touched_evidence)}) in one commit — split into "
                f"two commits, gate first (d7fc1df rule, 33 §3)"
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="Repo root containing gate-map.json")
    parser.add_argument(
        "--range",
        dest="rev_range",
        default="HEAD",
        help="Rev range to check (e.g. origin/master..HEAD); default: HEAD only",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    gates = load_gate_map(root)

    if ".." in args.rev_range:
        out = run_git(root, ["rev-list", "--no-merges", args.rev_range])
        commits = [line.strip() for line in out.splitlines() if line.strip()]
    else:
        commits = [run_git(root, ["rev-parse", args.rev_range]).strip()]

    all_violations: list[str] = []
    for commit in commits:
        all_violations.extend(check_commit(commit, commit_files(root, commit), gates))

    if all_violations:
        print("FAIL gate_evidence_separation:")
        for violation in all_violations:
            print(f"  - {violation}")
        return 1
    print(f"PASS gate_evidence_separation ({len(commits)} commit(s), {len(gates)} gate(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
