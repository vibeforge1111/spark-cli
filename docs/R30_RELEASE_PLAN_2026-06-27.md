# Spark R30 Release Plan

Date: 2026-06-27
Status: preparation packet, not published
Candidate release id: `spark-cli-public-installer-2026-06-27-r30`

## Release Promise

R30 should be the installer release where public install truth catches up with the reliability ladder and proof-system work already proven locally. It should not be a new-feature bucket.

R30 is ready only when a fresh user install can prove the same core claims that the running Spark stack can prove:

- Telegram streaming and rich messages are default-on and represented correctly.
- Double-preview streaming is fixed.
- Hidden context cannot render into ordinary Telegram replies.
- Action-capable routes emit proof capsules.
- No-action prompts like "do not run", "just explain", and "build mentioned" stay chat-only.
- Trace joins connect user intent, route decision, action or no-action evidence, and reply.
- Capability evidence includes last-success and last-boundary or failure proof.
- Surface evals keep Spark replies human instead of rigid.
- Voice is represented truthfully as duplex and blocker-free, but action-confirmation-bound.
- Access level 5 launches Codex workers with explicit `danger-full-access` sandboxing when Level 5 guardrails are active, including direct provider, PRD auto-dispatch, PRD bridge, and Telegram `/access 5` activation paths.
- Installer, registry, installed runtime, hosted metadata, and docs agree.

## Current Baseline

Local evidence captured on 2026-06-27:

- `spark os compile --json`: `ok=true`, `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`.
- `spark live status --json`: `ok=true`.
- Local installer integrity: passes against the committed R29 manifest.
- Hosted installer: `agent.sparkswarm.ai` serves R29, and local installer manifest/scripts now match that hosted baseline.
- `spark verify --provenance --json`: passes; signed commit enforcement remains report-only.
- `spark verify --registry-pins --json`: fails only because `spark-voice-comms` registry pin lags `refs/heads/main`.
- Spark OS publish handoffs remain visible: 2 local runtime test artifacts and 1 historical Builder trace lifecycle family.

Detailed owner-source audit: [R30 source owner audit](./R30_SOURCE_OWNER_AUDIT_2026-06-27.md). Concrete owner-lane ranges: [R30 owner handoff packet](./R30_OWNER_HANDOFF_PACKET_2026-06-27.md). Voice registry decision: [R30 voice registry decision](./R30_VOICE_REGISTRY_DECISION_2026-06-27.md). Builder trace lifecycle decision: [R30 Builder trace lifecycle decision](./R30_BUILDER_TRACE_LIFECYCLE_DECISION_2026-06-27.md). Current local proof status: [R30 evidence packet](./R30_EVIDENCE_PACKET_2026-06-27.md).

## Source Truth Order

Use this order for R30. Do not skip ahead.

1. Source-owner commits land or are ported first.
2. Installed runtime sources update second.
3. Registry pins and release metadata update third.
4. Installer scripts, manifest, and site metadata publish last as one named batch.

## Required Convergence

| Area | Current fact | R30 requirement |
| --- | --- | --- |
| `spark-telegram-bot` | Installed head `fa4c8884bb83`; registry pin `e5a1bd040986`; classified `local_runtime_test_artifact`. | Push or port the proven Telegram head, including `/access 5` activation proof, then update registry/release metadata so the runtime is no longer local-only. |
| `spawner-ui` | Installed head `7110dce4030a`; registry pin `19b7d0bff144`; classified `local_runtime_test_artifact`. | Push or port the proven Spawner head, including direct-client and PRD-lane Level 5 Codex sandbox fixes, then update registry/release metadata. |
| `spark-cli` | Local head includes R30 prep plus the voice source discovery fix; manifest now points at the public R29 baseline. | Include the voice discovery fix and R30 docs in the source-owner release before changing installer pins to R30. |
| `spark-voice-comms` | Installed source is importable; registry pin `21a9467e...` lags remote `main`/tag `spark-ship-2026-06-26` at `c74490d...`; local voice checkout `7555a36...` is ahead of its branch with trace/governor proof. | Do not pin R30 voice to the earlier public tag if R30 claims current voice trace proof. Port/tag the local voice trace/governor commits first, then update registry and installed-state truth together. |
| Builder trace health | Current windows clean; one historical high-severity lifecycle family remains from 2026-06-02. | Close with owner-approved lifecycle evidence or keep explicit as a non-hidden historical publish handoff. |
| Hosted installer | Hosted and local installer truth agree on R29. | Publish R30 only after local manifest, hosted scripts, hosted checksums, commands metadata, and release manifest all agree on R30. |

## R30 Must Have

1. Registry/release convergence for Telegram and Spawner.
2. Voice pin decision with proof.
3. R30 installer manifest and script release pins updated only after the source tag exists.
4. Hosted R30 metadata convergence at `agent.sparkswarm.ai`.
5. Fresh local proof packet:
   - `spark verify --r30 --json`
   - `spark os compile --json`
   - `spark live status --json`
   - `spark verify --registry-pins --json`
   - `spark verify --provenance --json`
   - `spark verify --installers --json`
   - `spark verify --installers --hosted-installers --json` after site deploy
6. Telegram proof packet:
   - `npm run control:proof:reliability`
   - `npm run build`
   - `npm run check:line-count`
7. Fresh install or upgrade smoke from R29 to R30 in an isolated `SPARK_HOME`, with two separate lanes:
   - unattended runs must refuse Telegram identity/access mutation before writes;
   - interactive identity setup must be approved and proven only after R30 source, registry, and installer truth are green.

## R30 Should Have

- A short public release note that says R30 makes installer truth match running Spark truth.
- Optional-module proof for `telegram-voice-starter`, QA Evidence Lane, and Skill Graphs before claiming the entire 11-repo lane ship-ready.
- One R30 evidence packet that records command, timestamp, result, and remaining handoff status.

## Out Of Scope

- New UI expansion.
- New media or voice features beyond proof and truthful capability boundaries.
- More Telegram route-safety repair unless a fresh proof fails.
- Hiding historical trace debt for a green-looking release.
- Sandbox/SSH/Modal onboarding in the initial installer.

## Stop-Ship Conditions

Stop R30 publication if any of these are true:

- `spark os compile --json` reports dirty repos, blocked releases, gaps, or critical duplicate truths.
- Registry pins do not match their declared remote refs.
- Hosted installer bytes, hosted checksums, commands metadata, and release manifest disagree.
- Telegram reliability proof fails, or live Telegram behavior disagrees with local proof.
- A local-only runtime commit is represented as public release truth.
- Setup writes raw secrets into generated module env files.
- A non-interactive installer/setup path can mutate Telegram identity or operator access.
