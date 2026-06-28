# Spark R30 Owner Handoff Packet

Date: 2026-06-27
Status: owner-source handoff packet, no pushes/tags/deploys performed

## Purpose

This packet turns the R30 source-owner audit into concrete owner-lane work. It records the exact local ranges that must be reviewed, ported, pushed, or replaced with equivalent owner-source commits before registry pins or installer manifests can move.

R30 is still blocked until these handoffs are source-owned and verified.

## Current Recheck

Fresh clean-tree recheck at `2026-06-28T05:54:09Z`:

- `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`: `ok=false`, by design.
- `source_truth_ready=false`.
- `source_truth_blockers=["release_lane","r30_voice_registry_decision","registry_pins"]`.
- `release_lane`: `0` dirty release repos; `5` direct R30 issues; `0` supporting hygiene rows.
- `r30_voice_registry_decision`: still blocked until the local voice trace/governor commits or equivalent proof are source-owned remotely.
- `registry_pins`: still red only because `spark-voice-comms` registry pin `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee` lags `refs/heads/main` at `c74490d68ece65ffad21dc5b88f44602e1afa703`.
- `r30_installer_pins`: intentionally still R29; installer pins must not move before source and registry truth are green.

The latest access/full-permission proof recorded in the evidence packet remains green: Telegram access/read-only focused tests passed, Spawner access/provider focused tests passed with `44 passed`, CLI Level 5 tests passed, live Access 5 reports `effective_codex_sandbox=danger-full-access`, and live Spawner Level 5 reports `level5_operator` / `automatic` / `auto_safe`.

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
| `spark-telegram-bot` | `e5a1bd040986..6f48013edb22` | remote `main` / `spark-ship-2026-06-26` at `67ad9e6ed297`; registry baseline tag `spark-ship-2026-06-22` at `e5a1bd040986`; no owner branch for `harness-discipline-line-count-gate` found | Port or push the reliability ladder, release-packet, line-count, publish-handoff, `/access 5` activation proof stack, Level 5 Codex sandbox confirmation fix, effective sandbox Telegram surface proof, read-only contradiction full-access copy block, effective Level 5 sandbox-before-operator-claims guard, Level 5 status sandbox guard, Level 5 proof gate, proof-oracle Level 5 runtime validation, effective-sandbox-only setup reply guard, operator-chat Level 5 status proof, state-plus-temp runner preflight, effective Level 5 runtime-env promotion for Telegram and Recursive bridge subprocesses, health-token preservation fix, active Telegram profile stale read-only env proof, startup profile-env refresh over stale read-only process env, Telegram Level 5 full-permission proof, the Level 5 full-permission audit doc, and natural confirmed Level 1/3/4 to Level 5 proof preservation onto the current owner release base. Then rerun Telegram gates before registry pin movement. |
| `spawner-ui` | `origin/release/stability-2026-06-02-spawner-authority..029c2086efcf` | owner branch `fdb8fded4744`; remote `main` / `spark-ship-2026-06-26` at `451d009aad84`; registry baseline tag `spark-ship-2026-06-22` at `19b7d0bff144` | Port or push the PRD proof-continuity stack plus direct-client, PRD-lane, persisted Level 5 Codex sandbox fixes, shared effective-env worker access/path validation, and Codex worker env propagation plus active Level 5 full-access lane classification onto the current owner release base. Then rerun Spawner proof/check gates. |
| `spark-voice-comms` | `origin/codex/turnintent-voice-policy-20260531..7555a363d763`; prepared local lane `release/r30-voice-trace-governor` at `c502ec096cef` | owner branch `12bddc9bd0bd`; remote `main` / `spark-ship-2026-06-26` at `c74490d68ece`; registry pin `21a9467e9bd4` | Local owner-lane port is prepared and test-clean, but not pushed/tagged or registry truth. Source-owner remote handoff, installed metadata, and registry convergence still block R30 voice publication. |
| `domain-chip-memory` | `origin/codex/turnintent-memory-boundary-20260531..1fd272e519b5` | owner branch `3116ccaa3977`; remote `main` / `spark-ship-2026-06-26` at `72a660a69c0c`; registry baseline tag `spark-ship-2026-06-22` at `f7f16a6ea8ee` | Review/push the vNext memory write authority proof against the current owner release base or replace with equivalent owner-source proof. |
| `spark-intelligence-builder` | `origin/codex/turnintent-builder-boundary-20260531..ca21e183c6c0` | owner branch `c94eac853fed`; remote `main` / `spark-ship-2026-06-26` at `9d7bdefaa9a0`; registry baseline tag `spark-ship-2026-06-22` at `e7f80fbf03bd` | Review/push or rebase the 44-commit trace/proof/media/memory stack against the current owner release base. Keep the historical high-severity lifecycle family visible until closed by source-owned evidence. |
| `spark-cli` | local docs/verifier lane on `harness-discipline-ruleset`; live head is verified by `git rev-parse HEAD` and `verify --r30`, with pre-refresh baseline `3bc788158c535b6a8eb0353e00797d11f39cd064` | hosted R29 tag `7751ef43581c`; local installer manifest/scripts now match R29; no R30 tag exists yet | Include R30 docs, live-status gate, Access 5 sandbox gate with `live_level5_env_files_all_profiled_services_full_access` plus `effective_codex_sandbox`, Telegram effective Level 5 runtime-env proof, Recursive bridge env-inheritance proof, active-profile stale read-only handoff proof, startup profile-env refresh over stale read-only process env, Telegram full-permission handoff proof, natural confirmed Level 1/3/4 to Level 5 proof preservation, refreshed Spawner active Level 5 full-access lane proof, `r30_unattended_identity_guard`, local runtime artifact handoff gate, direct owner patch handoff gate, executable owner handoff patch apply proof, voice prepared-lane commit proof gate, voice runtime truth gate with `requires_confirmation_for_actions=true`, publication-order `source_truth_blockers`, `r30_hosted_publication_contract`, hosted R29 baseline evidence, and voice source-discovery fix in the source release before installer pins move to R30. |

## Local Runtime Artifact Patch Inventory

These two owners are the current `local_runtime_test_artifacts` family. The
structured inventory is also recorded in
[R30 local runtime artifacts handoff manifest](./R30_LOCAL_RUNTIME_ARTIFACTS_HANDOFF_MANIFEST_2026-06-27.json).

| Repo | Exact range | Commits | Files changed | Boundary commits | Owner-lane command |
| --- | --- | ---: | ---: | --- | --- |
| `spark-telegram-bot` | `e5a1bd0409865ddb3024c15ed35ccd0038e31776..6f48013edb22fbf558735b59e11b95b3f0413584` | 1009 | 330 | first `43aeb4e476b9` / last `6f48013edb22` | `git log --reverse --oneline e5a1bd0409865ddb3024c15ed35ccd0038e31776..6f48013edb22fbf558735b59e11b95b3f0413584` |
| `spawner-ui` | `origin/release/stability-2026-06-02-spawner-authority..029c2086efcf48444865696333ccc6c756290d83` | 16 | 29 | first `424547437e7e` / last `029c2086efcf` | `git log --reverse --oneline origin/release/stability-2026-06-02-spawner-authority..029c2086efcf48444865696333ccc6c756290d83` |

Do not squash these into registry truth from this debugging lane. The owner
lane should inspect the exact range, decide whether to push or cherry-pick, run
the listed proof commands on the owner ref, and only then move installed
metadata and registry pins.

## R30 Gate Classification

`spark verify --r30 --json` now classifies release-lane registry/runtime issue
rows so owner handoffs can be sequenced without hiding broader drift.

Direct R30 blockers:

- `domain-chip-memory`: review/push the vNext memory write authority proof against the current owner release base or replace it with equivalent owner-source proof before registry movement.
- `spark-intelligence-builder`: review/push or rebase the Builder trace/proof stack against the current owner release base, then keep the historical trace lifecycle visible or close it with owner evidence.
- `spark-telegram-bot`: port or push the Telegram reliability ladder/release-packet stack plus the `/access 5` activation proof, Level 5 Codex sandbox confirmation fix, effective sandbox Telegram surface proof, read-only contradiction full-access copy block, effective Level 5 sandbox-before-operator-claims guard, Level 5 status sandbox guard, proof-oracle Level 5 runtime validation, effective-sandbox-only setup reply guard, operator-chat Level 5 status proof, state-plus-temp runner preflight, effective Level 5 runtime-env promotion for Telegram and Recursive bridge subprocesses, and the Level 5 full-permission audit doc onto the current owner release base, then rerun Telegram gates before registry pin movement.
- `spark-voice-comms`: port/tag the local voice trace/governor commits or equivalent owner-source proof before any R30 voice registry claim.
- `spawner-ui`: port or push the Spawner PRD proof-continuity commits plus direct-client, PRD-lane, persisted Level 5 Codex sandbox, shared effective-env worker access/path validation, and Codex worker env propagation fixes plus active Level 5 full-access lane classification onto the current owner release base, then rerun Spawner checks before registry pin movement.

Supporting release-hygiene rows are now converged locally through normal
`spark update <module> --skip-install-commands --skip-dirty --no-live-restart`
runs for QA Evidence Lane, Character, Harness Core, Researcher, and Skill
Graphs. The R30 release lane now has five direct rows and zero supporting rows.

The remaining five direct rows still block public installer truth until
registry, installed runtime metadata, and owner-source refs converge.

The same actions are emitted by `spark verify --r30 --json` under
`release_lane_classification`.

The structured handoff form is [R30 owner handoff manifest](./R30_OWNER_HANDOFF_MANIFEST_2026-06-27.json).
`spark verify --r30 --json` checks that the manifest matches the live
release-lane classification and commit metadata.
It also checks the direct-blocker `owner_refs` with live `git ls-remote` against
the fresh 2026-06-28 remote audit, including the absent Telegram
`harness-discipline-line-count-gate` owner branch and the absent voice
`release/r30-voice-trace-governor` remote branch, so owner-source porting does
not silently use stale public refs.

The Telegram and Spawner local runtime artifact handoff form is
[R30 local runtime artifacts handoff manifest](./R30_LOCAL_RUNTIME_ARTIFACTS_HANDOFF_MANIFEST_2026-06-27.json).
`spark verify --r30 --json` checks that those owner names, local heads,
installed registry commits, and proof commands match live release-lane evidence.
It also checks the local artifact `owner_refs` for Telegram and Spawner against
the same fresh 2026-06-28 remote audit, including absent candidate branches as
`null`, so local runtime artifact convergence cannot be replayed against stale
owner refs.

Fresh local proof status for direct blockers, refreshed at `2026-06-27T21:33:59Z`:

- `domain-chip-memory`: owner handoff patch `docs/r30/patches/r30-memory-authority-proof.patch` has SHA256 `58640eacefecf560df09e99a077cbbd767d37dadc37614da9d927445ec6dac83`; applying the tree-diff patch to owner branch base `3116ccaa3977` produces tree `ae30034f03ac`. `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts` passed and reported 5 normalized contracts, 4 official adapters, and 1 shadow adapter. This is review/apply material only, not registry or publication authority.
- `spark-intelligence-builder`: owner handoff patch `docs/r30/patches/r30-builder-trace-proof-stack.patch` has SHA256 `48ee6c2658d571026831c0efc311d8d58303694d732b49c4b18439c79130797d`; applying the tree-diff patch to owner branch base `c94eac853fed` produces tree `a9aedb619481`. `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py` passed, `208 passed, 26 subtests passed in 53.29s`. This is review/apply material only, not registry or publication authority.
- `spark-telegram-bot`: reliability, build, line-count, and profile-specific Level 5 env proof gates passed. Owner handoff patch `docs/r30/patches/r30-telegram-control-reliability-stack.patch` has SHA256 `5b3f824ae0ef13495a784572e118ae35ec4c5a8f4a11b73b1256515940da785f`; applying the tree-diff patch to public owner base `67ad9e6ed297` produces tree `0b4112a97ab8`, carrying local proof head `6f48013edb22` as review/apply material only, not registry or publication authority.
- `spark-voice-comms`: pytest passed.
- `spark-voice-comms`: owner handoff patch `docs/r30/patches/r30-voice-trace-governor.patch` applies to public base `c74490d68ece`, produces tree `e3e1f8814970`, and passes `132 passed`; this remains review/apply material only, not registry or publication authority.
- `spawner-ui`: owner handoff patch `docs/r30/patches/r30-spawner-runtime-artifact-tree.patch` has SHA256 `20ceb275a6f691d0c482f4947bf92dfc1890cf97cec0f992978a308c4b17c223`; applying the tree-diff patch to owner base `fdb8fded4744` produces tree `4e685e6206f7`. Focused access-lane and Codex sandbox tests passed with `22 passed`, and `npm run build` passed. This is review/apply material only, not registry or publication authority.
- `spark-cli`: the live local checkpoint is verified by `git rev-parse HEAD` and `verify --r30`; pre-refresh baseline `3bc788158c535b6a8eb0353e00797d11f39cd064` carries the R30 Access 5 anti-read-only gate, Telegram and Spawner owner patch artifacts, executable patch-apply proof, voice prepared-lane commit proof, live owner-ref audits, Telegram full-permission/audit handoff, natural confirmed Level 1/3/4 to Level 5 proof preservation, refreshed Spawner active Level 5 full-access lane proof, and hosted R29 baseline evidence. This checkpoint keeps registry and installer movement blocked until owner-source refs and installed metadata converge.

These are local proof passes, not owner-source convergence. Registry and
installer truth must not move until the corresponding owner-source refs exist
and installed metadata is updated through the normal path.

Executable owner-handoff patch apply verification at `2026-06-28T03:42:45Z`:

This proof is now part of `verify --r30`: the gate creates temporary Git
worktrees from the recorded owner bases, applies each patch, and requires
`git write-tree` to match the recorded target tree.

- `domain-chip-memory`: `r30-memory-authority-proof.patch` applies to
  `3116ccaa3977279581cb09d6e02353485de8a9b3` and produces tree
  `ae30034f03acbf57a2e7ac5c39103c9ac5ccf3a0`.
- `spark-intelligence-builder`: `r30-builder-trace-proof-stack.patch` applies
  to `c94eac853fed935ac09bed1c56912968f3365c14` and produces tree
  `a9aedb619481ffc9fa22d6289e82df47400948cf`.
- `spark-telegram-bot`: `r30-telegram-control-reliability-stack.patch`
  applies to `67ad9e6ed297baf6c9daa74b879fa45bc45bd579` and produces tree
  `0b4112a97ab8cd4ce6c593e11bd4eee2c3044d6b`. `git apply` still reports
  known blank-EOF whitespace warnings; the resulting tree matches.
- `spark-voice-comms`: `r30-voice-trace-governor.patch` applies with `git am`
  to `c74490d68ece65ffad21dc5b88f44602e1afa703` and produces tree
  `e3e1f881497011917fd9baa4f56db811ebccff7e`. The voice handoff manifest
  apply check now has to name `git write-tree`, that exact tree, and the voice
  pytest proof command.
- `spawner-ui`: `r30-spawner-runtime-artifact-tree.patch` applies to
  `fdb8fded47447417dbf146130bddd0967e1f6bc0` and produces tree
  `4e685e6206f788d28d40bc13a86b87285c1982da`.

## Owner-Lane Command Checklist

These commands are for the owner lane after authorization. They are written so
an owner can inspect and prepare a handoff without accidentally changing public
truth. Do not push from this debugging lane without explicit authorization.

### `spark-telegram-bot`

```bash
cd ~/.spark/modules/spark-telegram-bot/source
git fetch origin --tags
git status --short --branch
git log --oneline e5a1bd0409865ddb3024c15ed35ccd0038e31776..6f48013edb22fbf558735b59e11b95b3f0413584
npm test -- --run tests/accessLevel5Natural.test.ts tests/runnerPreflight.test.ts tests/accessActions.test.ts tests/buildE2E.test.ts
npm run build
npm run control:proof:reliability
npm run check:line-count
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/recursiveLevel5RuntimeEnv.test.ts tests/telegramCommandAuthority.test.ts
npm test -- --run tests/healthPolling.test.ts tests/profileEnv.test.ts tests/accessActions.test.ts
```

Owner action after review: push or port the
`e5a1bd040986..6f48013edb22` reliability ladder, access activation stack, health-token preservation fix, `Harden Telegram profile Level 5 env proof`, active-profile stale read-only env proof, startup profile-env refresh over stale read-only process env, and Level 5 full-permission audit doc into an owner release ref,
then update registry truth only after the proof commands pass on that owner ref.

### `spawner-ui`

```bash
cd ~/.spark/modules/spawner-ui/source
git fetch origin --tags
git status --short --branch
git log --oneline origin/release/stability-2026-06-02-spawner-authority..029c2086efcf48444865696333ccc6c756290d83
npm test -- --run src/lib/server/access-execution-lanes.test.ts src/routes/api/access/execution-lanes/access-execution-lanes.integration.test.ts src/lib/server/provider-clients/codex-cli-client.test.ts
npm test -- --run src/lib/server/prd-auto-dispatch.test.ts src/routes/api/prd-bridge/write/clarification-policy.test.ts src/lib/server/provider-clients/codex-cli-client.test.ts src/lib/services/spark-agent-bridge.test.ts src/lib/server/provider-clients/spark-harness-client.test.ts src/lib/server/high-agency-workers.test.ts
npm run build
npm run check
```

Owner action after review: push or port the Spawner PRD proof-continuity stack
and the direct-client, PRD-lane, persisted Level 5 Codex sandbox, shared effective-env worker access/path validation, Codex worker env propagation fixes, and active Level 5 full-access lane classification into the owner release lane, then update
registry truth only after `npm run check` passes on that owner ref.

### `spark-voice-comms`

```bash
cd ~/.spark/modules/spark-voice-comms/source
git fetch origin --tags
git status --short --branch
git log --oneline origin/codex/turnintent-voice-policy-20260531..7555a363d7638537b1a9ec1ee377e460d2343323
git switch -c release/r30-voice-trace-governor c74490d68ece65ffad21dc5b88f44602e1afa703
git cherry-pick 8a246af1eb0732aec432d88e4e4c2b6411023b7c
git cherry-pick 7555a363d7638537b1a9ec1ee377e460d2343323
PYTHONPATH=src python3 -m pytest -q
spark os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```

Owner action after review: create or select a stable owner release ref from the
current public owner base, then port or push
`8a246af1eb0732aec432d88e4e4c2b6411023b7c` and
`7555a363d7638537b1a9ec1ee377e460d2343323`, or equivalent source-owned
trace/governor commits, before any R30 voice registry claim. Do not pin R30
voice to `c74490d68ece` if R30 claims the current Spark OS voice proof.
If the cherry-pick route conflicts, keep the same proof boundary and record the
replacement source-owned commits before registry or installer truth moves.

Prepared local lane status:

- branch: `release/r30-voice-trace-governor`
- base: `c74490d68ece65ffad21dc5b88f44602e1afa703`
- port commit: `4eef348bae135ca3c0d85d4921bf3d4bc28f5e4f`
- port commit: `c502ec096cefb48839e3279d3392343231884415`
- proof: `PYTHONPATH=src python3 -m pytest -q` -> `132 passed`
- fresh proof: `2026-06-27T23:38:48Z`, `132 passed`

This closes the local preparation slice only. It does not authorize a push,
tag, registry pin update, installed metadata edit, installer movement, or
hosted publication.

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
git log --oneline origin/codex/turnintent-builder-boundary-20260531..ca21e183c6c04a658260b218e22fad7b67e02cc7
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

## Publishing-Machine Sequence

Use this only after explicit authorization to push/tag/publish. The debugging
lane must not perform these actions.

1. Land owner-source refs for the five direct R30 modules:
   `spark-voice-comms`, `spark-telegram-bot`, `spawner-ui`,
   `domain-chip-memory`, and `spark-intelligence-builder`.
2. On each owner ref, run the proof command listed above for that module.
3. Update installed runtime sources through the normal Spark install/update path,
   not by hand-editing installed metadata.
4. Update `registry.json` pins and provenance metadata only to owner-source refs
   that passed proof.
5. From `spark-cli`, run:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
PYTHONPATH=src python3 -m spark_cli.cli os compile --json
PYTHONPATH=src python3 -m spark_cli.cli live status --json
```

6. Only after source and registry truth are green, prepare the R30 installer pin
   batch in `scripts/installer-manifest.json`, `scripts/install.sh`, and
   `scripts/install.ps1`.
7. Run:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json
PYTHONPATH=src python3 -m pytest tests/test_cli.py -q
git diff --check
```

8. Publish hosted installer metadata only as the final authorized batch, then
   run hosted installer verification.

## Exact Commit Lists

### `spark-telegram-bot`

Range: `e5a1bd0409865ddb3024c15ed35ccd0038e31776..6f48013edb22fbf558735b59e11b95b3f0413584`

Top commits currently in the R30 handoff stack:

- `6f48013 Honor CLI Level 5 permission proof`
- `7cb3ce1 Preserve natural Level 5 confirmations`
- `ce4a234 Require Telegram Level 5 full permission proof`
- `Document Level 5 full permission audit`
- `d2f13ee Refresh Telegram Level 5 profile env`
- `dec4b01 Harden Telegram profile Level 5 env proof`
- `0cd7914 Preserve Telegram token during profile health checks`
- `8190500 Harden Recursive Level 5 runtime env`
- `97dd34d Require Level 5 proof for operator access status`
- `464cce4 Harden Telegram Level 5 runtime env`
- `d67d0a6 Compact Telegram imports after Level 5 env fix`
- `bb38eca Require effective Level 5 sandbox proof in Telegram`
- `a87f4eb Use proof oracle for Telegram Level 5`
- `fe39d37 Harden Telegram Level 5 proof gate`
- `4a630b3 Harden Telegram Level 5 sandbox status`
- `28aecd8 Require effective Level 5 sandbox before operator claims`
- `0279193 Block Level 5 full-access copy on read-only sandbox`
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
- `Harden Telegram Level 5 proof gate`
- `Use proof oracle for Telegram Level 5`
- `Require effective Level 5 sandbox proof in Telegram`
- `Require Level 5 proof for operator access status`

Minimum owner-lane proof after port:

```bash
npm test -- --run tests/accessLevel5Natural.test.ts tests/runnerPreflight.test.ts tests/accessActions.test.ts tests/buildE2E.test.ts
npm run build
npm run control:proof:reliability
npm run check:line-count
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts
```

### `spawner-ui`

Range: `origin/release/stability-2026-06-02-spawner-authority..029c2086efcf48444865696333ccc6c756290d83`

Commits:

- `029c2086 Prove Level 5 Codex launches ignore stale read-only env`
- `3042f8ac Carry Level 5 env into Codex workers`
- `7110dce4 Honor Level 5 sandbox in PRD Codex lanes`
- `97cb911b Honor persisted Level 5 sandbox in Spawner`
- `e0fbb5b6 Honor persisted Level 5 worker access`
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
npm run build
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
- Original local proof branch at `7555a363d763`: `PYTHONPATH=src python3 -m pytest -q` -> `80 passed`

Owner release base for R30 voice port:

- `refs/heads/main` / `spark-ship-2026-06-26` at `c74490d68ece65ffad21dc5b88f44602e1afa703`
- suggested local review branch: `release/r30-voice-trace-governor`

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

Range: `origin/codex/turnintent-builder-boundary-20260531..ca21e183c6c04a658260b218e22fad7b67e02cc7`

The range is large: 44 commits covering Builder trace/proof repairs, media transcription authority, memory route cadence, historical trace handoff docs, and the final memory authority reconciliation.

Representative terminal commits:

- `ca21e18 Restore Builder denial ledger proof`
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
- `d59f533 Require effective sandbox proof in R30 access gate`
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
those surfaces converge. Access 5 proof must include the hardening from
`Require effective sandbox proof in R30 access gate`, which rejects
configured-only Telegram Level 5 sandbox proof. It must also include
`missing_or_stale_services=[]`
for all startable or already-running Telegram profiles and
`effective_codex_sandbox=danger-full-access` for the service lane. The final
live access payload must also report `effective_access_level=5` and
`service_can_operate_whole_computer=true`; do not accept a module-level Telegram
restart, green env files alone, or a stale current-process sandbox as proof that
SparkRecursive/SparkQA-style bot profiles are writable. Stale no-token profile
files must remain visible as `skipped_unstartable_telegram_profiles` instead of
silently downgrading the whole install to workspace mode. `spark live status`
must use the same startable-profile rule: a no-token named profile can be shown
as stopped/unstartable, but it must not make the primary Telegram bot, Spawner,
or Level 5 proof look read-only or failed.

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
