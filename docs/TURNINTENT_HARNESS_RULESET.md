# Spark TurnIntent Harness Ruleset

Date: 2026-05-31

> Historical predecessor note: this file describes the TurnIntent-era adoption
> rules that led to Harness Core. Current installer-facing authority is
> `TurnIntentEnvelopeVNext` plus `GovernorDecisionV1`,
> `AuthorizationDecisionV1`, matching `ToolCallLedgerV1`, and owner consumer
> verification from `@spark/harness-core`. Treat old `spark.turn_intent.v1`
> wording as compatibility/migration context, not sufficient execution
> authority.

This is the Spark-wide rule for preventing deterministic route fighting, word hijacks, stale pending-state launches, memory-driven authority drift, and accidental tool calls.

Spark may keep deterministic systems underneath for speed, routing evidence, health checks, and state machines. Those systems must never become authority for a high-agency action unless they are bound to the shared TurnIntent harness contract.

> Raw words may propose candidates. Fresh user intent authorizes action.

## Non-Negotiables

1. Fresh user intent outranks keywords.
2. Fresh user intent outranks memory.
3. Fresh user intent outranks pending state.
4. Fresh user intent outranks stale route history.
5. Fresh user intent outranks mission IDs and provider names.
6. Words alone never launch, save, schedule, publish, mutate files, create chips, write memory, call network tools, run providers, or start missions.
7. Quoted examples, bug reports, meta-language, and no-action turns must block interruptive routes.
8. Positive explicit commands must still work without needless friction.
9. Deterministic machinery stays underneath; Telegram/chat surfaces stay human.
10. Every high-agency edge must appear in Spark CLI contract coverage.

## Required Edge Classes

Every Spark action edge must be classified as one of these:

- `envelope_verified`: a fresh `spark.turn_intent.v1` envelope authorizes route, owner, tool, mutation class, and constraints.
- `machine_origin_policy`: an internal event is allowed by an explicit non-user policy, with source owner and scope documented.
- `evidence_only`: the surface can read, summarize, score, advise, or propose, but cannot mutate or launch.
- `legacy_local_gate`: old local protection. This is allowed only for harmless local/read-only behavior. Any high-agency `legacy_local_gate` is a release blocker.

## High-Agency Actions

These always require `envelope_verified` or explicit `machine_origin_policy`:

- mission launch, dispatch, queue, execute, resume, pause, cancel
- file creation, file edit, scaffold, build, repair, apply, write
- memory write, memory promotion, durable preference save
- draft save/update/delete
- schedule create/update/delete
- chip/domain-chip creation or promotion
- provider run, external research, browser/network use
- publish, deploy, share, public promotion, network absorption
- startup-operator/self-improvement loops that can mutate state or start work
- voice install/transcribe/speak when it causes network, file, memory, or chat side effects

## No-Action Boundaries

The following must block interruptive routes unless a later fresh turn explicitly changes intent:

- "do not run/build/create/save/schedule/start/launch/publish"
- "not a request", "not a command", "not an instruction"
- "just explain", "explain only", "stay in chat", "we can talk here"
- quoted action phrases
- examples of action words
- bug reports about action routing
- architecture discussion about routing/action systems
- benchmark or QA prompt creation that mentions words like score, run, stale, build, mission, provider
- provenance questions about a prior action

## Positive Intent Rules

Explicit action should still be fast:

- A no-edit Spawner probe may launch while file mutation remains blocked.
- "Do not edit files" blocks file edits, not the requested no-edit mission.
- "Show/check/report Spark QA score" may read or run the score route only when the phrase explicitly targets Spark QA score proof.
- Bare "go" applies only to a live pending action with matching scope and expiry.
- Pending state must clear on conversation-only boundaries.
- Stale pending state must never wake up from a vague later turn.

## TurnIntent Envelope Requirements

Every envelope must preserve:

- turn/session identity
- selected route and owner system
- matched and blocked candidates
- directive constraints: no execution, no file mutation, no publish, local only, network policy
- allowed tools and mutation classes
- source of confidence
- freshness/expiry
- trace reference where applicable
- redacted evidence, not raw private content

Downstream systems must consume the envelope rather than re-reading raw user text as authority.

## Tool Call Lifecycle

Every tool call that can act should be represented as:

1. proposed route candidate
2. fresh TurnIntent verdict
3. owner/tool/mutation authorization
4. execution or refusal
5. result verdict
6. trace/evidence row
7. user-facing reply

Hooks may observe, block, enrich evidence, or transform results. Hooks must not become a hidden second router.

## Memory Rules

- Memory is evidence, not permission.
- Recalled memory may support context, but cannot override the current turn.
- Durable memory saves require owner proof.
- Memory bodies stay private; cross-system surfaces use proof metadata.
- Memory-sourced suggestions must remain candidates until imported by a fresh envelope.

## Pending-State Rules

- Pending state has owner, route, scope, expiry, and constraints.
- Pending state cannot outlive a user no-action turn.
- Pending state cannot cross from one surface into another unless explicitly imported.
- Pending state cannot authorize a higher mutation class than the fresh turn allows.

## Machine-Origin Policy

Machine-origin events are allowed only when:

- the source owner is explicit
- the event is scoped to a prior authorized user action or a documented service loop
- mutation class is bounded
- trace evidence exists
- user-facing surfaces do not present it as fresh user intent

Examples: mission relay progress, health polling, system-map compile, verifier runs, explicit scheduled task execution.

## Human Surface Rule

The harness can be exact internally. Telegram and chat must stay natural:

- ordinary answers should be one or two useful sentences
- dense cards are for status, diagnostics, review queues, and raw detail requests
- do not expose router internals unless asked
- do not turn every reply into headings like Mission, Provider, Move, Status
- if a reply feels deterministic, treat it as a product bug

## New Repo Adoption Rule

Any new repo that connects to Spark must declare:

- repo role and source owner boundaries
- high-agency actions it can perform
- whether it consumes TurnIntent envelopes
- whether it emits machine-origin events
- whether it is evidence-only
- privacy red lines
- contract coverage entries
- focused tests
- release gate commands

No new connected repo should be considered Spark-ready until `spark os compile --json` can classify its action edges with zero high-agency `legacy_local_gate` blockers.

## Release Gates

Before any PR claims Spark action/routing safety:

1. Add or update focused regression tests for the exact route.
2. Run the repo-specific focused tests.
3. Run typecheck/build/compile.
4. Run `spark os compile --json`.
5. Confirm `contract_coverage.release_blocker_count` is `0`.
6. Confirm dirty runtime truth is `0` for patched repos.
7. Confirm live Spark health when runtime behavior changed.
8. For Telegram-facing action boundaries, run both negative and positive live proof when appropriate.
9. Open or update PRs only after local proof passes.
10. Do not merge locally from the working machine.

## Spark CLI Responsibilities

Spark CLI owns the durable read-model and release gate for this standard:

- maintain `CONTRACT_COVERAGE_ACTION_EDGES`
- classify every connected action edge
- fail release on high-agency `legacy_local_gate`
- keep `spark os compile --json` privacy-preserving
- report missing optional modules explicitly
- keep registry/runtime truth visible
- keep docs and AGENTS guidance aligned with contract coverage behavior

## Durable Mantra

Understand once. Authorize once. Execute only through the owner. Preserve proof. Keep the surface human.
