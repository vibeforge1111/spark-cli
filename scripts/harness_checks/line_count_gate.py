#!/usr/bin/env python3
"""
line_count_gate.py - Harness Discipline checker for R-21 (god-file CI gate).

Enforces maintainability redline #8: no source file over HARD_CAP lines, with a
RATCHET so known-oversized files may only shrink (never grow) and no NEW file may
cross the cap. This is the cheapest Wave-0 checker (see docs/harness-discipline/
00_README.md "where to start" and 04 W0.1).

Ratchet semantics (the god-file census is monotonically non-increasing):
  FAIL if a file NOT in the baseline exceeds HARD_CAP (a new god-file), OR a
  baselined file's line count is GREATER than its recorded baseline (growth).
  PASS otherwise; a baselined file at/under its baseline is fine (shrinking is good).

This checker is itself bound by the ruleset it enforces: it FAILS CLOSED (a
corrupt baseline or unreadable file is a violation, never a silent 0) and surfaces
every violation with its real count - it never returns a success-shaped result on
error (RL-08).

Usage:
  line_count_gate.py --root <repo>                 # check (exit 1 on violation)
  line_count_gate.py --root <repo> --update        # (re)write the baseline
  line_count_gate.py --root <repo> --baseline <p>  # custom baseline path
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HARD_CAP = 3000   # redline #8: no file over 3000 lines without owner + refactor plan
WARN_CAP = 1500   # redline #8: no module over 1500 lines without an extraction ticket
SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "vendor", "__pycache__",
    "ts-dist", "ts-dist-esm", ".venv", "venv", ".pytest_cache",
    ".mypy_cache", "coverage", ".next", "out", "egg-info",
}
IGNORE_SUFFIX = (".min.js", ".d.ts", ".bundle.js")


def count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return -1  # unreadable -> surfaced as a violation, never silently 0


def scan(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_EXT:
            continue
        parts = p.relative_to(root).parts
        if any(part in IGNORE_DIRS or part.endswith(".egg-info") for part in parts):
            continue
        if p.name.endswith(IGNORE_SUFFIX):
            continue
        counts[str(p.relative_to(root))] = count_lines(p)
    return counts


def load_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("offenders", {})
    except (OSError, ValueError) as exc:
        # Fail closed: never proceed with an empty baseline on a corrupt file.
        print(f"ERROR: baseline {path} is unreadable/corrupt: {exc}", file=sys.stderr)
        sys.exit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description="R-21 god-file line-count ratchet gate")
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--baseline", type=Path, default=None)
    ap.add_argument("--update", action="store_true", help="rewrite baseline from current state")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: --root {root} is not a directory", file=sys.stderr)
        return 2
    baseline_path = args.baseline or (Path(__file__).parent / "line_count_baseline.json")

    counts = scan(root)
    unreadable = sorted(p for p, n in counts.items() if n < 0)

    if args.update:
        offenders = {p: n for p, n in sorted(counts.items()) if n > WARN_CAP}
        baseline_path.write_text(
            json.dumps(
                {"hard_cap": HARD_CAP, "warn_cap": WARN_CAP, "root": root.name,
                 "offenders": offenders},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {baseline_path} ({len(offenders)} files > {WARN_CAP} lines)")
        for p, n in sorted(offenders.items(), key=lambda kv: -kv[1])[:10]:
            flag = "  <-- over HARD_CAP" if n > HARD_CAP else ""
            print(f"   {n:>6}  {p}{flag}")
        return 0

    baseline = load_baseline(baseline_path)
    violations: list[str] = []
    warnings: list[str] = []

    for p, n in sorted(counts.items()):
        if n < 0:
            continue
        base = baseline.get(p)
        if base is None:
            if n > HARD_CAP:
                violations.append(f"NEW god-file  {n:>6} (> {HARD_CAP})  {p}")
            elif n > WARN_CAP:
                warnings.append(f"new file over warn cap  {n:>6} (> {WARN_CAP})  {p}")
        elif n > base:
            violations.append(f"GREW  {base} -> {n}  (baselined offender must not grow)  {p}")

    for p in unreadable:
        violations.append(f"UNREADABLE (cannot verify size)  {p}")

    if warnings:
        print("warnings (not blocking; each needs an extraction ticket - R-21):")
        for w in warnings:
            print("  WARN  " + w)

    if violations:
        print("\nR-21 LINE-COUNT GATE: FAIL")
        for v in violations:
            print("  FAIL  " + v)
        print(
            f"\n{len(violations)} violation(s). The god-file census must be monotonically "
            f"non-increasing. Shrink the file, or - if the growth is intentional and carries "
            f"an owner + refactor plan - update the baseline with --update as a reviewed change."
        )
        return 1

    shrunk = [(p, baseline[p], counts[p]) for p in baseline if p in counts and counts[p] < baseline[p]]
    print(
        f"R-21 LINE-COUNT GATE: PASS  ({len(baseline)} baselined god-files, "
        f"{len(shrunk)} shrinking, 0 growing, 0 new over cap)"
    )
    for p, b, n in sorted(shrunk, key=lambda t: t[1] - t[2], reverse=True)[:5]:
        print(f"   shrank {b} -> {n}  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
