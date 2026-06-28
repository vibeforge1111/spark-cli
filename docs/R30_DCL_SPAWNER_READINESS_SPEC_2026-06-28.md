# R30 Domain Chip Labs And Spawner Readiness Spec

Date: 2026-06-28
Status: planning and QA contract; not a publication record

## Purpose

R30 should not be called stable until the Telegram Domain Chip Labs and Spawner
path works as a product experience, not just as a set of passing helper tests.
This spec defines the working state we want, the task list, the QA list, and the
evidence packet required before any R30-ready claim.

No push, deploy, tag, registry movement, installer pin movement, or hosted
publication is authorized by this document.

## Great Working State

A user can say, in natural Telegram language, “build/create a domain chip for
X,” and Spark reliably does one of three things:

- locks the turn as DCL creation and asks one useful scope question
- stages or creates a private creator mission and returns mission/artifact proof
- gives one exact blocked-here reason with the next writable action

The user should not need to understand Builder, Spawner, registry pins, route
confidence, local runtime artifacts, or Access Level internals to know what
happened.

The happy path must return:

- chip/domain name or mission title
- mission id when Spawner accepts work
- artifact or review path when available
- queued/running/completed/staged state
- proof boundary: what is proven, what is not proven yet
- one clear next action

The blocked path must return:

- one failure class
- whether the issue is access, writable runner, Spawner bridge, provider,
  route authority, artifact validation, or release truth
- one next action, not a stack of guesses
- no claim that Level 5 is effective unless writable runner proof and effective
  Codex sandbox agree

## DCL Artifact Contract

Every generated Domain Chip Labs artifact needs:

- purpose and user outcome
- triggers and non-triggers
- playbook and examples
- manifest/hook contract
- evals and benchmark pack
- score dimensions and target metrics
- allowed mutations and forbidden mutations
- evidence ladder
- privacy boundary
- watchtower signals
- rollback path
- review packet
- activation notes

The chip is not “live” until router invocation, unrelated-route fallthrough, and
artifact evidence are all proven.

## Spawner Reliability Contract

Every `/run`, creator mission, PRD bridge, or mission handoff must close the
loop with one of:

- accepted with mission id
- staged with artifact/review path
- queued/running/completed/failed state
- blocked by exact failure class

No silent no-reply states are acceptable. A timeout, 4xx/5xx, rejected governor
decision, read-only runner, missing provider, missing artifact path, or invalid
mission id must become a user-readable result and a proof record.

## Task List

1. Inventory the real Telegram -> DCL -> Spawner surfaces:
   natural route, top-level handler parser, pending DCL state, creator mission
   bridge, `/run`, PRD bridge, mission board/status, artifact validation, Level
   5 access, writable-runner proof, and proof joins.
2. Record current green proof and current blockers before new implementation.
3. Keep DCL contract text centralized so Telegram route, handler, Spawner
   summary, and tests cannot drift.
4. Prove fresh DCL creation for multiple domains:
   creative/media, operations, research, coding/tooling, and coaching/advisory.
5. Prove simple chip preview still works for simple “build a domain chip”
   requests without accidentally launching work.
6. Prove rich DCL framework requests route to full creator mission, not shallow
   chip preview or generic PRD bridge.
7. Prove pending continuity:
   “go,” “doesn’t matter,” “use defaults,” repeated goal text, and scope
   follow-ups attach to the same pending chip/creator mission.
8. Prove stale memory cannot override fresh DCL intent.
9. Prove `/run` returns mission id/state or one exact failure.
10. Prove failed Spawner bridge replies are warm, short, and specific.
11. Prove Access Level 5 replies use effective sandbox and writable-runner
    evidence, not configured-only claims.
12. Update source-owner handoff docs after each Telegram/Spawner commit.
13. Keep installer pins and registry pins unchanged until owner-source truth is
    green.

## QA Matrix

| Area | Required cases |
| --- | --- |
| Intent lock | simple domain chip, rich DCL framework, non-video domain, no-create chat, stale-memory conflict |
| Pending state | go, use defaults, doesn’t matter, repeated goal, cancel, expired pending draft |
| Spawner closure | accepted mission id, staged artifact, timeout, rejected bridge, provider missing, mission id missing |
| `/run` | non-build run, build run, no-edit probe, missing reply, failed bridge reply |
| Access truth | Level 1/3/4 to Level 5, read-only runner, writable runner, configured-only sandbox rejection |
| Artifact contract | manifest/hook, triggers, non-triggers, evals, benchmark, watchtower, rollback, activation notes |
| Loop proof | baseline, candidate, score, held-out/trap checks, promotion block, regression watchtower |
| Surface quality | no raw ids unless useful, no report-card headings in natural replies, one next action |

## Planner-First Rule

Before each implementation slice, write down:

- failure being closed
- user-visible working state
- source owner
- exact test(s) that prove it
- release gate affected
- remaining blocker after the slice

Do not begin a broad code change unless that list is clear. If the list is not
clear, improve this spec or the R30 plan first.

## First Green Slice

Local Telegram commit `0cf6e5c` (`Harden DCL creator mission routing`) proves a
first narrow slice:

- rich “Spark Domain Chip Labs framework” prompts route to `creator.mission`
- top-level Telegram handler lets full creator-system DCL prompts use the
  Spawner creator mission lane instead of shallow chip preview
- DCL contract text includes manifest/hook, triggers/non-triggers, evals,
  benchmark, score dimensions, allowed mutations, watchtower, rollback, review
  packet, and activation notes
- simple domain-chip preview remains preview-first and now names watchtower
  checks in the scope question

Proof commands passed:

- `npm test -- --run tests/domainChipLabsCreator.test.ts`
- `npm test -- --run tests/conversationIntent.test.ts tests/naturalRouteDecision.test.ts tests/spawner.test.ts`
- `npm test -- --run tests/buildE2E.test.ts`
- `npm run build`
- `npm run check:line-count`

This is local runtime proof only. It does not move registry, installer, hosted,
or owner-source truth.

## Remaining Planned Slices

1. Spawner failure closure: missing mission id, timeout, rejected bridge, and
   no-reply states become exact replies and proof rows.
2. Pending continuity: “go,” “doesn’t matter,” repeated goal, and scope follow-up
   tests for both shallow chip preview and full creator mission.
3. Multi-domain DCL examples: creative/media, operations, research, coding, and
   coaching/advisory.
4. Level 5/writable truth: DCL and `/run` replies refuse effective-full-access
   claims without writable runner and effective sandbox proof.
5. Loop validation: baseline/candidate/score/held-out/watchtower proof appears
   in artifacts and status replies.
6. Source-owner handoff refresh: Telegram and Spawner local proof heads,
   patches, manifests, and docs converge before registry movement.

## Stop-Ship Conditions

Do not call this lane ready if any are true:

- DCL creation can silently fall back to generic chat or generic PRD bridge
- `/run` can fail without a reply
- Spawner can accept work without a mission id or traceable staged artifact
- Level 5 copy can claim full access without effective sandbox and writable
  proof
- generated DCL artifacts miss evals, benchmark, watchtower, rollback, or
  activation notes
- local proof exists only in runtime commits that are not represented in
  source-owner handoff docs
- R30 verifier shows new undocumented blockers
