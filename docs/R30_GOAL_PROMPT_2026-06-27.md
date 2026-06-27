# Spark R30 Goal Prompt

Use this prompt in a writable Codex lane when starting the R30 release-prep implementation.

```text
/goal Prepare Spark R30 as the installer release where public install truth catches up with the reliability ladder, proof systems, Telegram conversational upgrades, and current runtime truth.

Current baseline:
- Telegram control/reliability layer is clean.
- `spark os compile --json` is green locally: ok=true, gaps=0, dirty_repo_count=0, blocked_release_count=0.
- Voice compiles as duplex with blockers=0, but actions still require confirmation.
- Local installer manifest/scripts are R28; hosted `agent.sparkswarm.ai` is R29.
- Remaining handoffs: Telegram and Spawner are local runtime test artifacts; Builder has one historical high-severity lifecycle family; `spark-voice-comms` registry pin needs a stable truth decision.

Rules:
- First reduce proof gaps, trace-join gaps, registry drift, and installer-truth drift.
- Do not expand UI, media, voice features, or new capabilities unless they directly close a measured proof or install-readiness gap.
- No "save the day" fixes. Prefer durable owner-source, registry, lifecycle, and installer-contract fixes.
- Do not hide historical debt. Resolve it with evidence, lifecycle status, or explicit owner handoff.
- Do not claim R30 or publish-green until source owner commits, installed runtime heads, registry pins, installer manifest, hosted metadata, checksums, and docs agree.
- Commit often after each proven slice.
- Do not push, deploy, tag, publish, or remote-merge without explicit authorization.

Task list:
1. Read `docs/R30_RELEASE_PLAN_2026-06-27.md`, `docs/R30_SOURCE_OWNER_AUDIT_2026-06-27.md`, `docs/R30_INSTALLER_PREP_2026-06-27.md`, `docs/LAUNCH_RUNBOOK.md`, and `AGENTS.md`.
2. Audit source-owner state for `spark-cli`, `spark-telegram-bot`, `spawner-ui`, `spark-voice-comms`, Builder, memory, and registry metadata. Record exact heads, pins, refs, dirty state, and owner handoff status.
3. Converge Telegram and Spawner local runtime artifacts by porting/pushing owner commits or preparing exact owner handoff instructions. Do not update registry pins until owner-source proof exists.
4. Decide and prove `spark-voice-comms` registry truth: stable tag/ref or updated proven remote head. Keep voice action-confirmation-bound.
5. Resolve Builder historical trace lifecycle with owner-approved close evidence or keep it explicit as historical handoff.
6. Only after source and registry truth are green, prepare R30 installer pins and manifest as one named batch.
7. Run proof gates:
   - `spark os compile --json`
   - `spark live status --json`
   - `spark verify --registry-pins --json`
   - `spark verify --provenance --json`
   - `spark verify --installers --json`
   - Telegram `npm run control:proof:reliability`
   - Telegram `npm run build`
   - Telegram `npm run check:line-count`
   - hosted installer verification only after authorized deploy
8. Final output must state changes, commits, proof commands/results, remaining handoffs, and whether R30 is ready, blocked, or awaiting hosted publication.
```
