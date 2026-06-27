# Spark R30 Owner Convergence Queue

Date: 2026-06-28
Status: operational handoff queue, not a publication record

This queue turns the R30 owner audit into an execution order. It does not
authorize push, tag, deploy, registry pin, installed metadata, installer pin, or
hosted publication changes.

## Current Gate

Clean-tree `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` is
red only for release-truth work:

- `release_lane`: 5 direct R30 blockers and 5 supporting hygiene rows.
- `r30_voice_registry_decision`: voice needs source-owned trace/governor proof
  before registry movement.
- `registry_pins`: `spark-voice-comms` pin drift remains real.
- `r30_installer_pins`: installer pins intentionally remain on R29.

`publish_handoff_blockers.ok=true`: Telegram/Spawner local runtime artifacts
and Builder historical trace health are carried explicitly, not hidden.

## Direct Owner Queue

| Order | Module | Current public owner base | Local proof head | Registry/install truth | Owner action before registry |
| ---: | --- | --- | --- | --- | --- |
| 1 | `spark-voice-comms` | `main` / `spark-ship-2026-06-26` at `c74490d68ece`; owner branch `12bddc9bd0bd` | `c502ec096cef` on `release/r30-voice-trace-governor` | registry `21a9467e9bd4`; installed metadata `0d6e366fd04d` | Port/tag trace/governor commits or equivalent source-owned proof, then rerun voice and R30 gates. |
| 2 | `spark-telegram-bot` | `main` / `spark-ship-2026-06-26` at `67ad9e6ed297`; no matching owner branch for `harness-discipline-line-count-gate` | `bb38eca25cbe` | registry/installed `e5a1bd040986` | Port or push Telegram reliability, streaming/rich default, proof packet, line-count, `/access 5` proof stack, and the effective-sandbox-only Level 5 reply guard. |
| 3 | `spawner-ui` | `main` / `spark-ship-2026-06-26` at `451d009aad84`; owner release branch `fdb8fded4744` | `e0fbb5b60c22` | registry/installed `19b7d0bff144` | Port or push PRD proof-continuity, Level 5 Codex sandbox, and shared effective-env worker access/path validation fixes. |
| 4 | `domain-chip-memory` | `main` / `spark-ship-2026-06-26` at `72a660a69c0c`; owner branch `3116ccaa3977` | `1fd272e519b5` | registry/installed `f7f16a6ea8ee` | Review/push vNext memory write-authority proof or replace with equivalent owner-source proof. |
| 5 | `spark-intelligence-builder` | `main` / `spark-ship-2026-06-26` at `9d7bdefaa9a0`; owner branch `c94eac853fed` | `f21522accf66` | registry/installed `e7f80fbf03bd` | Review/push or rebase Builder trace/proof stack and keep historical trace lifecycle explicit. |

## Supporting Hygiene Queue

These rows must not block the first direct R30 control-layer convergence, but
they must stay visible before anyone claims Spark-wide publish truth across the
full 11-repo lane.

| Order | Module | Current public owner base | Local proof head | Registry/install truth | Owner action before Spark-wide publish |
| ---: | --- | --- | --- | --- | --- |
| 1 | `domain-chip-spark-qa-evidence-lane` | `main` at `4ea32635bf08`; reconcile branch `476644de047e` | `215c6b9cbefb` | registry `476644de047e`; installed metadata `fc1a8b42bdc7` | Decide whether the local `main` commit is source truth or reset/install back to the reconcile pin; then align installed metadata. |
| 2 | `spark-character` | `spark-ship-2026-06-26` at `8cad27624c4b`; registry tag `spark-ship-2026-06-22` at `6901e2e2ab0a` | `cf8177561c16` | registry/installed `6901e2e2ab0a` | Review the character-network-policy lane against the newer public tag before claiming character publish truth. |
| 3 | `spark-harness-core` | `main` at `a78c5bb2137a`; registry tag `v1.0.0-rc.2` at `71e564b36b93` | `b190986996f0` | registry/installed `71e564b36b93` | Decide whether the charter-link lane should become owner release truth or return runtime to the registry tag. |
| 4 | `spark-researcher` | `main` / `spark-ship-2026-06-26` at `9ac089dd791c`; registry tag `spark-ship-2026-06-22` at `906592e2bb02` | `587dbd2a57d6` | registry/installed `906592e2bb02` | Review the self-edit-governor lane against the current public tag before claiming researcher publish truth. |
| 5 | `spark-skill-graphs` | `main` at `bc30ee37b646`; reconcile branch `59c211afc6f0` | `8dcdd172f35f` | registry `59c211afc6f0`; installed metadata `8dcdd172f35f` | Resolve the split where installed metadata follows local `main` but registry still points at reconcile. |

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
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts
```

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
