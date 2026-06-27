# Spark R30 Evidence Packet

Date: 2026-06-27
Status: local proof packet; R30 blocked before registry/installer publication

## Verdict

R30 is not ready for installer pin changes or hosted publication.

Local runtime proof is strong: Spark OS compile, live status, provenance, local installer integrity, and Telegram reliability gates are green. The remaining blockers are release-truth blockers:

- `spark-voice-comms` registry pin drift is still real.
- `spark-telegram-bot` and `spawner-ui` are still local runtime test artifacts.
- Builder still has one historical high-severity lifecycle family.
- Source-owner handoffs have not yet landed remotely.

## Local Gate Results

| Gate | Result | Evidence |
| --- | --- | --- |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` | FAIL | Executable R30 gate is present and honest. Passing checks: R30 docs, OS compile, live status, voice runtime truth, Access 5 sandbox evidence, local installer integrity, and publication order. Blocking checks: publish handoffs, release-lane registry/runtime issues, voice registry truth, registry pin drift, and pre-R30 installer pins. |
| `spark os compile --json` | PASS | `ok=true`, `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`, `voice_surface_mode=egress`, `voice_surface_blockers=1` because transcription is not ready. |
| `spark live status --json` | PASS | `ok=true`; primary Telegram and QA Telegram profiles running; Spawner UI healthy; voice importable; no repair hints. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json` | FAIL | Only failing module is `spark-voice-comms`: registry pin `21a9467e9bd4...` diverges from remote `refs/heads/main` at `c74490d68ece...`. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json` | PASS | `ok=true`; commit pins and attestation metadata present; signed commit enforcement remains report-only. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json` | PASS | Local installer manifest/scripts are internally consistent for R29. This does not claim R30 readiness. |
| Telegram `npm run control:proof:reliability` | PASS | Fresh-strict audit clean for actionable/latest gaps; live trace clean; render firewall, capsules, evals, legacy prompt surface, capability evidence, and surface eval all clean. |
| Telegram `npm run build` | PASS | TypeScript compile passed. |
| Telegram `npm run check:line-count` | PASS | `R-21 LINE-COUNT GATE: PASS`; 13 baselined god-files, 0 growing, 0 new over cap. |
| R30 unattended identity setup smoke | PASS as guarded refusal | `SPARK_HOME=/tmp/spark-r30-smoke-3umCTp spark setup --non-interactive --bot-token fake-token --admin-telegram-ids 12345 ...` exited `2` before writes. Output classified the command as `identity_access_mutation` and told the operator to rerun in an interactive terminal. The temp home remained empty; secret/dashboard scan found no matches. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --hosted-installers --json` | PASS | Hosted `agent.sparkswarm.ai` and local committed installer truth agree on R29. Hosted script bytes match hosted checksum metadata; hosted command metadata and release manifest match R29. This does not claim R30 readiness. |

## Spark OS Compile Details

Generated at `2026-06-27T10:00:59Z`.

Important fields:

- `ok=true`
- `gaps=0`
- `dirty_repo_count=0`
- `blocked_release_count=0`
- `duplicate_truth_count=2`
- `critical_duplicate_truth_count=0`
- `voice_surface_mode=egress`
- `voice_surface_blockers=1`
- `voice_surface_blocker`: voice transcription is not ready
- `requires_confirmation_for_actions=true`

Publish handoff families:

- `local_runtime_test_artifacts`: `spark-telegram-bot`, `spawner-ui`
- `builder_trace_health`: `historical_open_high_severity_events`

## R30 Release Gate Details

Fresh post-commit run of `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`:

- `r30_docs`: pass
- `owner_handoff_manifest`: pass on a clean tree; the manifest matches the live release-lane classification and commit metadata
- `r30_local_runtime_artifacts_handoff`: pass; the structured Telegram/Spawner local runtime artifact manifest matches live release-lane owners, expected registry commits, local heads, installed registry commits, proof commands, and exact patch inventory. This does not clear the `publish_handoffs` block; it keeps the handoff evidence explicit until owner-source and registry truth converge.
- `os_compile`: pass, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`
- `r30_live_status`: pass, Spark live status is green
- `publish_handoffs`: fail, open families are `local_runtime_test_artifacts` and `builder_trace_health`
- `release_lane`: fail, `0` dirty release repos and `10` release-lane issue rows, classified as `5` direct R30 blockers and `5` supporting hygiene rows
- `r30_voice_registry_decision`: fail by design until `spark-voice-comms` trace/governor commits are source-owned and registry/installed truth converge; the structured voice owner handoff manifest is present and checked for exact commits, proof commands, and rejection of the existing public tag as the final R30 voice claim
- `r30_voice_runtime_truth`: pass, R30 docs match compiled voice runtime truth with `voice_surface_mode=egress`, `voice_surface_blockers=1`, blocker `voice transcription is not ready`, and `requires_confirmation_for_actions=true`
- `r30_builder_trace_lifecycle`: fail by design until Builder owner-source closure evidence exists or the historical family is explicitly carried in release truth
- `r30_access_level5_codex_sandbox`: pass, CLI transition proof plus installed Spawner and Telegram sources prove `/access 5` activates high-agency guardrails and all known Codex lanes inherit Level 5 `danger-full-access`. The R30 gate also checks live installed env/profile state through `live_level5_env_files_all_profiled_services_full_access`: `spawner`, `telegram`, `telegram_profile:primary`, and `telegram_profile:sparkqa-bot` all exist with the Level 5 env bundle, and the services restarted after Level 5 guardrail configuration.
- `registry_pins`: fail
- `local_installers`: pass
- `publication_order`: pass, because source/registry truth is not green yet and installer pins have not been advanced to R30. The structured `source_truth_blockers` list keeps the hold explicit: `publish_handoffs`, `release_lane`, and `registry_pins`.
- `r30_installer_pins`: fail, installer still points at `spark-cli-public-installer-2026-06-26-r29`
- `hosted_installers`: pass when requested against the R29 baseline; this confirms the hosted public installer is current for R29, not that R30 is published

Direct R30 release-lane blockers:

- `domain-chip-memory`: head differs from registry; next proof command is `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts`
- `spark-intelligence-builder`: head differs from registry; next proof command is `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py`
- `spark-telegram-bot`: head differs from registry; next proof commands are `npm run control:proof:reliability`, `npm run build`, `npm run check:line-count`, and the focused access command tests
- `spark-voice-comms`: head and installed metadata differ from registry; next proof commands are `PYTHONPATH=src python3 -m pytest -q` and `spark os compile --json`
- `spawner-ui`: head differs from registry; next proof commands are the focused Codex sandbox lane tests and `npm run check`

Fresh direct-blocker proof results:

- `domain-chip-memory`: `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts` passed and reported 5 normalized contracts, 4 official adapters, and 1 shadow adapter.
- `spark-intelligence-builder`: focused Builder pytest passed, `208 passed, 26 subtests passed`.
- `spark-telegram-bot`: `npm run control:proof:reliability`, `npm run build`, `npm run check:line-count`, and focused access command tests passed. Live trace joined rows `4/4`; line-count gate passed with 13 baselined files and 0 growing/new over cap. Local head is `729273eed1b2`, including the `/access 5` high-agency activation proof and Level 5 Codex sandbox confirmation fix.
- `spark-voice-comms`: `PYTHONPATH=src python3 -m pytest -q` passed, `80 passed`.
- `spawner-ui`: focused Codex sandbox lane tests passed, `54 passed`; `npm run check` passed with 0 Svelte errors and 0 warnings. Local head is `7110dce4030a`, including direct-client, PRD auto-dispatch, and PRD bridge Level 5 Codex sandbox fixes.

These passes prove the local direct-blocker stacks are test-clean. They do not
remove the R30 block until owner-source refs, registry pins, and installed
metadata converge.

Supporting release-hygiene rows:

- `domain-chip-spark-qa-evidence-lane`: head and installed metadata differ from registry
- `spark-character`: head differs from registry
- `spark-harness-core`: head differs from registry
- `spark-researcher`: head differs from registry
- `spark-skill-graphs`: head and installed metadata differ from registry

## Hosted Installer Details

Hosted verification was refreshed after moving the local installer baseline to R29.

Current hosted truth:

- hosted release: `spark-cli-public-installer-2026-06-26-r29`
- hosted ref: `spark-cli-public-installer-2026-06-26-r29`
- hosted commit: `a6738be7a97a7254a5b09e06ce08692d99967bd6`
- local committed manifest release/ref: `spark-cli-public-installer-2026-06-26-r29`

Hosted self-consistency:

- `install.sh` hosted byte hash matches hosted checksum metadata.
- `install.ps1` hosted byte hash matches hosted checksum metadata.
- `/install/commands.json` matches hosted installer hashes.
- `/install/release-manifest.json` reports the hosted R29 release/ref.

R30 interpretation:

- Do not call hosted R29 stale or broken; this checkout now verifies the hosted R29 baseline directly.
- Do not publish R30 hosted files until source-owner handoffs, registry pins,
  installed metadata, local R30 installer manifest/scripts, and local R30
  installer verification are green.

Builder trace current health:

- status: `current_clean`
- unresolved high severity open count: `1`
- current unresolved high severity open count: `0`
- latest unresolved high severity event: `2026-06-02 09:03:25`

## Telegram Reliability Details

Fresh run generated at `2026-06-27T10:01:25Z` / `2026-06-27T10:01:26Z`.

Key results:

- Fresh-strict trace audit: actionable clean, blocking clean, latest proof gaps `0`.
- Legacy proof gaps remain backed and non-release-blocking in:
  - `telegram_route_confidence`
  - `builder_gateway`
  - `spawner_prd_trace`
- Live trace join checker: clean.
- Joined rows: `4`.
- No-action route proof: ready `4/4`.
- Safe prompt proof: ready `4/4`.
- Render firewall: clean.
- Proof capsule coverage: clean.
- Reliability eval coverage: clean.
- Capability evidence: clean.
- Surface eval: clean, `26` cases checked, `0` issues.

## Registry Pin Blocker

The registry pin gate is red for `spark-voice-comms`.

Current evidence:

- registry pin: `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee`
- remote ref checked: `refs/heads/main`
- remote head: `c74490d68ece65ffad21dc5b88f44602e1afa703`
- status: `pin_drift`

Do not solve this by pinning to `c74490d` if R30 claims the current Spark OS voice trace proof. The owner handoff packet records why: local installed voice has two additional trace/governor commits that must land or be replaced by equivalent owner-source proof first.

## Installer Smoke Details

Fresh temp-home path: `/tmp/spark-r30-smoke-3umCTp`.

The first R30 smoke corrected the installer checklist: a non-interactive command
with `--bot-token` and `--admin-telegram-ids` is not a valid success smoke
because Spark intentionally treats that as an identity/access mutation. The
right result is a fail-closed refusal before any files are generated.

Observed result:

- exit code: `2`
- action class: `identity_access_mutation`
- risk: `high`
- reason: command changes Telegram, identity, or operator access configuration
- temp Spark home: empty after refusal
- scan for `fake-token`, private-key headers, `SPARK_API_URL`, and `SPARK_DASHBOARD_URL`: no matches

This proves the unattended identity guard, not a complete R30 fresh install.
The interactive identity setup lane remains unrun and should wait until source,
registry, and installer truth are green.

## Publication Boundary

No R30 publish, push, tag, deploy, registry pin update, installer manifest edit, or hosted metadata update happened in this evidence packet.

R30 can move to installer preparation only after:

1. owner-source handoffs land or are replaced with equivalent release commits;
2. installed runtime heads are updated from owner truth;
3. registry pins and attestations are updated;
4. `verify --registry-pins` passes;
5. Spark OS compile still has `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`, and `critical_duplicate_truth_count=0`;
6. local installer integrity passes for the new R30 manifest/scripts;
7. hosted installer verification passes after authorized deploy.
