# Spark R30 Documentation Index

Date: 2026-06-27
Status: organized R30 preparation packet, not a publication record

Use this index as the entry point for R30 release prep.

## Read Order

1. [R30 release plan](./R30_RELEASE_PLAN_2026-06-27.md)
2. [R30 source owner audit](./R30_SOURCE_OWNER_AUDIT_2026-06-27.md)
3. [R30 owner handoff packet](./R30_OWNER_HANDOFF_PACKET_2026-06-27.md)
4. [R30 owner handoff manifest](./R30_OWNER_HANDOFF_MANIFEST_2026-06-27.json)
5. [R30 local runtime artifacts handoff manifest](./R30_LOCAL_RUNTIME_ARTIFACTS_HANDOFF_MANIFEST_2026-06-27.json)
6. [R30 evidence packet](./R30_EVIDENCE_PACKET_2026-06-27.md)
7. [R30 voice registry decision](./R30_VOICE_REGISTRY_DECISION_2026-06-27.md)
8. [R30 voice owner handoff manifest](./R30_VOICE_OWNER_HANDOFF_MANIFEST_2026-06-27.json)
9. [R30 Builder trace lifecycle decision](./R30_BUILDER_TRACE_LIFECYCLE_DECISION_2026-06-27.md)
10. [R30 installer preparation checklist](./R30_INSTALLER_PREP_2026-06-27.md)
11. [R30 public release note draft](./R30_RELEASE_NOTE_DRAFT_2026-06-27.md)
12. [R30 goal prompt](./R30_GOAL_PROMPT_2026-06-27.md)

## Current Verdict

R30 is prepared as a documented release packet, but it is not ready for
installer pin changes, hosted publication, or public release claims.

Current green proof:

- `spark verify --r30 --json` exists as the executable R30 release gate.
- The R30 owner handoff manifest is present and checked by `spark verify --r30 --json` for module and commit alignment.
- The R30 local runtime artifacts handoff manifest is present and checked by `spark verify --r30 --json` for Telegram/Spawner owner, commit, installed-metadata, and proof-command alignment.
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
- R30 unattended identity setup smoke fails closed before writes.

Current blockers:

- `spark-voice-comms` registry pin drift remains real.
- `spark verify --r30 --json` reports `10` release-lane registry/runtime issue rows: `5` direct R30 blockers and `5` supporting hygiene rows.
- `spark-telegram-bot` and `spawner-ui` are still local runtime test artifacts.
- Builder has one historical high-severity lifecycle family that must remain visible or be closed with owner evidence.
- Hosted `agent.sparkswarm.ai` and local installer files now agree on R29; R30 is not hosted.

## Release Rule

Do not update R30 installer pins or publish hosted installer files until
source-owner commits, installed runtime heads, registry pins, installer
manifest, checksums, hosted metadata, and documentation all agree.

Start every R30 release check with:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```
