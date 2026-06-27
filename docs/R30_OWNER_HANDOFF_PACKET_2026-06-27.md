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
| `spark-telegram-bot` | `e5a1bd040986..4a630b3e72bd` | registry/tag `spark-ship-2026-06-22` at `e5a1bd040986`; no owner branch for `harness-discipline-line-count-gate` found | Port or push the reliability ladder, release-packet, line-count, publish-handoff, `/access 5` activation proof stack, Level 5 Codex sandbox confirmation fix, effective sandbox Telegram surface proof, read-only contradiction full-access copy block, effective Level 5 sandbox-before-operator-claims guard, and Level 5 status sandbox guard. Then rerun Telegram gates before registry pin movement. |
| `spawner-ui` | `origin/release/stability-2026-06-02-spawner-authority..7110dce4030a` | owner branch `fdb8fded4744`; registry/tag `spark-ship-2026-06-22` at `19b7d0bff144` | Port or push the PRD proof-continuity stack plus direct-client and PRD-lane Level 5 Codex sandbox fixes. Then rerun Spawner proof/check gates. |
| `spark-voice-comms` | `origin/codex/turnintent-voice-policy-20260531..7555a363d763` | owner branch `12bddc9bd0bd`; remote tag `spark-ship-2026-06-26` at `c74490d68ece`; registry pin `21a9467e9bd4` | Port/tag the two local trace/governor commits before any R30 voice registry claim. Do not pin R30 to `c74490d` if R30 claims current Spark OS voice proof. |
| `domain-chip-memory` | `origin/codex/turnintent-memory-boundary-20260531..1fd272e519b5` | owner branch `3116ccaa3977`; registry/tag `spark-ship-2026-06-22` at `f7f16a6ea8ee` | Review/push the vNext memory write authority proof or replace with equivalent owner-source proof. |
| `spark-intelligence-builder` | `origin/codex/turnintent-builder-boundary-20260531..f21522accf66` | owner branch `c94eac853fed`; registry/tag `spark-ship-2026-06-22` at `e7f80fbf03bd` | Review/push or rebase the 43-commit trace/proof/media/memory stack. Keep the historical high-severity lifecycle family visible until closed by source-owned evidence. |
| `spark-cli` | current `harness-discipline-ruleset` head from `git rev-parse HEAD` plus the R29 baseline alignment and hosted-publication contract | hosted R29 tag `7751ef43581c`; local installer manifest/scripts now match R29 | Include R30 docs, live-status gate, Access 5 sandbox gate with `live_level5_env_files_all_profiled_services_full_access` plus `effective_codex_sandbox`, `r30_unattended_identity_guard`, local runtime artifact handoff gate, voice runtime truth gate with `requires_confirmation_for_actions=true`, publication-order `source_truth_blockers`, `r30_hosted_publication_contract`, and voice source-discovery fix in the source release before installer pins move to R30. |

## Local Runtime Artifact Patch Inventory

These two owners are the current `local_runtime_test_artifacts` family. The
structured inventory is also recorded in
[R30 local runtime artifacts handoff manifest](./R30_LOCAL_RUNTIME_ARTIFACTS_HANDOFF_MANIFEST_2026-06-27.json).

| Repo | Exact range | Commits | Files changed | Boundary commits | Owner-lane command |
| --- | --- | ---: | ---: | --- | --- |
| `spark-telegram-bot` | `e5a1bd0409865ddb3024c15ed35ccd0038e31776..4a630b3e72bdbb761a8a85af437a0751e0854723` | 995 | 323 | first `43aeb4e476b9` / last `4a630b3e72bd` | `git log --reverse --oneline e5a1bd0409865ddb3024c15ed35ccd0038e31776..4a630b3e72bdbb761a8a85af437a0751e0854723` |
| `spawner-ui` | `origin/release/stability-2026-06-02-spawner-authority..7110dce4030a700ad61460ab79be7eff8312f06c` | 11 | 17 | first `424547437e7e` / last `7110dce4030a` | `git log --reverse --oneline origin/release/stability-2026-06-02-spawner-authority..7110dce4030a700ad61460ab79be7eff8312f06c` |

Do not squash these into registry truth from this debugging lane. The owner
lane should inspect the exact range, decide whether to push or cherry-pick, run
the listed proof commands on the owner ref, and only then move installed
metadata and registry pins.

## R30 Gate Classification

`spark verify --r30 --json` now classifies release-lane registry/runtime issue
rows so owner handoffs can be sequenced without hiding broader drift.

Direct R30 blockers:

- `domain-chip-memory`: review/push the vNext memory write authority proof or replace it with equivalent owner-source proof before registry movement.
- `spark-intelligence-builder`: review/push or rebase the Builder trace/proof stack, then keep the historical trace lifecycle visible or close it with owner evidence.
- `spark-telegram-bot`: port or push the Telegram reliability ladder/release-packet stack plus the `/access 5` activation proof, Level 5 Codex sandbox confirmation fix, effective sandbox Telegram surface proof, read-only contradiction full-access copy block, effective Level 5 sandbox-before-operator-claims guard, and Level 5 status sandbox guard, then rerun Telegram gates before registry pin movement.
- `spark-voice-comms`: port/tag the local voice trace/governor commits or equivalent owner-source proof before any R30 voice registry claim.
- `spawner-ui`: port or push the Spawner PRD proof-continuity commits plus direct-client and PRD-lane Level 5 Codex sandbox fixes, then rerun Spawner checks before registry pin movement.

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

The Telegram and Spawner local runtime artifact handoff form is
[R30 local runtime artifacts handoff manifest](./R30_LOCAL_RUNTIME_ARTIFACTS_HANDOFF_MANIFEST_2026-06-27.json).
`spark verify --r30 --json` checks that those owner names, local heads,
installed registry commits, and proof commands match live release-lane evidence.

Fresh local proof status for direct blockers:

- `domain-chip-memory`: proof command passed.
- `spark-intelligence-builder`: focused proof tests passed.
- `spark-telegram-bot`: reliability, build, and line-count gates passed.
- `spark-voice-comms`: pytest passed.
- `spawner-ui`: focused Codex sandbox lane tests and Svelte check passed.

These are local proof passes, not owner-source convergence. Registry and
installer truth must not move until the corresponding owner-source refs exist
and installed metadata is updated through the normal path.

## Owner-Lane Command Checklist

These commands are for the owner lane after authorization. They are written so
an owner can inspect and prepare a handoff without accidentally changing public
truth. Do not push from this debugging lane without explicit authorization.

### `spark-telegram-bot`

```bash
cd ~/.spark/modules/spark-telegram-bot/source
git fetch origin --tags
git status --short --branch
git log --oneline e5a1bd0409865ddb3024c15ed35ccd0038e31776..4a630b3e72bdbb761a8a85af437a0751e0854723
npm run control:proof:reliability
npm run build
npm run check:line-count
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts
```

Owner action after review: push or port the
`e5a1bd040986..4a630b3e72bd` reliability ladder and access activation stack into an owner release ref,
then update registry truth only after the proof commands pass on that owner ref.

### `spawner-ui`

```bash
cd ~/.spark/modules/spawner-ui/source
git fetch origin --tags
git status --short --branch
git log --oneline origin/release/stability-2026-06-02-spawner-authority..7110dce4030a700ad61460ab79be7eff8312f06c
npm test -- --run src/lib/server/prd-auto-dispatch.test.ts src/routes/api/prd-bridge/write/clarification-policy.test.ts src/lib/server/provider-clients/codex-cli-client.test.ts src/lib/services/spark-agent-bridge.test.ts src/lib/server/provider-clients/spark-harness-client.test.ts src/lib/server/high-agency-workers.test.ts
npm run check
```

Owner action after review: push or port the Spawner PRD proof-continuity stack
and the direct-client and PRD-lane Level 5 Codex sandbox fixes into the owner release lane, then update
registry truth only after `npm run check` passes on that owner ref.

### `spark-voice-comms`

```bash
cd ~/.spark/modules/spark-voice-comms/source
git fetch origin --tags
git status --short --branch
git log --oneline origin/codex/turnintent-voice-policy-20260531..7555a363d7638537b1a9ec1ee377e460d2343323
PYTHONPATH=src python3 -m pytest -q
spark os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```

Owner action after review: port or push
`8a246af1eb0732aec432d88e4e4c2b6411023b7c` and
`7555a363d7638537b1a9ec1ee377e460d2343323`, or equivalent source-owned
trace/governor commits, before any R30 voice registry claim. Do not pin R30
voice to `c74490d68ece` if R30 claims the current Spark OS voice proof.

### `domain-chip-memory`

```bash
cd ~/.spark/modules/domain-chip-memory/source
git fetch origin --tags
git status --short --branch
git log --oneline origin/codex/turnintent-memory-boundary-20260531..1fd272e519b562afc118ca46ff7da175d735dc44
PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts
```

Owner action after review: push or replace the vNext memory authority proof with
equivalent owner-source evidence before registry movement.

### `spark-intelligence-builder`

```bash
cd ~/.spark/modules/spark-intelligence-builder/source
git fetch origin --tags
git status --short --branch
git log --oneline origin/codex/turnintent-builder-boundary-20260531..f21522accf6687596244f516555d37ffb69200c9
PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py
```

Owner action after review: push, port, or rebase the Builder trace/proof stack.
Keep the historical high-severity trace lifecycle explicit unless owner-source
closure evidence is added.

After any owner-source movement, return to `spark-cli` and rerun:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
spark os compile --json
```

## Exact Commit Lists

### `spark-telegram-bot`

Range: `e5a1bd0409865ddb3024c15ed35ccd0038e31776..4a630b3e72bdbb761a8a85af437a0751e0854723`

Top commits currently in the R30 handoff stack:

- `0279193 Block Level 5 full-access copy on read-only sandbox`
- `4a630b3 Harden Telegram Level 5 sandbox status`
- `28aecd8 Require effective Level 5 sandbox before operator claims`
- `4856174 Surface effective Level 5 sandbox in Telegram`
- `729273e Fix Level 5 Codex sandbox confirmation`
- `fa4c888 Prove Telegram Level 5 activation path`
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

Required terminal subjects that must survive owner-source porting:

- `Add Telegram rich draft streaming controls`
- `Package Telegram control release evidence`
- `Prove Telegram Level 5 activation path`
- `Fix Level 5 Codex sandbox confirmation`
- `Surface effective Level 5 sandbox in Telegram`
- `Block Level 5 full-access copy on read-only sandbox`
- `Require effective Level 5 sandbox before operator claims`
- `Harden Telegram Level 5 sandbox status`

Minimum owner-lane proof after port:

```bash
npm run control:proof:reliability
npm run build
npm run check:line-count
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts
```

### `spawner-ui`

Range: `origin/release/stability-2026-06-02-spawner-authority..7110dce4030a700ad61460ab79be7eff8312f06c`

Commits:

- `7110dce4 Honor Level 5 sandbox in PRD Codex lanes`
- `5ae5387d Honor Level 5 Codex sandbox in direct client`
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
npm test -- --run src/lib/server/prd-auto-dispatch.test.ts src/routes/api/prd-bridge/write/clarification-policy.test.ts src/lib/server/provider-clients/codex-cli-client.test.ts src/lib/services/spark-agent-bridge.test.ts src/lib/server/provider-clients/spark-harness-client.test.ts src/lib/server/high-agency-workers.test.ts
npm run check
```

Run any focused PRD/proof-continuity tests used by the owner lane before registry pin movement.

### `spark-voice-comms`

Range: `origin/codex/turnintent-voice-policy-20260531..7555a363d7638537b1a9ec1ee377e460d2343323`

Commits:

- `8a246af1eb0732aec432d88e4e4c2b6411023b7c` (`8a246af Join voice runtime state traces`)
- `7555a363d7638537b1a9ec1ee377e460d2343323` (`7555a36 Accept media transcription governor authority`)

Proof captured locally:

- Remote tag `spark-ship-2026-06-26` at `c74490d68ece`: `PYTHONPATH=src python3 -m pytest -q` -> `121 passed`
- Installed local branch at `7555a363d763`: `PYTHONPATH=src python3 -m pytest -q` -> `80 passed`

Minimum owner-lane proof after port:

```bash
PYTHONPATH=src python3 -m pytest -q
spark os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```

Expected Spark OS voice result after install/update:

- `voice_surface_mode=egress`
- `voice_surface_blockers=1`
- `voice_surface_blocker`: voice transcription is not ready
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

### `spark-cli`

Current R30 prep head: run `git rev-parse HEAD` in `~/.spark/tools/spark-cli`
from the source-owner release lane. Do not copy an old debugging-lane commit
hash into release truth.

Recent R30 prep commits to include before any R30 installer pin movement:

- `11385e6 Gate R30 unattended identity smoke`
- `d9ecaec Clarify Level 5 effective sandbox proof`
- `7e490a5 Gate R30 Level 5 named profile restarts`
- `7478f0d Require Level 5 proof per Telegram profile`
- `6d1a6f1 Refresh R30 local proof evidence`
- `0680654 Gate R30 CLI handoff clauses`
- `5be9bb2 Expose R30 publication source blockers`
- `7e577a1 Gate R30 voice action confirmation truth`
- `5b15978 Track R30 runtime handoff inventory`
- `34f0c34 Gate R30 local runtime handoffs`
- `5743974 Gate R30 voice owner handoff manifest`
- `4ef05fc Refresh R30 CLI owner handoff`
- `788e9d9 Gate R30 access and voice truth`
- `35bdbb3 Gate R30 on live status proof`
- `ec59e5e Report current R30 voice runtime truth`
- `bedeed1 Use module source path for live healthchecks`
- `39e1341 Add R30 Access 5 sandbox gate`

Minimum source-lane proof before installer pin movement:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_access.py tests/test_cli.py -k 'access_level5_service_proof or access_level5_transition or level5 or r30_access_level5_codex_sandbox or r30_voice_runtime_truth or r30_release_gate or r30_live_status or r30_voice_registry_decision or r30_builder_trace_lifecycle'
PYTHONPATH=src python3 -m spark_cli.cli os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json
```

Expected before registry/installer movement: the focused tests pass, OS compile
is green, Access 5 and voice runtime truth checks pass inside the R30 gate, and
the R30 gate still blocks on owner-source, registry, and installer truth until
those surfaces converge. Access 5 proof must include `missing_or_stale_services=[]`
for all named Telegram profiles and `effective_codex_sandbox=danger-full-access`
for the service lane. The final live access payload must also report
`effective_access_level=5` and `service_can_operate_whole_computer=true`; do not
accept a module-level Telegram restart, green env files alone, or a stale
current-process sandbox as proof that SparkRecursive/SparkQA-style bot profiles
are writable.

Keep this separate from the historical lifecycle close. The remaining Builder lifecycle family is carried as explicit historical release debt and is still:

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
