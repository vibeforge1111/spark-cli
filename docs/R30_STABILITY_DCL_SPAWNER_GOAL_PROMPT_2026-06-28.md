# R30 Stability, Domain Chip Labs, And Spawner Goal Prompt

Date: 2026-06-28
Status: goal prompt and task contract; not a publication record

## Why This Exists

R30 should not be called ready merely because installer manifests line up. It
also needs the core user path to feel dependable:

- a user can create a Spark Domain Chip Labs artifact from a natural Telegram
  conversation
- Spawner can start or explain mission work without silent failures
- Access Level 5 and writable-runner truth are reflected honestly
- proof systems stay fresh enough that release claims are not vibes
- proof stays quiet unless it changes the decision or gives the user a receipt

This goal sits on top of the existing R30 source-owner, registry, and installer
gates. It does not authorize push, deploy, tag, publish, registry movement, or
installer pin changes.

Before broad implementation, use
[R30_DCL_SPAWNER_READINESS_SPEC_2026-06-28.md](./R30_DCL_SPAWNER_READINESS_SPEC_2026-06-28.md)
as the planner-first contract: define the user-visible working state, exact QA
matrix, proof owner, remaining blocker, and stop-ship condition for each slice.
Use
[R30_DCL_SPAWNER_RELIABILITY_WORKFLOWS_2026-06-28.md](./R30_DCL_SPAWNER_RELIABILITY_WORKFLOWS_2026-06-28.md)
for the quiet-proof rulesets, live Telegram Desktop/CUA workflow, and
benchmark/eval plan.
Use
[R30_DCL_SPAWNER_QA_PLAN_2026-06-28.md](./R30_DCL_SPAWNER_QA_PLAN_2026-06-28.md)
as the release-gate ladder for local tests, live Telegram proof, evidence
packets, stop conditions, and commit discipline.

## Task List

1. Audit the current Telegram -> Domain Chip Labs -> Spawner path end to end:
   natural intent, pending state, `/run`, Spawner bridge, mission id/reply,
   artifact path, failure replies, and proof joins.
2. Confirm whether Domain Chip Labs creation works for more than one domain,
   not only Higgsfield/Seedance examples.
3. Define the minimal DCL artifact contract and make Telegram ask no more than
   one useful scope question when the user intent is already clear.
4. Require capability truth in every creation or Spawner reply: allowed,
   writable, staged, created, blocked-here, or failed-with-reason.
5. Make `/run` and Spawner mission creation close the loop with either a mission
   id/artifact proof or one exact failure reason.
6. Add regression tests for DCL intent lock, pending-state continuity, stale
   memory/caution hijack, read-only runner, Level 5 writable runner, failed
   Spawner bridge, missing `/run` reply, and conversational surface quality.
7. Run Telegram build, line-count, focused route tests, Spawner focused tests,
   and R30 verifier after each proven slice.
8. Keep R30 blocked until source-owner refs, registry pins, installed runtime
   metadata, installer pins, hosted metadata, and docs agree.

## Goal Prompt

Use this in a writable Codex lane:

```text
Goal: Make Spark R30 genuinely stable for Domain Chip Labs creation, Spawner execution, and Telegram usability before any R30-ready claim.

Do not push, deploy, tag, publish, move registry pins, or change installer pins. Preserve the existing R30 source-owner, registry, installer, and live trace gates. First reduce measured proof gaps, trace-join gaps, Spawner closure gaps, DCL creator gaps, and confusing capability-truth replies.

Mandate: make Spark act on fresh intent cleanly, then prove it quietly. Proof capsules, traces, route decisions, memory frames, and access internals stay underneath unless the user asks for raw detail. Natural action replies should give one receipt: created, blocked, skipped, or needs confirmation.

Start with the R30 DCL/Spawner readiness spec. For each slice, document the failure being closed, great working state, source owner, exact QA, affected gate, remaining blocker, and stop-ship condition before broad code changes.

Audit the real Telegram -> Domain Chip Labs -> Spawner path end to end: natural “build/create a domain chip” intent, pending state, scope follow-ups, /run, Spawner bridge, mission id/reply, artifact path, failure replies, Access Level 5 truth, writable-runner proof, and route/action/reply proof joins. Use the Higgsfield/Seedance conversation as one failure specimen, but prove the creator lane works for multiple domains.

Implement durable behavior, not one-off copy fixes. Domain chip creation must lock intent, avoid stale memory/caution hijacks, ask at most one useful scope question, keep “go/doesn’t matter/repeated goal” attached to the same pending chip, and return either chip/mission/artifact proof or one exact blocked-here reason. Generated DCL artifacts must include purpose, triggers, non-triggers, playbook, examples, manifest/hook contract, evals, benchmark pack, score dimensions, allowed mutations, evidence ladder, privacy boundary, watchtower, rollback, review packet, and activation notes.

Spawner must be boringly reliable: every /run or mission handoff returns a mission id, artifact/review path, queued/running/completed state, or a precise failure class. No silent no-reply states. No “access is Level 5” claim unless effective Codex sandbox and writable runner proof agree.

Add regression tests for DCL intent lock, non-video domain creation, pending-state continuity, stale-memory conflict, read-only runner, Level 5 writable runner, failed Spawner bridge, missing /run reply, router fallthrough, loop benchmark proof, watchtower regression, and warm Telegram surface quality. Run the R30 DCL Spawner QA plan gate ladder: focused regression, top-level Telegram route, cross-route drift, build and line-count, runtime smoke, Telegram Desktop/CUA proof, live trace proof, and R30 verifier checks. Commit only after the relevant gates pass and update R30 docs with green proof, blocked proof, and remaining source-owner handoffs.
```

## Autonomous /goal Prompt

Use this when starting a long autonomous Codex goal:

```text
Goal: Continue R30 Domain Chip Labs and Spawner reliability until the current local slice is either proven, committed locally, and handed off with exact remaining blockers, or blocked by live Telegram/user confirmation.

Read first:
- ~/.spark/tools/spark-cli/docs/R30_DCL_SPAWNER_READINESS_SPEC_2026-06-28.md
- ~/.spark/tools/spark-cli/docs/R30_DCL_SPAWNER_RELIABILITY_WORKFLOWS_2026-06-28.md
- ~/.spark/tools/spark-cli/docs/R30_DCL_SYSTEM_SOURCE_MAP_2026-06-28.md
- ~/.spark/tools/spark-cli/docs/R30_DCL_SPAWNER_QA_PLAN_2026-06-28.md
- ~/.spark/tools/spark-cli/docs/R30_DCL_SPAWNER_TELEGRAM_CONTINUATION_HANDOFF_2026-06-28.md

Boundary:
Do not push, publish, deploy, tag, merge, move registry pins, update installer pins, change hosted metadata, expose secrets, or claim R30 readiness. Preserve all user/unrelated worktree changes. R30 remains red until source-owner truth, installed runtime metadata, registry pins, installer pins, hosted metadata, live Telegram proof, and docs agree.

Mandate:
Make Spark act on fresh intent cleanly, then prove it quietly. Deterministic proof lives underneath. Natural Telegram replies should give one receipt: created, blocked, skipped, or needs confirmation. Raw traces, memory frames, route internals, local paths, ids, and access chatter stay hidden unless explicitly requested.

First slice:
Finish the creator-mission closure refinement already in the Telegram worktree. Prove missing mission/review proof fails closed, user-visible staged artifact proof is review-only without mission id, local filesystem paths are rejected as proof, and pending creator mission state is only remembered for proven mission ids.

QA order:
Follow the R30 DCL Spawner QA Plan gate ladder. Run focused regressions first, then top-level Telegram route tests, cross-route drift tests, build and line-count, runtime smoke, Telegram Desktop/CUA live proof when safe, live trace proof, and R30 verifier checks. Stop if Telegram Desktop has a user draft, the visible chat is wrong, a no-action prompt starts work, live behavior disagrees with local tests, or source/registry/installer movement would be required.

After the first slice:
Refresh Spark CLI docs, patch metadata, handoff manifests, and evidence packets only after local and live proof agree. Keep remaining blockers explicit. Then continue in order: pending continuity, multi-domain DCL coverage, /run closure taxonomy, Level 5 writable truth, artifact-loop promotion proof, QA Evidence Lane DCL scenarios, and only then Spark CLI DCL readiness reporting.

Completion standard:
End with an evidence packet: failure reproduced, primary failure class, patch scope, local tests, smoke tests, live Telegram/CUA result, docs/manifests touched, remaining blockers, commit status, and PR/push status. Do not mark complete merely because tests are partially green.
```
