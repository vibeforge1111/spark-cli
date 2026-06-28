# R30 DCL Spawner Telegram Continuation Handoff

Date: 2026-06-28
Status: continuation handoff; not a publication record

## Boundary

This document is for the next writable lane that continues R30 Domain Chip Labs
and Spawner reliability work from Telegram.

Do not push, deploy, tag, publish, move registry pins, update installer pins, or
claim R30 readiness from this handoff. R30 remains blocked until source-owner
truth, registry pins, installed runtime metadata, installer pins, hosted
metadata, and docs agree.

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
- current WIP has uncommitted failing regression tests in:
  - `tests/spawner.test.ts`
  - `tests/domainChipLabsCreator.test.ts`

Do not commit the Telegram WIP until the implementation patch makes the focused
tests, build, and line-count pass.

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

## Current Red WIP

The next gap is Spawner closure proof for creator missions.

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

Current failing regressions are already written but not committed.

Focused unit failure:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/spawner.test.ts
```

Expected failing test:

- `creatorMission fails closed when Spawner omits mission and staged artifact proof`

Current failure:

```text
AssertionError: true !== false
```

Meaning: current `spawner.creatorMission()` still reports `success=true` for an
`ok: true` response with no mission proof.

Focused top-level Telegram failure:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/domainChipLabsCreator.test.ts
```

Expected failing test:

- `DCL framework Telegram turn fails closed when Spawner omits mission proof`

Current failure:

```text
Expected /Creator mission failed/i, but the reply contained:
Private path staged. Nothing is running yet.
```

Meaning: the real `handleTextMessage()` path still renders a staged DCL creator
plan when the Spawner bridge response lacks closure proof.

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
