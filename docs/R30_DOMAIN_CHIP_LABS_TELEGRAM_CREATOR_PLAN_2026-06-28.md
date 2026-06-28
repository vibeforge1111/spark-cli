# R30 Domain Chip Labs Telegram Creator Plan

Generated: 2026-06-28

## Current R30 Handoff Truth

R30 is not an installer-publish lane yet. It is still a source-owner convergence lane.

- Telegram proof head: `8958d01a80a42c7c64c45c63956c1001568a6e11`
- Telegram owner base: `67ad9e6ed297baf6c9daa74b879fa45bc45bd579`
- Telegram handoff patch: `docs/r30/patches/r30-telegram-control-reliability-stack.patch`
- Patch SHA256: `2d5f14ed8eea42b9707e06cf88d46a1b2eef6e7ab4e1c0465542810fcc71c160`
- Patch apply tree after `git add -A`: `94671ae63d4e34fa8a412ccc04ca75f6cac93bc8`
- Local Telegram proof is review/apply material only. It is not registry, installer, or hosted publication authority.

The latest Telegram slice improves the domain-chip creation preview and adds regression coverage for fresh “build a domain chip” intent. It does not complete the full Domain Chip Labs creator lane.

## Problem To Solve

The R30 installer should not only prove tracing and permissions. It should let a normal Telegram conversation create a real Spark Domain Chip Labs artifact without route hijacks, stale caution, missing replies, or read-only confusion.

The failed conversation showed these gaps:

- explicit domain-chip creation was previewed through a generic name-generation prompt
- stale philosophy/caution replies overrode the user's fresh build intent
- Access Level 5, runner writability, and mission creation proof were mixed together
- `/run` did not close the loop with a mission id or exact failure
- the user had to understand Spark internals to know what happened

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

## Implementation Task List

1. Inventory current DCL creation routes, pending state, Spawner creator mission bridge, chip scaffolding, recursive loop sync, and Domain Chip Labs artifact expectations.
2. Build a shared `domainChipCreatorLane` contract for parse -> preview -> confirm -> stage/create -> prove -> follow-up.
3. Replace generic domain-chip preview/fallback copy with DCL-specific UX across Telegram natural chat, pending confirmations, `/run`, and creator-mission paths.
4. Add capability-truth replies for DCL creation: allowed, writable, staged, created, blocked-here, missing-proof, or failed-with-reason.
5. Add a DCL review packet schema and ensure generated PRDs require the full artifact and loop-engineering contract.
6. Add tests for explicit creation, scope follow-ups, stale memory conflicts, read-only runner, Level 5 writable runner, failed Spawner bridge, missing reply after `/run`, router fallthrough, loop benchmark, and watchtower proof.
7. Update R30 docs and release gates so DCL Telegram creator quality is a measured installer-readiness criterion, not polish.
8. Keep registry/installer pins blocked until source-owner refs and local runtime artifacts converge.

## Goal Prompt

Use this in a writable Codex lane:

```text
Goal: Make Spark R30’s Telegram Domain Chip Labs creator lane genuinely usable and evidence-backed.

Start from current R30 handoff truth. Do not publish, push, tag, deploy, move registry pins, or claim installer readiness. First reduce measured proof, trace-join, handoff, and DCL creator UX gaps.

Audit Telegram, Spawner creator missions, Domain Chip Labs standards, chip manifests/hooks, recursive/self-improving loops, pending-state UX, Access Level 5 capability truth, and R30 release docs. Preserve the current reliability ladder and source-owner gates.

Implement a durable DCL Telegram creator lane: natural “build/create a domain chip” intent must lock to domain_chip.create, ask at most one relevant scope question, keep stale memory/caution from hijacking current intent, stage/create only when authorized and writable, and always return either chip/mission proof or one exact failure. Default scope should support ideation only, shot/prompt packets, or full workflow. Generated artifacts must include purpose, triggers, non-triggers, playbook, examples, manifest/hook contract, evals, benchmark pack, score dimensions, allowed mutations, evidence ladder, privacy boundary, watchtower, rollback, review packet, and activation notes.

Add verifiable loop engineering: baseline, candidate, score, compare, promote only on proof, held-out checks, watchtower signals, and proof capsules joining user intent -> route -> action/no-action -> artifact/eval/reply. Telegram surface should be warm and concise; raw ledgers stay behind inspect/status.

Add regression tests for explicit DCL creation, scope follow-ups, stale-memory conflict, read-only runner, Level 5 writable runner, failed Spawner bridge, missing /run reply, router fallthrough, benchmark loop proof, and watchtower regression. Run focused tests, build, line-count, and R30 verifier. Commit after each proven slice. Update R30 docs with what is green, what remains blocked, and why.
```
