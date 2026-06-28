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

This goal sits on top of the existing R30 source-owner, registry, and installer
gates. It does not authorize push, deploy, tag, publish, registry movement, or
installer pin changes.

Before broad implementation, use
[R30_DCL_SPAWNER_READINESS_SPEC_2026-06-28.md](./R30_DCL_SPAWNER_READINESS_SPEC_2026-06-28.md)
as the planner-first contract: define the user-visible working state, exact QA
matrix, proof owner, remaining blocker, and stop-ship condition for each slice.

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

Start with the R30 DCL/Spawner readiness spec. For each slice, document the failure being closed, great working state, source owner, exact QA, affected gate, remaining blocker, and stop-ship condition before broad code changes.

Audit the real Telegram -> Domain Chip Labs -> Spawner path end to end: natural “build/create a domain chip” intent, pending state, scope follow-ups, /run, Spawner bridge, mission id/reply, artifact path, failure replies, Access Level 5 truth, writable-runner proof, and route/action/reply proof joins. Use the Higgsfield/Seedance conversation as one failure specimen, but prove the creator lane works for multiple domains.

Implement durable behavior, not one-off copy fixes. Domain chip creation must lock intent, avoid stale memory/caution hijacks, ask at most one useful scope question, keep “go/doesn’t matter/repeated goal” attached to the same pending chip, and return either chip/mission/artifact proof or one exact blocked-here reason. Generated DCL artifacts must include purpose, triggers, non-triggers, playbook, examples, manifest/hook contract, evals, benchmark pack, score dimensions, allowed mutations, evidence ladder, privacy boundary, watchtower, rollback, review packet, and activation notes.

Spawner must be boringly reliable: every /run or mission handoff returns a mission id, artifact/review path, queued/running/completed state, or a precise failure class. No silent no-reply states. No “access is Level 5” claim unless effective Codex sandbox and writable runner proof agree.

Add regression tests for DCL intent lock, non-video domain creation, pending-state continuity, stale-memory conflict, read-only runner, Level 5 writable runner, failed Spawner bridge, missing /run reply, router fallthrough, loop benchmark proof, watchtower regression, and warm Telegram surface quality. Run focused tests, Telegram build, line-count, Spawner focused tests, and R30 verifier. Commit after each proven slice and update R30 docs with green proof, blocked proof, and remaining source-owner handoffs.
```
