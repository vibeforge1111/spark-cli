# Spark R30 Owner Convergence Queue

Date: 2026-06-28
Status: operational handoff queue, not a publication record

This queue turns the R30 owner audit into an execution order. It does not
authorize push, tag, deploy, registry pin, installed metadata, installer pin, or
hosted publication changes.

## Current Gate

Clean-tree `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` is
red only for release-truth work. Rechecked from `spark-cli` head
`ee365439bea2739dfbade928a07cd57ebf1165af`; dirty release repo count remained
`0`, OS compile stayed green, the owner handoff manifest stayed aligned, and
the Access 5 anti-read-only gate stayed green.

The current blocker set is still exactly `release_lane`,
`r30_voice_registry_decision`, and `registry_pins`.

- `release_lane`: 5 direct R30 blockers and 0 supporting hygiene rows.
- `r30_voice_registry_decision`: voice needs source-owned trace/governor proof
  before registry movement.
- `registry_pins`: `spark-voice-comms` pin drift remains real.
- `r30_installer_pins`: installer pins intentionally remain on R29.

`publish_handoff_blockers.ok=true`: Telegram/Spawner local runtime artifacts
and Builder historical trace health are carried explicitly, not hidden.

Current `release_lane` mismatches from the same gate:

| Class | Module | Local head | Registry truth | Installed metadata | Issues |
| --- | --- | --- | --- | --- | --- |
| Direct R30 | `spark-voice-comms` | `c502ec096cef` | `21a9467e9bd4` | `0d6e366fd04d` | `head_differs_from_registry`, `installed_metadata_differs_from_registry` |
| Direct R30 | `spark-telegram-bot` | `dec4b016148` | `e5a1bd040986` | `e5a1bd040986` | `head_differs_from_registry` |
| Direct R30 | `spawner-ui` | `3042f8acbdde` | `19b7d0bff144` | `19b7d0bff144` | `head_differs_from_registry` |
| Direct R30 | `domain-chip-memory` | `1fd272e519b5` | `f7f16a6ea8ee` | `f7f16a6ea8ee` | `head_differs_from_registry` |
| Direct R30 | `spark-intelligence-builder` | `f21522accf66` | `e7f80fbf03bd` | `e7f80fbf03bd` | `head_differs_from_registry` |

Fresh remote-ref audit confirmed the owner bases
listed below are still current. No remote `release/r30-voice-trace-governor`
or `harness-discipline-line-count-gate` owner branch exists yet.

## Direct Owner Queue

| Order | Module | Current public owner base | Local proof head | Registry/install truth | Owner action before registry |
| ---: | --- | --- | --- | --- | --- |
| 1 | `spark-voice-comms` | `main` / `spark-ship-2026-06-26` at `c74490d68ece`; owner branch `12bddc9bd0bd` | `c502ec096cef` on `release/r30-voice-trace-governor` | registry `21a9467e9bd4`; installed metadata `0d6e366fd04d` | Port/tag trace/governor commits or equivalent source-owned proof, then rerun voice and R30 gates. |
| 2 | `spark-telegram-bot` | `main` / `spark-ship-2026-06-26` at `67ad9e6ed297`; no matching owner branch for `harness-discipline-line-count-gate` | `dec4b016148` | registry/installed `e5a1bd040986` | Port or push Telegram reliability, streaming/rich default, proof packet, line-count, `/access 5` proof stack, effective-sandbox-only Level 5 reply guard, operator-chat Level 5 status proof, state-plus-temp runner preflight, effective Level 5 runtime-env promotion for Telegram and Recursive bridge subprocesses, health-token preservation, and active Telegram profile stale read-only env proof. |
| 3 | `spawner-ui` | `main` / `spark-ship-2026-06-26` at `451d009aad84`; owner release branch `fdb8fded4744` | `3042f8acbdde` | registry/installed `19b7d0bff144` | Port or push PRD proof-continuity, Level 5 Codex sandbox, shared effective-env worker access/path validation, and Codex worker env propagation fixes. |
| 4 | `domain-chip-memory` | `main` / `spark-ship-2026-06-26` at `72a660a69c0c`; owner branch `3116ccaa3977` | `1fd272e519b5` | registry/installed `f7f16a6ea8ee` | Review/push vNext memory write-authority proof or replace with equivalent owner-source proof. |
| 5 | `spark-intelligence-builder` | `main` / `spark-ship-2026-06-26` at `9d7bdefaa9a0`; owner branch `c94eac853fed` | `f21522accf66` | registry/installed `e7f80fbf03bd` | Review/push or rebase Builder trace/proof stack and keep historical trace lifecycle explicit. |
| 6 | `spark-cli` | remote R29 release tag `7751ef43581c`; remote `master` `a6738be7a97a` | `ee365439bea2` | local installer stays R29 until source/registry truth is green | Port/push R30 docs, voice discovery, publication-order gates, Access 5 anti-read-only verifier hardening, the refreshed Telegram Access 5 owner-handoff proof, the direct owner manifest patch gate, and the voice prepared-lane commit proof gate before installer pins move to R30. |

## Supporting Hygiene Queue

Supporting hygiene rows are clear in the current R30 gate. Keep them visible in
future audits, but do not spend the next owner-source cycle on stale supporting
rows while the five direct R30 blockers remain open.

## Required Proof Commands

Run these on the owner-source ref before changing registry pins.

### `spark-voice-comms`

```bash
PYTHONPATH=src python3 -m pytest -q
spark os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```

### `spark-telegram-bot`

```bash
npm run control:proof:reliability
npm run build
npm run check:line-count
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/recursiveLevel5RuntimeEnv.test.ts tests/telegramCommandAuthority.test.ts
```

Owner handoff patch artifact:

- `docs/r30/patches/r30-telegram-control-reliability-stack.patch`
- SHA256 `a1abe7e2ce57ae9d9ee5174b2511d97de83d94d71846936722a0150ea90ff72d`
- applies to public owner base `67ad9e6ed297baf6c9daa74b879fa45bc45bd579`
- produces tree `7e6a23e6b476cbea861dfede7373a8c631150952`, matching local proof head `dec4b0161482e9dd12df2480f348dcf7e4edacae`
- this is review/apply material only, not registry, tag, installer, or publication authority

### `spawner-ui`

```bash
npm test -- --run src/lib/server/prd-auto-dispatch.test.ts src/routes/api/prd-bridge/write/clarification-policy.test.ts src/lib/server/provider-clients/codex-cli-client.test.ts src/lib/services/spark-agent-bridge.test.ts src/lib/server/provider-clients/spark-harness-client.test.ts src/lib/server/high-agency-workers.test.ts
npm run check
```

### `domain-chip-memory`

```bash
PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts
```

### `spark-intelligence-builder`

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py
```

### Supporting Hygiene Repos

Until owner-specific proof commands are promoted, the Spark-wide hygiene proof is:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json
```

## After Owner Source Lands

Only after the relevant owner refs exist remotely and pass their proof commands:

1. Update installed runtime heads through the normal install/update path.
2. Update `registry.json` pins and provenance metadata.
3. Run `spark verify --registry-pins --json`.
4. Run `spark verify --r30 --json`.
5. Move R30 installer pins only when source truth and registry truth are green.
6. Publish hosted installer metadata only as the final authorized R30 batch.
