# Spark R30 Owner Handoff Packet

Date: 2026-06-27
Status: owner-source handoff packet, no pushes/tags/deploys performed

## Purpose

This packet turns the R30 source-owner audit into concrete owner-lane work. It records the exact local ranges that must be reviewed, ported, pushed, or replaced with equivalent owner-source commits before registry pins or installer manifests can move.

R30 is still blocked until these handoffs are source-owned and verified.

## Required Order

1. Review and port/push owner-source commits.
2. Re-run each repo's local proof gate on the owner lane.
3. Update installed runtimes from the owner-source commits.
4. Update `registry.json` pins and attestations.
5. Run Spark OS, registry, provenance, Telegram, and installer gates.
6. Only then prepare the R30 installer manifest/scripts and hosted metadata.

## Handoff Matrix

| Repo | Local range to review | Current public/owner truth | R30 handoff |
| --- | --- | --- | --- |
| `spark-telegram-bot` | `e5a1bd040986..64408560dcf2` | registry/tag `spark-ship-2026-06-22` at `e5a1bd040986`; no owner branch for `harness-discipline-line-count-gate` found | Port or push the reliability ladder, release-packet, line-count, and publish-handoff stack. Then rerun Telegram gates before registry pin movement. |
| `spawner-ui` | `origin/release/stability-2026-06-02-spawner-authority..0a892f0bcdaf` | owner branch `fdb8fded4744`; registry/tag `spark-ship-2026-06-22` at `19b7d0bff144` | Port or push the nine PRD proof-continuity commits and merge resolution. Then rerun Spawner proof/check gates. |
| `spark-voice-comms` | `origin/codex/turnintent-voice-policy-20260531..7555a363d763` | owner branch `12bddc9bd0bd`; remote tag `spark-ship-2026-06-26` at `c74490d68ece`; registry pin `21a9467e9bd4` | Port/tag the two local trace/governor commits before any R30 voice registry claim. Do not pin R30 to `c74490d` if R30 claims current Spark OS voice proof. |
| `domain-chip-memory` | `origin/codex/turnintent-memory-boundary-20260531..1fd272e519b5` | owner branch `3116ccaa3977`; registry/tag `spark-ship-2026-06-22` at `f7f16a6ea8ee` | Review/push the vNext memory write authority proof or replace with equivalent owner-source proof. |
| `spark-intelligence-builder` | `origin/codex/turnintent-builder-boundary-20260531..f21522accf66` | owner branch `c94eac853fed`; registry/tag `spark-ship-2026-06-22` at `e7f80fbf03bd` | Review/push or rebase the 43-commit trace/proof/media/memory stack. Keep the historical high-severity lifecycle family visible until closed by source-owned evidence. |
| `spark-cli` | local R30 prep commits through `65b9be9` | hosted R29 tag `7751ef43581c`; local installer manifest/scripts remain R28 | Include R30 docs and voice source-discovery fix in the source release before installer pins move. |

## R30 Gate Classification

`spark verify --r30 --json` now classifies release-lane registry/runtime issue
rows so owner handoffs can be sequenced without hiding broader drift.

Direct R30 blockers:

- `domain-chip-memory`: review/push the vNext memory write authority proof or replace it with equivalent owner-source proof before registry movement.
- `spark-intelligence-builder`: review/push or rebase the Builder trace/proof stack, then keep the historical trace lifecycle visible or close it with owner evidence.
- `spark-telegram-bot`: port or push the Telegram reliability ladder/release-packet stack, then rerun Telegram gates before registry pin movement.
- `spark-voice-comms`: port/tag the local voice trace/governor commits or equivalent owner-source proof before any R30 voice registry claim.
- `spawner-ui`: port or push the Spawner PRD proof-continuity commits, then rerun Spawner checks before registry pin movement.

Supporting release-hygiene rows:

- `domain-chip-spark-qa-evidence-lane`: converge owner source and installed metadata before claiming full Spark-wide publish truth.
- `spark-character`: converge owner source and installed runtime metadata before claiming full Spark-wide publish truth.
- `spark-harness-core`: converge owner source and installed runtime metadata before claiming full Spark-wide publish truth.
- `spark-researcher`: converge owner source and installed runtime metadata before claiming full Spark-wide publish truth.
- `spark-skill-graphs`: converge owner source and installed metadata before claiming the optional-module lane ship-ready.

All ten rows still block public installer truth until registry, installed
runtime metadata, and owner-source refs converge.

The same actions are emitted by `spark verify --r30 --json` under
`release_lane_classification`.

The structured handoff form is [R30 owner handoff manifest](./R30_OWNER_HANDOFF_MANIFEST_2026-06-27.json).
`spark verify --r30 --json` checks that the manifest matches the live
release-lane classification and commit metadata.

Fresh local proof status for direct blockers:

- `domain-chip-memory`: proof command passed.
- `spark-intelligence-builder`: focused proof tests passed.
- `spark-telegram-bot`: reliability, build, and line-count gates passed.
- `spark-voice-comms`: pytest passed.
- `spawner-ui`: Svelte check passed.

These are local proof passes, not owner-source convergence. Registry and
installer truth must not move until the corresponding owner-source refs exist
and installed metadata is updated through the normal path.

## Exact Commit Lists

### `spark-telegram-bot`

Range: `e5a1bd0409865ddb3024c15ed35ccd0038e31776..64408560dcf249d221f40598dde910a84b7eae12`

Top commits currently in the R30 handoff stack:

- `6440856 Refresh Spark publish readiness handoffs`
- `caa28b5 Refresh Spark publish handoff status`
- `a0aa855 Classify publish readiness handoffs`
- `856c504 Package Telegram control release evidence`
- `b630ae2 Shrink mission relay formatting tests`
- `50784d4 Document Spark publish readiness handoffs`
- `ccea930 Refresh cleanup canary runtime evidence`
- `beabc6d Record line-count ratchet checkpoint`
- `5cf5eac Refresh full canary runtime evidence`
- `f4e8683 Supersede stale duplicate safe prompt rows`

Minimum owner-lane proof after port:

```bash
npm run control:proof:reliability
npm run build
npm run check:line-count
```

### `spawner-ui`

Range: `origin/release/stability-2026-06-02-spawner-authority..0a892f0bcdaf9c9a956d054a6bfee16d29608df7`

Commits:

- `0a892f0b Merge remote-tracking branch 'origin/release/stability-2026-06-02-spawner-authority' into release/stability-2026-06-02-spawner-authority`
- `e9ba42eb Document PRD event proof joins`
- `40396d24 Join PRD event trace proof`
- `56671b10 Carry PRD bridge proof capsules`
- `53d424a7 Add Spawner PRD proof continuity repair`
- `1a2fe0d2 Add Spawner PRD trace redaction repair`
- `0adc4880 Mark missing PRD Harness proof gaps`
- `95d5b3ee Redact PRD trace path refs`
- `42454743 Carry Harness proof refs in PRD traces`

Minimum owner-lane proof after port:

```bash
npm run check
```

Run any focused PRD/proof-continuity tests used by the owner lane before registry pin movement.

### `spark-voice-comms`

Range: `origin/codex/turnintent-voice-policy-20260531..7555a363d7638537b1a9ec1ee377e460d2343323`

Commits:

- `8a246af Join voice runtime state traces`
- `7555a36 Accept media transcription governor authority`

Proof captured locally:

- Remote tag `spark-ship-2026-06-26` at `c74490d68ece`: `PYTHONPATH=src python3 -m pytest -q` -> `121 passed`
- Installed local branch at `7555a363d763`: `PYTHONPATH=src python3 -m pytest -q` -> `80 passed`

Minimum owner-lane proof after port:

```bash
PYTHONPATH=src python3 -m pytest -q
spark os compile --json
```

Expected Spark OS voice result after install/update:

- `voice_surface_mode=duplex`
- `voice_surface_blockers=0`
- `can_trigger_actions=false`
- `requires_confirmation_for_actions=true`

### `domain-chip-memory`

Range: `origin/codex/turnintent-memory-boundary-20260531..1fd272e519b562afc118ca46ff7da175d735dc44`

Commit:

- `1fd272e Accept vNext memory write authority proof`

Minimum owner-lane proof after port:

```bash
PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts
```

Run the SDK authority tests used by the memory owner lane before registry pin movement.

### `spark-intelligence-builder`

Range: `origin/codex/turnintent-builder-boundary-20260531..f21522accf6687596244f516555d37ffb69200c9`

The range is large: 43 commits covering Builder trace/proof repairs, media transcription authority, memory route cadence, historical trace handoff docs, and the final memory authority reconciliation.

Representative terminal commits:

- `f21522a Reconcile Builder memory authority after merge`
- `40c4a8e Merge remote-tracking branch 'origin/codex/turnintent-builder-boundary-20260531' into codex/turnintent-builder-boundary-20260531`
- `3cf59ec Join historical trace handoff evidence`
- `a72cc74 Document trace health historical handoffs`
- `2f54280 Separate historical trace health handoffs`
- `8617cc9 Preserve Harness proof refs in Builder traces`

Minimum owner-lane proof after port:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py
```

Keep this separate from the historical lifecycle close. The remaining Builder lifecycle family is still:

- component: `telegram_runtime`
- event type: `tool_call_ledger_recorded`
- status/severity: `blocked` / `high`
- latest event: `2026-06-02 09:03:25`
- current 1h and 24h high-open counts: `0`

## Registry And Installer Rule

Do not update `registry.json`, `installed.json`, `scripts/installer-manifest.json`, `scripts/install.sh`, or `scripts/install.ps1` from this handoff packet alone.

Those files can move only after owner-source commits exist remotely and the corresponding local proof gates pass from the source-owner lane.

## Final R30 Gate After Owner Handoffs

```bash
spark os compile --json
spark live status --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json
```

From `spark-telegram-bot`:

```bash
npm run control:proof:reliability
npm run build
npm run check:line-count
```

After authorized hosted publication only:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --hosted-installers --json
```
