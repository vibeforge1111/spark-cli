# Spark R30 Documentation Index

Date: 2026-06-27
Status: organized R30 preparation packet, not a publication record

Use this index as the entry point for R30 release prep.

## Read Order

1. [R30 release plan](./R30_RELEASE_PLAN_2026-06-27.md)
2. [R30 source owner audit](./R30_SOURCE_OWNER_AUDIT_2026-06-27.md)
3. [R30 owner handoff packet](./R30_OWNER_HANDOFF_PACKET_2026-06-27.md)
4. [R30 owner convergence queue](./R30_OWNER_CONVERGENCE_QUEUE_2026-06-28.md)
5. [R30 owner handoff manifest](./R30_OWNER_HANDOFF_MANIFEST_2026-06-27.json)
6. [R30 local runtime artifacts handoff manifest](./R30_LOCAL_RUNTIME_ARTIFACTS_HANDOFF_MANIFEST_2026-06-27.json)
7. [R30 evidence packet](./R30_EVIDENCE_PACKET_2026-06-27.md)
8. [R30 voice registry decision](./R30_VOICE_REGISTRY_DECISION_2026-06-27.md)
9. [R30 voice owner handoff manifest](./R30_VOICE_OWNER_HANDOFF_MANIFEST_2026-06-27.json)
10. [R30 Builder trace lifecycle decision](./R30_BUILDER_TRACE_LIFECYCLE_DECISION_2026-06-27.md)
11. [R30 installer preparation checklist](./R30_INSTALLER_PREP_2026-06-27.md)
12. [R30 installer baseline drift audit](./R30_INSTALLER_BASELINE_DRIFT_AUDIT_2026-06-28.md)
13. [R30 public release note draft](./R30_RELEASE_NOTE_DRAFT_2026-06-27.md)
14. [R30 goal prompt](./R30_GOAL_PROMPT_2026-06-27.md)
15. [Access Level 5 read-only elimination audit](./ACCESS_LEVEL5_READ_ONLY_ELIMINATION_AUDIT_2026-06-28.md)
16. [R30 Domain Chip Labs Telegram creator plan](./R30_DOMAIN_CHIP_LABS_TELEGRAM_CREATOR_PLAN_2026-06-28.md)
17. [R30 Domain Chip Labs and Spawner readiness spec](./R30_DCL_SPAWNER_READINESS_SPEC_2026-06-28.md)
18. [R30 DCL Spawner reliability workflows](./R30_DCL_SPAWNER_RELIABILITY_WORKFLOWS_2026-06-28.md)
19. [R30 DCL system source map](./R30_DCL_SYSTEM_SOURCE_MAP_2026-06-28.md)
20. [R30 DCL Spawner QA plan](./R30_DCL_SPAWNER_QA_PLAN_2026-06-28.md)
21. [R30 Telegram live trace recapture](./R30_TELEGRAM_LIVE_TRACE_RECAPTURE_2026-06-28.md)
22. [R30 stability, Domain Chip Labs, and Spawner goal prompt](./R30_STABILITY_DCL_SPAWNER_GOAL_PROMPT_2026-06-28.md)
23. [R30 DCL Spawner Telegram continuation handoff](./R30_DCL_SPAWNER_TELEGRAM_CONTINUATION_HANDOFF_2026-06-28.md)
24. [R30 ship convergence audit](./R30_SHIP_CONVERGENCE_AUDIT_2026-07-01.md)

## Current Verdict

R30 is prepared as a documented release packet, but it is not ready for
installer pin changes, hosted publication, or public release claims.

Latest gate truth is captured in the 2026-07-01 ship convergence audit. That
fresh packet still has `spark verify --r30 --json` and
`spark verify --registry-pins --json` red, with source truth, installer pins,
registry pins, voice registry drift, builder trace lifecycle, and hosted
installer proof still blocking public R30.

Current green proof:

- `spark verify --r30 --json` exists as the executable R30 release gate.
- The R30 owner handoff manifest is present and checked by `spark verify --r30 --json` for module and commit alignment.
- The R30 local runtime artifacts handoff manifest is present and checked by `spark verify --r30 --json` for Telegram/Spawner owner, commit, installed-metadata, and proof-command alignment.
- The R30 local runtime handoff docs are checked against the structured artifact manifest for module heads, ranges, commit counts, required terminal subjects, and proof commands.
- Spark live status is checked by `spark verify --r30 --json`.
- The publication-order guard is green while source truth is red because installer pins remain pre-R30.
- Telegram reliability/control layer is clean.
- Spark OS compile is green with `gaps=0`.
- Local and hosted installer integrity are green for the current R29 manifest.
- The voice registry decision is explicit and checked by the R30 gate.
- The voice owner handoff manifest records exact commits and proof commands, and is checked by the R30 gate.
- Voice runtime truth is checked by the R30 gate so docs cannot claim duplex/green while compiled runtime truth is `egress` with a transcription blocker.
- The Builder trace lifecycle decision is explicit and checked by the R30 gate.
- The Access 5 Codex sandbox evidence is checked by the R30 gate across CLI transition proof, direct Spawner, PRD, and Telegram activation paths.
- The Access Level 5 read-only elimination audit records the live invariant: lower-level Telegram chats may become operator only after effective `danger-full-access` service proof, Telegram runner writability proof, and default Codex launcher stale-env promotion proof.
- R30 unattended identity setup smoke fails closed before writes.
- The R30 Domain Chip Labs Telegram creator plan records the current
  conversation failure audit, universal creator UX standard, artifact contract,
  loop-engineering contract, and under-4000-character implementation goal
  prompt.
- The R30 Domain Chip Labs and Spawner readiness spec defines the great working
  state, artifact contract, Spawner closure contract, task list, QA matrix,
  planner-first rule, first local Telegram proof slice, and stop-ship
  conditions for this lane.
- The R30 DCL Spawner reliability workflows document turns the readiness spec
  into an executable QA ladder across local tests, Telegram Desktop/CUA live
  checks, DCL contract proof, Spawner closure, Level 5 truth, benchmark/eval
  proof, and R30 verifier gates.
- The R30 DCL system source map records where the local contract, closure,
  proof, benchmark, eval, and readiness surfaces already live before autonomous
  implementation begins.
- The R30 DCL Spawner QA plan defines the gate ladder, failure taxonomy, local
  test matrix, live Telegram Desktop/CUA plan, evidence packet, commit
  discipline, autonomous run order, and stop conditions.
- The R30 DCL Spawner Telegram continuation handoff records the original
  missing-proof red-test slice, the local closure-proof update, the live
  Telegram Desktop input-safety block, and the exact QA ladder for the next
  writable lane.
- The R30 Telegram live trace recapture runbook gives the exact four
  SparkRecursive_bot safe prompts and pass criteria needed before Telegram
  reliability can be called green again.
- The R30 stability/DCL/Spawner goal prompt makes Domain Chip Labs creation,
  Spawner loop closure, and Telegram capability truth explicit R30 readiness
  criteria rather than polish.

Current blockers:

- `spark-voice-comms` registry pin drift remains real.
- `spark verify --r30 --json` reports `5` release-lane registry/runtime issue rows: `5` direct R30 blockers and `0` supporting hygiene rows.
- `spark-telegram-bot` and `spawner-ui` are still local runtime test artifacts.
- Builder has one historical high-severity lifecycle family carried as explicit release debt; it must remain visible until closed with owner evidence.
- Hosted `agent.sparkswarm.ai` and local installer files now agree on R29; R30 is not hosted.
- Domain Chip Labs Telegram creation is documented as a planned R30 UX/readiness
  lane, not yet a complete installer-ready capability.
- The first local Telegram DCL creator slice is proven only as local runtime
  evidence; source-owner handoff docs and runtime manifests must be refreshed
  before it can count as source truth.
- Telegram live trace recapture is currently stale and must be refreshed in the
  real SparkRecursive_bot chat before the reliability ladder is green again.
- Domain Chip Labs creation and Spawner execution are not yet proven as a
  complete, installer-ready user path.
- The R30 installer baseline drift audit confirms no current R30 prep doc claims
  the local installer baseline is still R28; remaining R28 references are
  historical context or patch history.

## Release Rule

Do not update R30 installer pins or publish hosted installer files until
source-owner commits, installed runtime heads, registry pins, installer
manifest, checksums, hosted metadata, and documentation all agree.

Start every R30 release check with:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```
