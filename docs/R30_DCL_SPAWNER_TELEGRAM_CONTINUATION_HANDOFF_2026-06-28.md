# R30 DCL Spawner Telegram Continuation Handoff

Date: 2026-06-28
Status: continuation handoff with locally proven closure-proof update and live
Telegram no-action proof; not a publication record

## Boundary

This document is for the next writable lane that continues R30 Domain Chip Labs
and Spawner reliability work from Telegram.

Do not push, deploy, tag, publish, move registry pins, update installer pins, or
claim R30 readiness from this handoff. R30 remains blocked until source-owner
truth, registry pins, installed runtime metadata, installer pins, hosted
metadata, and docs agree.

## Current Continuation Update

The original missing-proof red slice is now locally closed in the Telegram repo
at commit `3259a9f` (`Harden creator mission closure proof`). It builds on
`eece10d` (`Fail closed on creator mission proof gaps`) and:

- only accepts user-visible Spawner URLs/paths as staged artifact proof
- treats staged artifact proof without mission id as review-only
- rejects local filesystem paths as closure proof
- wires `tests/creatorMissionClosure.test.ts` into the default test runner
- adds top-level Telegram regressions proving `trace.mission_id` is remembered
  as pending mission state and staged review/artifact proof without mission id
  stays review-only

Fresh local QA passed on 2026-06-28 after the refinement:

```bash
npm test -- --run tests/spawner.test.ts tests/creatorMissionClosure.test.ts
npm test -- --run tests/domainChipLabsCreator.test.ts
npm test -- --run tests/conversationIntent.test.ts tests/naturalRouteDecision.test.ts
npm test -- --run tests/buildE2E.test.ts
npm run build
npm run check:line-count
```

Runtime smoke passed after the local build:

```bash
PYTHONPATH=src python3 -m spark_cli.cli live status --json
PYTHONPATH=src python3 -m spark_cli.cli providers status --json
PYTHONPATH=src python3 -m spark_cli.cli providers test --role chat --json
npm run health:runtime -- --json
PYTHONPATH=src python3 -m spark_cli.cli access status --json
```

Observed smoke state:

- Spark Live was green.
- Telegram primary was polling on relay port `8789`.
- Spawner live health returned HTTP 200.
- Provider roles were ready and chat provider returned `PING_OK`.
- Current process effective access stayed Level 4/workspace-write; service
  Level 5 guardrails were active for Spawner and Telegram, so do not claim this
  Codex process itself has whole-computer access.

Telegram Desktop/CUA proof was recaptured with Peekaboo after a targeted local
restart:

```bash
PYTHONPATH=src python3 -m spark_cli.cli restart spark-telegram-bot --profile primary --allow-dirty-runtime --json
npx -y @steipete/peekaboo see --app Telegram --json --path /tmp/r30-dcl-telegram-preflight-after-restart.png
```

The visible chat was `Spark Recursive`, the composer was empty, and the primary
bot restarted cleanly on pid `71227`.

Live no-action prompt:

```text
Quick QA no-action check: I'm not asking you to create, run, repair, or publish anything. In one or two sentences, what proof would you require before a Domain Chip Labs creator mission can be considered safe to run?
```

Observed live reply was conversational and did not start work:

```text
Fresh proof required: locked user intent, confirmed access/runner capability, DCL scaffold contract present, and a proof capsule showing the mission stays private with no API calls, publishing, secrets, or network claims.

If any of that is stale or missing, Spark can keep shaping in chat but should not run or claim the creator mission is safe.
```

Explicit `/proof` for the turn showed `Intent: conversation_ideation`,
`Authority: allowed by spark.turn_intent.v1`, `Governor: read_only, verified`,
`Execution: completed`, `Gaps: none`, `Audit blocking: clean`, and no blocking
gap planes. Bot logs also show Spawner and creator mission routes blocked for
that no-action prompt before the conversational route completed.

The Spark CLI R30 verifier now sees the R30 docs packet as present, including
the reliability workflow and QA plan documents, but remains red. Current red
reasons are expected and must not be hidden:

- `r30_docs`, `os_compile`, and `r30_live_status` are green after the local
  Telegram commit
- `publish_handoffs`
- `owner_handoff_manifest`
- `r30_local_runtime_artifacts_handoff`
- `r30_owner_handoff_patch_apply`
- `release_lane`
- `r30_voice_registry_decision`
- `registry_pins`
- installer pins still at R29

Default specialization-loop proof is also red because `spark-domain-chip-labs`,
`spark-swarm`, and `specialization-path-*` roots are not installed or
discoverable in the active Spark registry. Temporary env-var discovery of the
older local repos under
`/Users/alchemistab/Documents/Codex/2026-05-09/does-this-spark-update-look-good/pr-work`
finds the roots, but the proof gate still fails because `spark-qa-operator`
claims improvement without trap proof while the other discovered paths are
held-steady, unproven, or missing registry definition. Treat this as the next
loop-engineering reliability gap, not as R30-ready evidence.

## Clean Baseline

Spark CLI docs/verifier repo:

- repo: `/Users/alchemistab/.spark/tools/spark-cli`
- branch: `harness-discipline-ruleset`
- clean checkpoint: `ca5c45e` (`Document R30 DCL Spawner readiness`)
- post-commit R30 verifier summary:
  - R30 docs green, 18 required docs, no missing docs
  - owner handoff manifest green
  - local runtime artifacts handoff green
  - local runtime handoff docs green
  - owner patch apply green
  - 0 dirty release repos
  - 5 direct R30 blockers remain: `domain-chip-memory`,
    `spark-intelligence-builder`, `spark-telegram-bot`,
    `spark-voice-comms`, `spawner-ui`
  - installer pins remain R29

Telegram bot repo:

- repo: `/Users/alchemistab/.spark/modules/spark-telegram-bot/source`
- branch: `harness-discipline-line-count-gate`
- clean committed checkpoint before current WIP: `0cf6e5c`
  (`Harden DCL creator mission routing`)
- current closure-proof commit touched:
  - `scripts/run-tests.cjs`
  - `src/creatorMissionClosureProof.ts`
  - `src/spawner.ts`
  - `tests/creatorMissionClosure.test.ts`
  - `tests/domainChipLabsCreator.test.ts`

Do not refresh patch metadata, handoff manifests, registry pins, or installer
truth until the local commit and source-owner handoff are intentionally updated.

## What Is Already Green

The first DCL creator slice is committed at Telegram `0cf6e5c`:

- rich “Spark Domain Chip Labs framework” prompts route to `creator.mission`
- full creator-system DCL prompts use the Spawner creator mission lane instead
  of shallow chip preview or generic PRD bridge
- DCL contract text includes manifest/hook, triggers/non-triggers, evals,
  benchmark, score dimensions, allowed mutations, watchtower, rollback, review
  packet, and activation notes
- simple domain-chip preview remains preview-first

Proof that passed before this handoff:

```bash
npm test -- --run tests/domainChipLabsCreator.test.ts
npm test -- --run tests/conversationIntent.test.ts tests/naturalRouteDecision.test.ts tests/spawner.test.ts
npm test -- --run tests/buildE2E.test.ts
npm run build
npm run check:line-count
```

## Original Red WIP, Now Closed Locally

This was the red gap this continuation closed locally. It is retained here as
the failure spec for review and future source-owner handoff.

Observed bug:

- `spawner.creatorMission()` treats `ok: true` as success even when Spawner
  returns no `missionId`, no `trace.mission_id`, and no staged artifact or
  review path.
- `formatCreatorMissionSummary()` then renders a staged-looking creator plan
  with `missionId = unknown` and a generic board link.
- Top-level Telegram DCL flow can therefore tell the user a private path was
  staged even though no mission id or traceable staged artifact was proven.

This violates the R30 readiness spec:

- Spawner cannot accept work without mission id or traceable staged artifact.
- A missing mission id must become one exact blocked-here reason.
- No pending creator mission should be remembered without mission proof.

The regressions now pass locally in the Telegram worktree.

Focused unit regression:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/spawner.test.ts
```

Regression:

- `creatorMission fails closed when Spawner omits mission and staged artifact proof`

Meaning: `spawner.creatorMission()` must report `success=false` for an `ok:
true` response with no mission proof.

Focused top-level Telegram regression:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/domainChipLabsCreator.test.ts
```

Regression:

- `DCL framework Telegram turn fails closed when Spawner omits mission proof`

Meaning: the real `handleTextMessage()` path must render one failure reason
instead of a staged DCL creator plan when the Spawner bridge response lacks
closure proof.

## Intended Durable Fix

Patch the Spawner bridge boundary, not only the Telegram copy.

Recommended implementation shape:

1. Add a small helper in `src/spawner.ts` that detects creator mission closure
   proof from the Spawner response.
2. Treat a creator mission response as accepted only if it has one of:
   - `missionId`
   - `trace.mission_id`
   - a traceable staged artifact/review path that can be shown to the user
3. If `ok: true` but closure proof is missing, return:

```ts
{
  success: false,
  error: 'Creator mission bridge returned ok but missing mission id or staged artifact proof.'
}
```

4. Keep `formatCreatorMissionSummary()` as the final user-facing guard:
   - failed result -> short failure reply
   - no staged-looking copy
   - no generic `/kanban` link pretending a mission exists
5. Keep `handleCreatorMissionPlan()` from remembering pending creator mission
   state unless `result.success && result.missionId && !read_only`.

If a valid staged artifact path exists without a mission id, the reply must
still make the state explicit as staged/review-only and must include the
artifact/review path. Do not silently convert it to a runnable mission.

## QA Ladder For Next Lane

Run in Telegram repo after the patch:

```bash
npm test -- --run tests/spawner.test.ts
npm test -- --run tests/domainChipLabsCreator.test.ts
npm test -- --run tests/conversationIntent.test.ts tests/naturalRouteDecision.test.ts
npm test -- --run tests/buildE2E.test.ts
npm run build
npm run check:line-count
```

Then update docs/handoff truth in Spark CLI:

- bump Telegram local proof head from `0cf6e5c` to the new commit
- regenerate `docs/r30/patches/r30-telegram-control-reliability-stack.patch`
- update patch SHA256, line count, expected tree, proof commands, and evidence
  packet
- run focused CLI R30 docs/handoff tests
- run `spark_cli.cli verify --r30 --json` and confirm docs/handoff/patch gates
  stay green while source/registry blockers remain explicit

Commit order:

1. Commit the Telegram implementation slice only after its tests/build/line-count
   pass.
2. Commit the Spark CLI docs/handoff refresh after verifier checks pass.

## Next Larger Work After Closure Proof

After the missing-proof closure gap is fixed, continue the R30 DCL/Spawner lane:

- pending continuity for “go,” “doesn’t matter,” “use defaults,” repeated goal,
  cancel, and expired pending draft
- multi-domain DCL coverage beyond Higgsfield/Seedance:
  creative/media, operations, research, coding/tooling, coaching/advisory
- `/run` closure proof for missing reply, failed bridge, timeout, rejected
  bridge, provider missing, and mission id missing
- Access Level 5 writable-runner truth in DCL and `/run` replies
- loop proof in generated artifacts: baseline, candidate, score,
  held-out/trap checks, promotion block, watchtower regression
- Telegram surface quality: warm concise replies, one next action, no raw ids
  unless needed, no report-card headings for natural follow-ups

## Stop-Ship Reminder

Do not call R30 ready if any are true:

- DCL creation can silently fall back to generic chat or generic PRD bridge
- Spawner can accept work without a mission id or traceable staged artifact
- `/run` can fail without a reply
- Level 5 copy can claim full access without effective sandbox and writable
  proof
- generated DCL artifacts miss evals, benchmark, watchtower, rollback, or
  activation notes
- local proof exists only in runtime commits that are not represented in
  source-owner handoff docs
- R30 verifier shows new undocumented blockers
