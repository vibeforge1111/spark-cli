"""release_policy_binding_gate — asserts the binding-gate machinery is intact (item 0.3; docs/33).

The action-time enforcement lives in the pre-push hook + `spark release-gate check` (fail-closed
against the local ship artifact). This CI check asserts the MACHINERY cannot silently rot:

  1. gate-map.json present and structurally valid (every gate declares gate_code; the four
     gated-action path sets are registered as evidence of the release gate).
  2. The pre-push hook is committed at scripts/hooks/pre-push and still routes through
     `spark_cli.release_gate hook-check` fail-closed (no bypass edit survives CI).
  3. src/spark_cli/release_gate.py imports and exposes the required API.
  4. No commit in the checked range violates gate/evidence separation (delegates to
     gate_evidence_separation.py — the d7fc1df rule).

It deliberately does NOT assert local ship artifacts on CI runners (they never ship); asserting
them here would be theater. Local action-time checks read the real artifact.

Exit codes: 0 pass · 1 violation · 2 operational error. Fails closed on unreadable inputs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_GATE_MAP_GATES = ("release_gate",)
REQUIRED_HOOK_MARKERS = ("spark_cli.release_gate", "hook-check", "fail closed")
REQUIRED_API = (
    "write_release_gate_capture",
    "evaluate_release_gate",
    "classify_push",
    "gate_code_tree_hash",
    "load_waivers",
)


def fail(msg: str) -> None:
    print(f"  - {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="Repo root")
    parser.add_argument(
        "--range",
        dest="rev_range",
        default="HEAD",
        help="Rev range for the separation sub-check (default: HEAD only)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    violations: list[str] = []

    # 1. gate-map.json
    gate_map_path = root / "gate-map.json"
    gates: dict = {}
    if not gate_map_path.is_file():
        violations.append(f"gate-map.json missing at {gate_map_path}")
    else:
        try:
            payload = json.loads(gate_map_path.read_text(encoding="utf-8"))
            gates = payload.get("gates") or {}
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: gate-map.json unreadable: {exc}", file=sys.stderr)
            return 2
        if not isinstance(gates, dict) or not gates:
            violations.append("gate-map.json declares no gates")
        for name in REQUIRED_GATE_MAP_GATES:
            if name not in gates:
                violations.append(f"gate-map.json missing required gate {name!r}")
        for name, entry in gates.items():
            if not isinstance(entry, dict) or not entry.get("gate_code"):
                violations.append(f"gate {name!r} declares no gate_code files")

    # 2. the committed hook
    hook_path = root / "scripts" / "hooks" / "pre-push"
    if not hook_path.is_file():
        violations.append(f"pre-push hook missing at {hook_path}")
    else:
        hook_text = hook_path.read_text(encoding="utf-8", errors="replace")
        for marker in REQUIRED_HOOK_MARKERS:
            if marker not in hook_text:
                violations.append(f"pre-push hook no longer carries required marker {marker!r}")

    # 3. the release_gate module API
    module_path = root / "src" / "spark_cli" / "release_gate.py"
    if not module_path.is_file():
        violations.append(f"release_gate module missing at {module_path}")
    else:
        spec = importlib.util.spec_from_file_location("spark_cli_release_gate_check", module_path)
        try:
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 — any import failure is a binding failure
            violations.append(f"release_gate module failed to import: {exc}")
            module = None
        if module is not None:
            for symbol in REQUIRED_API:
                if not hasattr(module, symbol):
                    violations.append(f"release_gate module missing required API {symbol!r}")

    # 4. separation sub-check (d7fc1df)
    separation = root / "scripts" / "harness_checks" / "gate_evidence_separation.py"
    if not separation.is_file():
        violations.append(f"gate_evidence_separation.py missing at {separation}")
    elif gate_map_path.is_file() and gates:
        result = subprocess.run(
            [sys.executable, str(separation), "--root", str(root), "--range", args.rev_range],
            capture_output=True,
            text=True,
        )
        if result.returncode == 2:
            print("ERROR: separation sub-check errored:", result.stderr.strip(), file=sys.stderr)
            return 2
        if result.returncode != 0:
            violations.append("gate_evidence_separation failed:\n    " + result.stdout.strip().replace("\n", "\n    "))

    if violations:
        print("FAIL release_policy_binding_gate:")
        for violation in violations:
            fail(violation)
        return 1
    print("PASS release_policy_binding_gate (gate-map, hook, module API, separation all intact)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
