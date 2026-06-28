# R30 Domain Chip Labs Telegram Creator Plan

Generated: 2026-06-28

## Current R30 Handoff Truth

R30 is not an installer-publish lane yet. It is still a source-owner convergence lane.

- Telegram proof head: `0cf6e5c1624bfbe2e7c17163e2edce8c48d91032`
- Telegram owner base: `67ad9e6ed297baf6c9daa74b879fa45bc45bd579`
- Telegram handoff patch: `docs/r30/patches/r30-telegram-control-reliability-stack.patch`
- Patch SHA256: `c5f0e9a60fdbf623c22a932cbf2f4adb9e258f5ff9dfee4ce46f9a40930914f6`
- Patch apply tree after `git add -A`: `1b676a0f948215599e41cf8f7a8ca7af5903af9e`
- Local Telegram proof is review/apply material only. It is not registry, installer, or hosted publication authority.

The latest Telegram slice hardens rich Domain Chip Labs creator mission routing
and adds top-level Telegram regression coverage for full creator-system prompts.
It does not complete the full Domain Chip Labs creator lane.

## Problem To Solve

The R30 installer should not only prove tracing and permissions. It should let a normal Telegram conversation create a real Spark Domain Chip Labs artifact without route hijacks, stale caution, missing replies, or read-only confusion.

The failed conversation showed these gaps:

- explicit domain-chip creation was previewed through a generic name-generation prompt
- stale philosophy/caution replies overrode the user's fresh build intent
- Access Level 5, runner writability, and mission creation proof were mixed together
- `/run` did not close the loop with a mission id or exact failure
- the user had to understand Spark internals to know what happened

This is not a Higgsfield/Seedance-only problem. That conversation is the
example that exposed the broader product gap: Telegram does not yet provide a
reliable, warm, low-friction creator lane for any user who wants to turn a
domain need into a private Spark Domain Chip Labs artifact.

## Conversation Failure Audit

The conversation should have produced one of two outcomes:

- a private `domain-chip-video-skit-crafter` mission with a mission id and
  reviewable artifact contract
- one exact blocked-here reply with a writable-lane prompt

Instead, Spark drifted through generic naming prompts, stale caution, read-only
confusion, Telegram poller error text, Access Level 5 uncertainty, and finally a
missing `/run` reply. The relevant failures are:

- intent lock failed: explicit "build/create a domain chip" did not persist as
  `domain_chip.create`
- scope memory failed: "go", "doesn't matter", and the repeated mission prompt
  did not continue the same pending chip
- capability truth failed: allowed access, writable runner, current process
  sandbox, service sandbox, and mission proof were blurred together
- action closure failed: `/run` returned no mission id, no staged artifact, and
  no exact failure
- surface quality failed: the user had to debug Spark instead of shaping the
  chip

R30 should treat those as measured release-readiness gaps, not copy polish.

## Telegram UX Standard

A great Telegram domain-chip creation flow should feel like this:

1. User says a natural request: “build a domain chip for X.”
2. Spark locks intent as `domain_chip.create`, not generic chat, creator philosophy, or stale memory.
3. Spark asks at most one relevant scope question, unless the request is already specific.
4. Spark states the execution truth plainly: writable and starting, or allowed but blocked here, or needs confirmation.
5. Spark stages or creates the chip and returns proof: chip key, mission id/path, first files or review packet, and next action.
6. If blocked, Spark gives one exact writable-lane prompt and does not pretend work happened.
7. Follow-ups like “go”, “full workflow”, “ideation only”, or “use defaults” continue the same pending chip, not a new generic mission.

Default preview copy should be DCL-shaped:

- ideation only
- shot/prompt packets
- full campaign/workflow
- private DCL scaffold
- evals, watchtower, evidence ladder
- no external API calls, posting, secrets, or network publication unless explicitly approved

## Universal Creator Onboarding

The lane should ask itself the same product questions before it asks the user
anything:

- Can the user's first message already define a useful v1 chip?
- Is this a new chip, a refinement to an existing chip, or a benchmark loop for
  a chip already in use?
- What is the smallest private artifact that would improve the user's next
  workflow?
- Which capability is actually available right now: chat-only shaping, staged
  artifact, writable mission, or live activation?
- What proof will let the user trust that something happened?
- What should the chip never do, even if the domain gets tempting?

Telegram should usually ask at most one question:

- scope: ideation, packets, full workflow, evaluator, or watchtower
- audience/domain: who or what the chip is optimizing for
- boundary: private review only, local files, or activation-ready scaffold

If a user says "doesn't matter", "go", or repeats the goal, Spark should choose
the safest useful default and proceed instead of reopening the whole decision.

## Domain Chip Labs Artifact Contract

Every created chip should have:

- purpose and user outcome
- triggers and non-triggers
- playbook and examples
- manifest and hook contract
- eval cases and benchmark pack
- score dimensions and target metric
- allowed mutations and forbidden mutations
- evidence ladder
- privacy boundary
- watchtower signals
- rollback path
- review packet
- activation notes

The chip should not be called “live” until router invocation, fallthrough, and artifact evidence pass.

Different domains may need different modules, but the contract should stay
stable. Examples:

- creative chip: trend signals, prompt packets, taste rubric, safety boundary
- research chip: source policy, freshness checks, claim ledger, uncertainty
  handling
- operations chip: triggers, runbook, escalation rules, rollback, audit packet
- coding chip: repository triggers, test matrix, patch rules, review rubric
- coaching chip: tone boundary, progression loop, reflection criteria, privacy
  guard

## Loop Engineering Contract

Self-improving loops must be verifiable, bounded, and reviewable.

- Baseline: capture current output quality before mutation.
- Candidate: generate one controlled improvement.
- Score: use explicit metrics, not vibes.
- Compare: show before/after and held-out cases.
- Promote: only when the candidate wins without stealing unrelated routes.
- Watchtower: detect regressions, stale context, unsafe scope creep, and activation hijacks.
- Ledger: keep proof capsules for intent, route, artifact writes, evals, and promotion.

For user-facing Telegram, Spark should summarize the loop in human terms and keep raw ledgers behind inspect/status surfaces.

The self-improvement loop must never be a vague "make it better" promise. It
needs a baseline artifact, candidate change, scoring rubric, held-out examples,
promotion rule, rollback path, and a plain-language review summary the user can
understand in Telegram.

## Implementation Task List

1. Preserve R30 handoff truth: keep installer pins, registry pins, hosted
   metadata, tags, deploys, and source-owner claims blocked until the existing
   R30 gates are green.
2. Inventory current DCL creation routes, pending state, Spawner creator
   mission bridge, chip scaffolding, recursive loop sync, Domain Chip Labs
   standards, and artifact expectations.
3. Define a shared `domainChipCreatorLane` contract for parse -> preview ->
   confirm -> stage/create -> prove -> follow-up.
4. Add intent lock and pending-state continuity for explicit creation,
   repeated goal text, "go", "doesn't matter", and scope follow-ups.
5. Replace generic domain-chip preview/fallback copy with DCL-specific UX across
   Telegram natural chat, pending confirmations, `/run`, and creator-mission
   paths.
6. Add capability-truth replies for DCL creation: chat-only, allowed, writable,
   staged, created, blocked-here, missing-proof, or failed-with-reason.
7. Add a DCL review packet schema and ensure generated PRDs require the full
   artifact and loop-engineering contract.
8. Add proof capsules that join user intent -> route -> action/no-action ->
   artifact/eval/reply.
9. Add tests for explicit DCL creation, generic-domain examples, scope
   follow-ups, stale-memory conflict, read-only runner, Level 5 writable runner,
   failed Spawner bridge, missing `/run` reply, router fallthrough, benchmark
   loop proof, watchtower regression, and conversational surface quality.
10. Update R30 docs and release gates so DCL Telegram creator quality is a
    measured installer-readiness criterion, not polish.
11. Commit after each proven slice and keep historical debt visible.

## Handoff Shape

This lane should hand off in three layers:

- product handoff: Telegram UX standard, onboarding questions, artifact
  contract, loop-engineering contract, and conversation failure audit
- engineering handoff: route contract, pending-state contract, capability-truth
  states, Spawner bridge behavior, proof capsules, and tests
- release handoff: source-owner refs, local runtime artifact status, registry
  pins, installer pins, hosted metadata, and exact remaining blockers

The handoff should make it easy for the next lane to continue without
rediscovering why R30 is still blocked.

## Goal Prompt

Use this in a writable Codex lane:

```text
Goal: Make Spark R30’s Telegram Domain Chip Labs creator lane genuinely usable and evidence-backed.

Start from current R30 handoff truth. Do not publish, push, tag, deploy, move registry pins, or claim installer readiness. First reduce measured proof, trace-join, handoff, and DCL creator UX gaps. Do not expand UI, media support, or new features unless they directly close a measured control-proof or DCL creator-readiness gap.

Audit Telegram, Spawner creator missions, Domain Chip Labs standards, chip manifests/hooks, recursive/self-improving loops, pending-state UX, Access Level 5 capability truth, and R30 release docs. Use the Higgsfield/Seedance conversation as evidence of a general DCL creator-lane failure, not as the only target. Preserve the current reliability ladder and source-owner gates.

Implement a durable DCL Telegram creator lane: natural “build/create a domain chip” intent must lock to domain_chip.create, ask at most one relevant scope question, keep stale memory/caution from hijacking current intent, preserve pending chip state across “go”, “doesn’t matter”, and repeated goals, stage/create only when authorized and writable, and always return either chip/mission proof or one exact failure. Default scope should support ideation only, prompt/shot packets, full workflow, evaluator, or watchtower. Generated artifacts must include purpose, triggers, non-triggers, playbook, examples, manifest/hook contract, evals, benchmark pack, score dimensions, allowed mutations, evidence ladder, privacy boundary, watchtower, rollback, review packet, and activation notes.

Add verifiable loop engineering: baseline, candidate, score, compare, promote only on proof, held-out checks, watchtower signals, and proof capsules joining user intent -> route -> action/no-action -> artifact/eval/reply. Telegram surface should be warm and concise; raw ledgers stay behind inspect/status.

Add regression tests for explicit DCL creation, non-video domain examples, scope follow-ups, stale-memory conflict, read-only runner, Level 5 writable runner, failed Spawner bridge, missing /run reply, router fallthrough, benchmark loop proof, watchtower regression, and conversational surface quality. Run focused tests, build, line-count, and R30 verifier. Commit after each proven slice. Update R30 docs with what is green, what remains blocked, and why.
```
