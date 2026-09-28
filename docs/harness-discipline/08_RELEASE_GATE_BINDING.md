# item 0.3 — Bind the ship gate (design of record, rev 2)

Spec: research-repo `docs/33-RELEASE-AND-VERSIONING-POLICY.md` §§1–4 (§7 jury/cooling-off = r31, NOT here);
plan `docs/18` item 0.3; `docs/22` §0.3; seam IC-10 (`docs/41`); schema homes `docs/40` §2 + §3.6.
DoD: **a red-gate deploy is structurally impossible.**
Estate map: `spark-loops-desktop/docs/ECOSYSTEM-DISK-MAP-2026-07-02.md`.

## The problem (verified on disk)
- `spark verify --r30` (cli.py:16975 → `collect_r30_release_gate_payload` :10157) is a pure reporter:
  computes `{ok, checks:[{name,ok,detail}]}`, prints, exits 0/1. Persists nothing, blocks nothing.
- The four gated actions have NO CLI chokepoint: G1 pins (`registry.json`), G2 `r*` tags, G4 installer
  files (`scripts/installer-manifest.json`, `install.sh`, `install.ps1`) are manual edits + `git push`
  (commits `f04b4a8`, `b2344a8`); G3 hosted deploy is out-of-band Railway → enforced transitively via G2+G4.
- No capture persistence, no waivers, no gate-map, no tree-hash, no hooks anywhere. r30 recorded
  `gates.verifyR30={exit:"1",ok:false}` and shipped anyway (pins advanced ~2h after the last red capture).
- Harness defects: blank `git-state-*.txt` when git absent (silent); chip gates ran as loose logs outside
  the roll-up gates table (`r30-ship-audit-summary.json` has 6 rows, no chip row; the `evaluate-builtin`
  argparse typo exited 2 and blocked nothing); readiness audit ran with `--allow-incomplete`
  (`spark-telegram-bot ops/r30LoopEngineeringReadinessAudit.ts:396,403`; permissive script wired at
  `package.json:44`, `:45` is `:strict`).

## Placement (per docs 40 §2 / 33 / operator steers)
- **Capture** = part of the existing **Ship artifact** family → `~/.spark/release-artifacts/<train>/`
  (+ maintain the `r30-ship-latest`-style `latest` symlink convention). NOT a new registry (invariant #2).
- **Waivers** = `spark-waiver.v1` (40 §3.6: check/release/reason/risk_accepted/expiry/signed_off_by,
  additionalProperties:false, expiry ≤30d, per-check per-release) → `~/.spark/release-artifacts/<train>/waivers.json`.
- **All gate tooling lives in spark-cli** (doc 33 owner surface: "spark-cli release tooling, pre-push hooks,
  the ship harness, registry.json, hosted installer manifest"). spark-compete is the community-PR RFP repo —
  NOT the canon home (operator, 2026-07-02). harness-core owns kernel/authority contracts, not release papers
  (pending agent confirmation; capture cites doc-33/40 ids either way).
- New code goes in **`src/spark_cli/release_gate.py`** + `scripts/harness_checks/*` — NOT into the
  20.5k-line cli.py god-file (doc 21 #9; line_count ratchet). cli.py gets only thin subcommand wiring.
- Capture **pins absolute canonical paths** (incl. the canonical barrel
  `~/.spark/state/spark-intelligence/state.db` via `system-map.json → builder_state_db.path`) — never
  "state.db" by convention (the barrel is env-forked ×3; see estate map).

## The pieces (this item)
1. **`src/spark_cli/release_gate.py`** — stdlib-only evaluator + capture writer. Public API (injectable
   kwargs for tests, mirroring `collect_registry_pin_drift_payload` style):
   - `gate_code_tree_hash(repo_root, gate_map)` — sha256 over the gate-map's registered gate-code files.
   - `write_release_gate_capture(payload, *, artifacts_root, repo_root, train)` — persists
     `release-gate-capture.json` (schema id `spark-release-gate-capture.v1`, provenance `computed`):
     the full verify payload + per-repo git-state (git-on-PATH asserted; absence/failure = a RED
     `git_state` harness check, never blank files) + merged gates table INCLUDING chip gates (an errored
     chip gate = red row, exit 2 = red row) + `allow_incomplete_detected` scan (any readiness-audit log
     produced with --allow-incomplete reddens `capture_integrity`) + `gate_code_tree_hash` + absolute
     canonical paths + capture timestamp. Updates `<artifacts_root>/latest` symlink.
   - `evaluate_release_gate(*, artifacts_root, repo_root, now)` → `{permitted, reason, checks:[...]}`.
     FAIL-CLOSED: no capture → refuse; unparseable → refuse; tree-hash mismatch (gate code edited since
     capture) → refuse (stale); any red check without a valid matching waiver → refuse. Waiver validity =
     spark-waiver.v1 shape + per-check + release matches train + not expired (expiry ≤30d from capture) +
     non-empty reason/risk_accepted/signed_off_by. Blanket/multi-check waivers invalid by construction
     (one entry names exactly one check).
   - `classify_push(ref_lines, changed_paths)` — G1 (registry.json), G2 (`r*` / `spark-*-r*` tags),
     G4 (installer manifest/scripts) detection for the hook.
2. **`gate-map.json`** (repo root) — registers gate code vs evidence per gate (33 §3): gate_code globs
   (release_gate.py, the verify collectors' file, harness_checks/*) vs evidence inputs (registry.json,
   installer files, docs/R30_*). Drives tree-hash + separation checks.
3. **`scripts/hooks/pre-push`** — thin sh → `python3 -m spark_cli.release_gate hook-check` (stdin refs).
   Fail-closed (missing python/module/capture = refuse). Installed deliberately via
   `spark release-gate install-hooks` (sets `core.hooksPath`) — NEVER auto-armed by this commit.
4. **`scripts/harness_checks/gate_evidence_separation.py`** — d7fc1df rule: for a commit range, no commit
   touches both a gate's code and that gate's evidence (per gate-map.json). Exit 0/1/2 per
   line_count_gate.py idiom.
5. **`scripts/harness_checks/release_policy_binding_gate.py`** — asserts the MACHINERY can't silently
   rot: gate-map present + structurally valid (every gate declares gate_code; `release_gate` present);
   the committed `scripts/hooks/pre-push` still carries the fail-closed gate invocation markers
   (`spark_cli.release_gate`, `hook-check`, `fail closed`) — a bypass edit to the hook fails CI;
   `src/spark_cli/release_gate.py` imports and exposes the required API; and no commit in range
   violates gate/evidence separation (delegates to `gate_evidence_separation.py`). It deliberately does
   NOT assert local ship artifacts (CI runners never ship — that would be theater; action-time checks
   read the real artifact). Exit 0/1/2.
6. **CLI wiring** (thin, in cli.py): `spark release-gate capture|check|hook-check|install-hooks`
   via `release_gate.py`'s functions; `verify --release-policy-binding` branch optional (defer if it
   bloats — the harness_checks scripts are the CI face).
7. **CI**: two steps in `.github/workflows/ci.yml` `test-and-audit`, named exactly
   `release_policy_binding_gate` and `gate_evidence_separation` (required-check names).
8. **Tests** in `tests/test_cli.py` `SparkCliTests` (unittest style, injectable kwargs):
   red-capture refusal · no-capture refusal (fail-closed) · stale-tree-hash refusal · valid-waiver permit ·
   expired/blanket/wrong-release waiver refusal · git-absent = red git_state (never blank) · chip-gate
   exit-2 = red row in table · allow-incomplete detection = red · classify_push G1/G2/G4 · separation
   violation detection (synthetic two-file commit).

### R-21 owner and extraction plan

- **Owner:** Spark CLI release tooling.
- **Reason for the reviewed baseline change:** retaining source commit `af68617` adds six lines of thin
  CLI wiring and its complete fail-closed regression matrix. The implementation itself remains in
  `src/spark_cli/release_gate.py`; no release-gate domain logic moved into `cli.py`.
- **Bounded follow-up:** the next release-gate test change must first move this matrix into
  `tests/test_release_gate.py` and return `tests/test_cli.py` to at most its prior 19,147-line
  baseline. No further growth of either baselined file is permitted before that extraction.

## Commit discipline (the d7fc1df rule applied to ITSELF)
- **Commit A**: gate machinery (release_gate.py, hooks, harness_checks, CLI wiring, tests, CI steps).
- **Commit B**: gate-map.json + any evidence-side registration (separate — a gate and its evidence never
  change in one commit; the separation checker must not be born violating itself).
- Never `git checkout <ref> -- <file>` with uncommitted work (banked lesson).

## Explicitly NOT in this commit (honest carry-forwards)
- Fixing the chip module's `evaluate-builtin` typo caller + the Telegram `--allow-incomplete` default:
  live in OTHER repos; the gate neutralizes both (errored gate = red row; permissive audit = red check).
  Noted for their repos' next touch.
- Jury + 24h cooling-off (33 §7) = r31 cut.
- Arming the hook on the operator's live clone = deliberate operator act post-merge.
- GitHub branch-protection required-check enrollment = operator act (needs repo admin).
- **The §2 consecutive-train ADR rule** ("a waiver on a check MUST NOT be re-issued for the same reason
  on >2 consecutive trains; the third requires an ADR") is NOT enforced — the evaluator judges one
  train's capture + waivers in isolation, so cross-train state (walking prior trains' `waivers.json`)
  is needed. Does not affect single-ship structural impossibility; disclosed here + in a code comment
  (`release_gate.py`) rather than silently dropped. Enforce when the r31 jury (§7) lands.

## Adversarial verification (3 lenses, before commit)
Bypass / fail-open / waiver-forgery lenses were run against the machinery. Five confirmed defects were
fixed and regression-tested: merge-commit-hidden pin advance on a new-branch push (`git diff-tree -m`
per-parent, closing the combined-diff blind spot); evidence-fixture staleness (a green capture no longer
permits after `registry.json` itself changes — 33 §1 rule 1); corrupt `installed.json` now reddens a
row instead of dropping chip gates; the G2 tag regex broadened to `r\d` (r31rc1/r31.1/r31-hotfix);
`unknown-release` captures are non-waivable. The design-doc overclaim about check 5 was corrected above.
