# R30 DCL System Source Map

Date: 2026-06-28
Status: local system research map; not a publication record

## Purpose

This map gives the autonomous R30 Domain Chip Labs and Spawner goal a fast entry
point into the real system. It records where the current contract, closure,
proof, benchmark, eval, and readiness surfaces already live, and where they do
not yet line up.

Do not treat this document as release proof. It is navigation and gap evidence
only.

## Source Surfaces

| Surface | Current source | What it owns |
| --- | --- | --- |
| Telegram DCL contract text | `spark-telegram-bot/source/src/domainChipLabsCreatorContract.ts` | artifact contract, loop contract, full creator-system route pattern |
| Telegram DCL intent and route shaping | `spark-telegram-bot/source/src/conversationIntent.ts` | natural DCL/creator extraction, benchmark/autoloop language, fresh-intent routing |
| Telegram creator mission bridge | `spark-telegram-bot/source/src/spawner.ts` | creator mission request/summary, closure proof, review-only summary, pending mission proof handoff |
| Telegram pending creator state | `spark-telegram-bot/source/src/telegramPendingCreatorMissionEvidence.ts` | current thin pending mission memory keyed by chat/user |
| Spawner creator trace | `spawner-ui/source/src/lib/server/creator-mission.ts` | creator mission execution policy, status packet blockers, validation ledger ingestion, benchmark evidence summary |
| Spawner run closure | `spawner-ui/source/src/routes/api/spark/run/+server.ts` and Telegram `spawner.ts` | `/run` acceptance/failure surface; still needs shared closure classes |
| QA Evidence Lane | `domain-chip-spark-qa-evidence-lane/source` | response-surface evaluator, redaction checks, live/freshness/access/status scenarios, watchtower command |
| QA Evidence schema | `domain-chip-spark-qa-evidence-lane/source/schemas/evidence_lane_packet.schema.json` | current packet shape: scenario, candidate response, evidence sources, metadata |
| Memory benchmark discipline | `domain-chip-memory/source/src/domain_chip_memory` | official/shadow memory benchmark adapters, scorecards, mutation suggestions |
| Researcher chip starter | `spark-researcher/source/src/spark_researcher/chip_starter.py` | domain chip templates with evaluate/suggest/packets/watchtower hooks |
| Researcher promotion/collective proof | `spark-researcher/source/src/spark_researcher/collective.py` | benchmark-grounded outcome contexts, scorecards, promotion/readiness concepts |
| Spark CLI capability cards | `spark-cli/src/spark_cli/system_map.py` | creator-system and specialization-path status, proof labels, unverified benchmark/rollback warnings |
| R30 workflow docs | `spark-cli/docs/R30_DCL_SPAWNER_RELIABILITY_WORKFLOWS_2026-06-28.md` | QA ladder, quiet-proof rulesets, live Desktop/CUA rules, benchmark/eval plan |

## Current Alignment

Strong alignment exists in four places:

- Telegram already names the DCL artifact and loop contract from a small local
  contract file.
- Spawner creator missions already model read-only/manual-run policy and can
  ingest benchmark ledger evidence into `improvement_evidence`.
- QA Evidence Lane already protects the conversational surface against raw ids,
  local paths, secrets, report-card headings, stale status, and access overclaim.
- Spark CLI already keeps creator-system and specialization-path capability
  cards conservative when benchmark, rollback, or publication evidence is
  present but unverified.

## Important Gaps

1. The DCL artifact contract is still mostly text, not a shared schema consumed
   by Telegram, Spawner, QA Evidence Lane, and Spark CLI.
2. QA Evidence Lane does not yet have DCL-specific scenarios for creator
   mission closure, domain-chip promotion, stale-memory hijack of creation,
   watchtower regression, or unsupported capability-gain claims.
3. Pending creator mission state only remembers mission id and timestamp. It
   does not yet store intent type, target domain, execution policy, proof
   requirements, chosen defaults, or scope question.
4. Spawner creator missions can summarize benchmark evidence, but promotion
   proof is not yet portable as one proof capsule with baseline, candidate,
   score, held-out/trap result, watchtower, rollback, and approval.
5. `/run` and creator mission closure are adjacent but not yet one shared
   closure taxonomy.
6. Spark CLI system-map proof is conservative, but it does not yet expose a
   dedicated DCL lane readiness card with multi-domain proof count, live trace
   freshness, closure freshness, Level 5 truth, and artifact-loop completeness.

## First Autonomous Goal Hooks

Use these as the first code-reading anchors:

1. `domainChipLabsCreatorContract.ts`: promote text contract toward a reusable
   checklist/schema without changing user-facing copy first.
2. `creator-mission.ts`: inspect `applyImprovementEvidenceFromLedger`,
   `creatorMissionRequiresBenchmarkProof`, and
   `creatorMissionHasPromotionEvidence` before inventing new promotion logic.
3. `domain-chip-spark-qa-evidence-lane/validator.py`: extend evaluator
   scenarios for quiet proof and DCL creator outcomes.
4. `telegramPendingCreatorMissionEvidence.ts`: extend pending state only after
   tests define go/use-defaults/cancel/expired behavior.
5. `system_map.py`: add DCL readiness reporting only after Telegram/Spawner/eval
   proof data exists to avoid a decorative status card.

## Stop Conditions

Stop and report instead of implementing when:

- a supposed shared contract would require broad cross-repo edits without a
  failing regression
- QA Evidence Lane can only judge prose and has no evidence fields for the DCL
  scenario being added
- a new readiness card would report green from presence-only metadata
- pending-state expansion risks remembering runnable state without mission or
  review proof
- any doc or verifier change would imply R30 readiness while source-owner,
  registry, installer, hosted, or live trace truth is still red
