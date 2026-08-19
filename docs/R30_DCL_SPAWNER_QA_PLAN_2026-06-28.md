# R30 DCL Spawner QA Plan

Date: 2026-06-28
Status: QA planning contract; not a publication record

## Purpose

This plan defines the QA gates for making Spark Domain Chip Labs creation,
Spawner execution, Telegram usability, and quiet proof reliable enough to
continue R30 work.

It does not authorize push, deploy, tag, publish, registry movement, installer
pin movement, hosted publication, or an R30-ready claim.

## QA Principles

1. Prove the real route, not only helpers.
2. Start with a failing regression for each behavioral fix.
3. Keep proof strict underneath and conversation natural on top.
4. Treat stale memory, access chatter, and old plans as evidence, not authority.
5. Every action reply must produce one receipt: created, blocked, skipped, or
   needs confirmation.
6. Every failure must produce one exact failure class and one next action.
7. Live Telegram proof is required before Telegram-facing changes are called
   done.
8. R30 remains red until source-owner, registry, installer, hosted, runtime, and
   docs agree.

## Gate Ladder

| Gate | Scope | Required proof | Stop condition |
| --- | --- | --- | --- |
| G0 | Worktree audit | dirty files understood, unrelated changes preserved | unknown dirty changes in files being edited |
| G1 | Focused regression | smallest failing test proves the bug | helper passes but top-level route fails |
| G2 | Top-level Telegram route | `handleTextMessage` or live command path proves route/reply | stale memory or route hijack still wins |
| G3 | Cross-route drift | conversation intent, natural route, build E2E stay green | no-action wording starts work |
| G4 | Build discipline | TypeScript build and line-count pass | god-file growth without reviewed plan |
| G5 | Runtime smoke | live status, access truth, Spawner health, provider state | smoke result disagrees with local tests |
| G6 | Telegram Desktop/CUA | active chat, input safety, visual reply proof | draft present, wrong chat, or unsafe prompt |
| G7 | Live trace | live route/no-action/safe prompt rows are fresh | route mismatch, stale proof, missing safe prompt |
| G8 | R30 docs/verifier | manifests, patches, docs, verifier status updated | verifier red reason is hidden or mislabeled |

## Failure Taxonomy

Use exactly one primary failure class per bug:

- stale truth
- permission or capability drift
- route hijack
- negation failure
- pending-state leak
- provider or auth uncertainty
- supervision mismatch
- memory overriding fresh state
- UI/CLI/Telegram disagreement
- malformed success
- missing closure proof
- missing user reply
- artifact promotion overclaim
- render firewall leak

Secondary labels are allowed in evidence notes, but the primary class controls
which tests must be added.

## Local Test Matrix

### Creator Mission Closure

Required cases:

- accepted top-level `missionId`
- accepted `trace.mission_id`
- `ok:true` with no mission/review proof fails closed
- staged review/artifact path without mission id is review-only
- local filesystem path does not count as proof
- read-only creator plan never becomes runnable pending state
- pending creator mission is remembered only for proven mission id and
  non-read-only execution policy

Commands:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/spawner.test.ts tests/creatorMissionClosure.test.ts
npm test -- --run tests/domainChipLabsCreator.test.ts
```

### DCL Intent And Pending Continuity

Required cases:

- simple domain chip preview stays preview-first
- rich Spark Domain Chip Labs framework prompt routes to creator mission
- non-video domains route correctly: operations, research, coding/tooling,
  coaching/advisory, creative/media
- stale memory cannot override fresh create intent
- no-create/no-start turns remain chat
- go/use defaults/doesn't matter/repeated goal attach to the right pending
  state
- cancel and expired pending draft do not leak into new work

Commands:

```bash
npm test -- --run tests/conversationIntent.test.ts tests/naturalRouteDecision.test.ts
npm test -- --run tests/buildE2E.test.ts
```

### `/run` And Mission Relay Closure

Required cases:

- accepted mission id
- queued/running/completed/failed state
- failed bridge reply
- timeout
- rejected governor/authority
- provider missing
- malformed success
- missing reply
- no-edit probe returns exact phrase or one precise failure

Commands should include Spawner and Telegram tests once the slice begins:

```bash
cd ~/.spark/modules/spawner-ui/source
npm test -- --run src/routes/api/spark/run/spark-run.integration.test.ts

cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/buildE2E.test.ts tests/missionRelayFormatting.test.ts tests/missionRelayHealth.test.ts
```

### Level 5 Truth

Required cases:

- configured Level 5 but effective sandbox is not full-access
- writable-runner probe fails
- writable-runner probe passes
- active Telegram profile has stale read-only env
- recursive/Codex subprocess inherits effective Level 5 truth
- read-only creator mission remains read-only under Level 5

Commands:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/runnerPreflight.test.ts tests/buildE2E.test.ts
```

### Quiet Proof And Render Firewall

Required cases:

- normal replies do not expose raw ids, local paths, secrets, trace rows, hidden
  frames, or report-card headings
- action replies show one receipt only
- slash commands and diagnostics can still render dense cards
- stale proof blocks action claims without blocking normal reasoning
- failure copy uses "I could not do X because Y. Next move is Z." shape

Commands:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm test -- --run tests/telegramSurface.test.ts tests/missionRelayFormatting.test.ts tests/outboundSanitize.test.ts tests/redaction.test.ts

cd ~/.spark/modules/domain-chip-spark-qa-evidence-lane/source
PYTHONPATH=src python3 -m pytest -q
```

### Artifact Loop And Promotion Proof

Required cases:

- missing baseline blocks promotion
- missing candidate blocks promotion
- missing score/delta blocks promotion
- held-out fail blocks promotion
- trap fail blocks promotion
- rollback missing blocks promotion
- watchtower regression blocks promotion
- successful private candidate stays private until publication approval

Initial source anchors:

- `spawner-ui/source/src/lib/server/creator-mission.ts`
- `domain-chip-memory/source/src/domain_chip_memory`
- `spark-researcher/source/src/spark_researcher/collective.py`
- `spark-cli/src/spark_cli/system_map.py`

## Live Telegram Desktop/CUA Plan

Before sending anything:

1. Capture Telegram Desktop:

```bash
npx -y @steipete/peekaboo see --app Telegram --json --path /tmp/r30-telegram-preflight.png --timeout-seconds 40
```

2. Confirm the visible chat is Spark Recursive or SparkRecursive_bot.
3. Confirm the input field is empty. If a user draft is present, stop.
4. Send only no-action recapture prompts unless the user explicitly approves a
   no-edit run.

No-action prompts:

```text
I am mentioning build and mission, but do not start anything. What is the current Spark risk profile?
```

```text
I am asking about a bug in mission routing. Do not launch a mission; just explain the likely failure class.
```

```text
Do not repair anything. Just tell me whether a repair is needed right now, using fresh state.
```

```text
If memory says Spawner is down but spark live status says it is up, which source wins?
```

```text
Quick QA no-action check: I'm not asking you to create, run, repair, or publish anything. In one or two sentences, what proof would you require before a Domain Chip Labs creator mission can be considered safe to run?
```

Optional no-edit run after explicit approval:

```text
Run a tiny mission through Spawner that only replies: SPARK_QA_NO_EDIT_OK. Do not edit files.
```

After replies:

```bash
cd ~/.spark/modules/spark-telegram-bot/source
npm run control:proof:live-trace
npm run control:proof:reliability
```

Pass criteria:

- no-action prompts do not start work
- replies are concise and human
- fresh state beats memory where relevant
- no raw ids, stack traces, secrets, or local paths leak
- live proof rows are fresh and joined
- route mismatches are zero

## Evidence Packet

Every slice must leave this packet in the handoff or final report:

- failure reproduced: exact prompt/result or why not reproduced
- primary failure class
- patch scope
- local tests and results
- smoke tests and results
- live Telegram/CUA test and result
- docs/manifests/patch metadata touched
- remaining blockers
- PR/push status

## Commit And Publication Discipline

Commit only after:

- focused regression passes
- top-level route passes
- build and line-count pass
- live Telegram proof passes for Telegram-facing changes, or the user explicitly
  accepts a local-only checkpoint
- docs reflect what is green and what is still blocked

Do not push, publish, tag, move pins, update installer metadata, or claim R30
readiness from this machine unless the user explicitly changes the release
boundary and all gates agree.

## Autonomous Run Order

1. Close the current creator-mission closure refinement.
2. Clear or stop on Telegram Desktop draft before live recapture.
3. Run no-action live recapture and reliability proof.
4. Refresh Telegram patch/manifests/docs only after local and live proof agree.
5. Move to pending continuity.
6. Move to multi-domain DCL coverage.
7. Move to `/run` closure taxonomy.
8. Move to Level 5 truth.
9. Move to artifact loop/promotion proof.
10. Add DCL readiness to Spark CLI only after real proof sources exist.

## Stop Conditions

Stop and report when:

- live behavior disagrees with local tests
- Telegram Desktop has a user draft in the input field
- a no-action prompt starts work
- a helper-level fix does not hold through `handleTextMessage`
- a readiness card would go green from presence-only metadata
- source-owner or registry movement would be needed
- secrets, private paths, raw ids, or hidden frames would be exposed
