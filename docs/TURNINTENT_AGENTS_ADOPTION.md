# Spark TurnIntent AGENTS Adoption

Date: 2026-05-31

Use this when adding or updating `AGENTS.md` in Spark repos, Codex workspaces, or the publishing machine.

## Shared Section For Every Spark-Connected Repo

```md
## Spark TurnIntent Harness Rule

This repo participates in Spark's shared agent harness. Keep deterministic machinery exact underneath, but never let raw words become action authority.

Core rules:

- Fresh user intent outranks keywords, memory, pending state, route history, mission IDs, provider names, and deterministic classifiers.
- Words alone never launch, save, schedule, publish, mutate files, create chips, write memory, run providers, call network tools, or start missions.
- Quoted examples, bug reports, meta-language, "not a command", "do not run/build/create/save/schedule", "just explain", and "stay in chat" block interruptive routes.
- Positive explicit commands must still work; do not add broad guardrails that stop real work.
- Every high-agency action edge must be `envelope_verified` or explicit `machine_origin_policy`.
- Evidence-only systems may advise, score, summarize, or propose, but must not mutate or launch.
- Any high-agency `legacy_local_gate` is a release blocker.
- Telegram/chat replies should stay human; deterministic state should not leak as robotic template text.

Before changing any action/routing surface:

1. Identify the source owner.
2. Classify the action edge: `envelope_verified`, `machine_origin_policy`, `evidence_only`, or `legacy_local_gate`.
3. Preserve no-action boundaries and positive explicit actions.
4. Add focused route/authority tests.
5. Run repo tests plus `spark os compile --json` when contract coverage changes.
6. Do not open or update PRs until local proof passes.
7. Do not merge locally from a working/debugging machine.
```

## Publishing Machine Section

```md
# Spark Publishing Machine Rules

This machine owns merge/publish discipline. Do not treat local proof from another machine as sufficient by itself.

Before merge/publish:

1. Pull the target PR branch.
2. Confirm PR checks are green or intentionally absent.
3. Confirm GitHub merge state is clean or review-blocked only.
4. Run the repo-specific proof for touched repos.
5. Run `/Users/alchemistab/.spark/bin/spark verify --registry-pins --json`.
6. Run `/Users/alchemistab/.spark/bin/spark os compile --json`.
7. Require `contract_coverage.release_blocker_count=0`.
8. Require patched runtime repos to be clean.
9. Merge in owner-safe order: Spark CLI contract, Builder, Spawner, Telegram, supporting evidence/proposal repos.
10. Update registry pins after source owner PRs land.
11. Run final `/Users/alchemistab/.spark/bin/spark status --json`.

Never publish a high-agency Spark action surface if it is only protected by raw keyword checks or stale local gates.
```

## Repo-Specific Sections

### spark-telegram-bot

```md
## TurnIntent Requirements For Telegram

Telegram owns ingress and user-facing chat, not global authority.

- Build a `spark.turn_intent.v1` envelope for each fresh user turn.
- High-agency branches must use the shared authorization wrapper.
- `deterministicRouteAllowed(...)` may propose candidates but must not be final authority for action.
- Builder bridge cannot override no-execution/plain-chat boundaries.
- Pending clarifications must expire, clear on no-action turns, and never wake from vague later replies.
- No-edit Spawner probes may launch while file mutation remains blocked.
- Telegram must not claim memory saves, schedule mutation, chip creation, mission launch, provider runs, research, or publish actions without owner proof.
- Ordinary replies must stay conversational.

Required proof:

- Harness Core action authority tests
- Telegram action authority tests
- `tests/turnIntent350Matrix.test.ts`
- full `npm test`
- `npm run build`
- live Telegram negative/positive proof when release risk is user-visible
```

### spawner-ui

```md
## TurnIntent Requirements For Spawner

Spawner owns execution. Treat every launch/mutation path as high-agency unless proven read-only.

- `/api/dispatch` requires envelope or machine-origin policy.
- PRD auto-dispatch requires envelope import or documented machine-origin policy.
- Creator mission create/execute must preserve execution policy and mutation class.
- Canvas auto-run/imported loads cannot execute from stored state alone.
- Provider dispatch must record source policy, trace, owner, and mutation class.
- No-edit requests can launch no-edit work while blocking file mutation.
- UI affordances may suggest actions, but server authority owns execution.

Required proof:

- `src/lib/server/intent-boundary.test.ts`
- `src/routes/api/dispatch/dispatch.authority.test.ts`
- `src/lib/server/prd-auto-dispatch.test.ts`
- creator mission create/execute tests
- `src/lib/services/mission-board-cards.test.ts`
- `npm run check`
- `npm run build`
```

### spark-intelligence-builder

```md
## TurnIntent Requirements For Builder

Builder owns runtime intelligence, memory orchestration, AOC, and route-family verdicts. It does not get to refight a no-action Telegram turn.

- Mutation bridges require parsed envelope authorization.
- Memory writes, schedule mutation, draft mutation, chip creation, loops, and mission starts cannot rely on local text detection alone.
- AOC, memory, and source ledgers are evidence, not hidden authority.
- Builder may ask, explain, refuse, or return a route verdict; it must not silently launch from stale context.
- Bridge payloads must be metadata-only unless a private local command explicitly needs content.

Required proof:

- `python3 -m compileall src tests`
- bridge authority tests
- focused bridge tests for changed mutation routes
- privacy scan for route/memory payloads
```

### domain-chip-memory

```md
## TurnIntent Requirements For Memory

Memory is durable evidence. It is not fresh user intent.

- Default stance is evidence-only.
- Memory may recall, score, promote, or block based on owner gates.
- Memory cannot authorize a fresh high-agency action.
- Durable save claims require proof metadata.
- Raw memory bodies stay out of cross-system projections.
- Promotion gates must remain explicit and test-backed.

Required proof:

- `python3 -m compileall src tests`
- promotion gate tests when touched
- SDK/shim tests when touched
- memory proof-card tests for projection changes
```

### spark-researcher

```md
## TurnIntent Requirements For Researcher

Researcher is proposal/evidence-first.

- Advisory packets and self-edit outputs do not auto-apply.
- Network research requires authorized network policy from the caller.
- Domain-chip authoring output remains proposal/evidence until a separate authorized owner consumes it.
- No raw provider output, private prompt text, or private artifacts in public release docs.

Required proof:

- `python3 -m compileall src tests`
- proposal/privacy tests for changed behavior
- explicit local/live evidence label in PR notes
```

### spark-character

```md
## TurnIntent Requirements For Character

Character owns persona/scoring support, not route authority.

- Persona and scoring are evidence/support surfaces.
- Live-data/search heuristics must honor network policy when invoked by Spark.
- Character evolution remains review-only until an authorized owner promotes it.
- Do not add hidden provider/network calls to normal scoring or tests.

Required proof:

- `python3 -m compileall src tests`
- character/search shim tests when touched
- public-safe artifact review for persona changes
```

### spark-voice-comms

```md
## TurnIntent Requirements For Voice

Voice is an ingress/egress capability, not permission.

- Transcripts become fresh envelopes before downstream routing.
- Install/transcribe/speak must honor mutation and network policy.
- Voice capability does not imply permission to save memory, call hosted providers, or send audio.
- Raw audio/transcript bodies do not enter shared projections by default.

Required proof:

- `python3 -m compileall src tests`
- voice hook tests
- network/provider policy tests when touched
```

### spark-cli

```md
## TurnIntent Requirements For Spark CLI

Spark CLI owns registry truth, runtime truth, and contract coverage.

- Every connected action edge must appear in contract coverage.
- High-agency `legacy_local_gate` is a release blocker.
- `spark os compile --json` must remain privacy-preserving.
- Registry/runtime pin drift must be explicit.
- Dirty installed sources cannot be hidden by local assumptions.
- Missing optional modules should be reported explicitly, not treated as silent success.

Required proof:

- `PYTHONPATH=src python3 -m unittest tests.test_system_map -v`
- `python3 -m compileall src tests`
- `/Users/alchemistab/.spark/bin/spark verify --registry-pins --json`
- `/Users/alchemistab/.spark/bin/spark os compile --json`
- `/Users/alchemistab/.spark/bin/spark status --json`
```

## New Spark Repo Template

```md
# <repo-name> Spark Agent Ruleset

## Repo Role

This repo owns:

- <source-owned truth>
- <supported read/write surfaces>
- <emitted evidence/contracts>

This repo does not own:

- Telegram ingress unless it is a Telegram repo
- Builder route/memory authority unless it is Builder
- Spawner execution unless it is Spawner
- Spark CLI registry/install truth unless it is Spark CLI

## TurnIntent Harness Rule

- Declare whether this repo is `envelope_verified`, `machine_origin_policy`, `evidence_only`, or currently `legacy_local_gate`.
- Any high-agency action requires envelope or machine-origin policy.
- Raw words, memory, pending state, route history, provider names, and mission IDs cannot authorize action.
- No-action turns block action.
- Positive explicit commands must still work.

## High-Agency Actions

This repo can:

- <list actions>

Each action must declare:

- owner
- route
- tool name
- mutation class
- authority class
- freshness/expiry
- tests

## Privacy Red Lines

Never commit or expose:

- secrets, tokens, env values, credentials, private keys
- raw account IDs
- raw prompts when metadata is enough
- provider output bodies
- memory bodies
- transcript/audio bodies unless explicitly local/private and requested

## Verification

Required before PR:

- focused route/authority tests
- build/typecheck/compile
- privacy scan for payloads and artifacts
- `spark os compile --json` when action coverage changes
- repo status clean after commit
```
