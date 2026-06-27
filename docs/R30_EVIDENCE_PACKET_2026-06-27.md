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

Fresh CLI proof refresh at `2026-06-27T21:27:09Z`:

- `PYTHONPATH=src python3 -m spark_cli.cli os compile --json`: `ok=true`, `gaps=0`
- `PYTHONPATH=src python3 -m spark_cli.cli live status --json`: `ok=true`; all listed Spark modules healthy, including Telegram relay runtime
- `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json`: `ok=false`; only failing module remains `spark-voice-comms`
- `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json`: `ok=true`
- `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json`: `ok=true`

| Gate | Result | Evidence |
| --- | --- | --- |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` | FAIL | Executable R30 gate is present and honest. Passing checks: R30 docs, OS compile, live status, publish-handoff classification, owner/local handoff docs, voice runtime truth, Access 5 sandbox evidence, unattended identity guard, local installer integrity, and publication order. Blocking checks: release-lane registry/runtime issues, voice registry truth, registry pin drift, and pre-R30 installer pins. |
| `spark os compile --json` | PASS | `ok=true`, `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`, `voice_surface_mode=egress`, `voice_surface_blockers=1` because transcription is not ready. |
| `spark live status --json` | PASS | `ok=true`; primary Telegram profile is running; stale no-token `sparkqa-bot` remains visible but stopped/unstartable; Spawner UI healthy; voice importable; no repair hints. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json` | FAIL | Only failing module is `spark-voice-comms`: registry pin `21a9467e9bd4...` diverges from remote `refs/heads/main` at `c74490d68ece...`. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json` | PASS | `ok=true`; commit pins and attestation metadata present; signed commit enforcement remains report-only. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json` | PASS | Local installer manifest/scripts are internally consistent for R29. This does not claim R30 readiness. |
| Telegram `npm run control:proof:reliability` | PASS | Fresh-strict audit clean for actionable/latest gaps; live trace clean; render firewall, capsules, evals, legacy prompt surface, capability evidence, and surface eval all clean. |
| Telegram `npm run build` | PASS | TypeScript compile passed. |
| Telegram `npm run check:line-count` | PASS | `R-21 LINE-COUNT GATE: PASS`; 13 baselined god-files, 0 growing, 0 new over cap. |
| Level 5 named-profile service proof | PASS | `PYTHONPATH=src python3 -m pytest -q tests/test_access.py -k "level5"` passed with regressions proving startable Telegram profiles must restart after Level 5 guardrail setup. If one startable profile is stale or missing, Level 5 reports `partial`, `service_enabled=false`, and effective access stays at Level 4. A stale no-token profile file is reported as `skipped_unstartable_telegram_profiles` instead of downgrading the whole install. |
| R30 unattended identity setup smoke | PASS as guarded refusal | `SPARK_HOME=/tmp/spark-r30-smoke-3umCTp spark setup --non-interactive --bot-token fake-token --admin-telegram-ids 12345 ...` exited `2` before writes. Output classified the command as `identity_access_mutation` and told the operator to rerun in an interactive terminal. The temp home remained empty; secret/dashboard scan found no matches. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --hosted-installers --json` | PASS | Hosted `agent.sparkswarm.ai` and local committed installer truth agree on R29. Hosted script bytes match hosted checksum metadata; hosted command metadata and release manifest match R29. This does not claim R30 readiness. |

## Spark OS Compile Details

Latest CLI proof refresh: `2026-06-27T21:27:09Z`.

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
- `r30_local_runtime_artifacts_handoff`: pass; the structured Telegram/Spawner local runtime artifact manifest matches live release-lane owners, expected registry commits, local heads, installed registry commits, proof commands, required terminal subjects, exact patch inventory, and fresh owner refs from the 2026-06-28 remote audit. The handoff remains visible as carried publication-bound evidence while owner-source and registry truth converge.
- `r30_local_runtime_handoff_docs`: pass; the R30 release, source-owner, owner-handoff, and evidence docs preserve the structured artifact module heads, ranges, commit counts, required terminal subjects, and proof commands from the local runtime artifact manifest.
- `os_compile`: pass, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`
- `r30_live_status`: pass, Spark live status is green
- `publish_handoffs`: pass for R30 source-truth blocking, with open families carried as explicit evidence: `local_runtime_test_artifacts` and `builder_trace_health`. The gate now separates `blocking_families=[]` from `carried_families=["local_runtime_test_artifacts", "builder_trace_health"]` so documented historical/publication-bound handoffs do not look like fresh unresolved work.
- `release_lane`: fail, `0` dirty release repos and `10` release-lane issue rows, classified as `5` direct R30 blockers and `5` supporting hygiene rows
- `r30_voice_registry_decision`: fail by design until `spark-voice-comms` trace/governor commits are source-owned and registry/installed truth converge; the structured voice owner handoff manifest is present and checked for exact full commit hashes, proof commands, and rejection of the existing public tag as the final R30 voice claim
- `r30_voice_runtime_truth`: pass, R30 docs match compiled voice runtime truth with `voice_surface_mode=egress`, `voice_surface_blockers=1`, blocker `voice transcription is not ready`, and `requires_confirmation_for_actions=true`
- `r30_builder_trace_lifecycle`: carried as explicit historical release debt while current windows remain clean. The decision gate checks that the release packet preserves the exact historical family identity: `historical_open_high_severity_events`, component `telegram_runtime`, event type `tool_call_ledger_recorded`, status/severity `blocked` / `high`, and latest event `2026-06-02 09:03:25`; owner-approved closure evidence is still required before removing the handoff.
- `r30_access_level5_codex_sandbox`: pass, CLI transition proof plus installed Spawner and Telegram sources prove `/access 5` activates high-agency guardrails and all known Codex lanes inherit Level 5 `danger-full-access`. The R30 gate also checks live installed env/profile state through `live_level5_env_files_all_profiled_services_full_access`: `spawner`, `telegram`, `telegram_profile:primary`, and `telegram_profile:sparkqa-bot` all exist with the Level 5 env bundle. Service proof now requires every startable or already-running Telegram profile to be active after guardrail configuration; `missing_or_stale_services=[]` while `skipped_unstartable_telegram_profiles=["sparkqa-bot"]` records the stale no-token profile file without downgrading the primary bot or Spawner. The access payload now names `current_process_codex_sandbox`, `service_codex_sandbox`, and `effective_codex_sandbox` separately, and the R30 gate fails if the final live payload does not report `effective_access_level=5`, `service_can_operate_whole_computer=true`, and `effective_codex_sandbox=danger-full-access`.
- `r30_unattended_identity_guard`: pass, `verify --r30` now runs the isolated fake-token setup smoke and requires exit code `2`, `identity_access_mutation` output, no generated module/setup/installed/secret state files, and no fake-token/dashboard/private-key residue.
- `registry_pins`: fail
- `local_installers`: pass
- `publication_order`: pass, because source/registry truth is not green yet and installer pins have not been advanced to R30. The structured `source_truth_blockers` list keeps the hold explicit without re-blocking carried handoffs: `release_lane`, `r30_voice_registry_decision`, and `registry_pins`. The R30 gate exposes `source_truth_ready`, `source_truth_blockers`, `installer_pins_are_r30`, and `publish_handoff_blockers` at the top level so release audits can read the publication hold without digging into nested check payloads.
- `r30_installer_pins`: fail, installer still points at `spark-cli-public-installer-2026-06-26-r29`
- `r30_hosted_publication_contract`: fail when hosted verification is requested before R30 source truth and local installer pins are green. This names the hosted result as baseline-only instead of letting a self-consistent hosted R29 pass look like R30 publication proof.
- `hosted_installers`: pass when requested against the R29 baseline; this confirms the hosted public installer is current for R29, not that R30 is published.

Direct R30 release-lane blockers:

- `domain-chip-memory`: head differs from registry; next proof command is `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts`
- `spark-intelligence-builder`: head differs from registry; next proof command is `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py`
- `spark-telegram-bot`: head differs from registry; next proof commands are `npm run control:proof:reliability`, `npm run build`, `npm run check:line-count`, and the focused access command tests
- `spark-voice-comms`: head and installed metadata differ from registry; next proof commands are `PYTHONPATH=src python3 -m pytest -q`, `spark os compile --json`, `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json`, and `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`
- `spawner-ui`: head differs from registry; next proof commands are the focused Codex sandbox lane tests and `npm run check`

Fresh direct-blocker proof results, refreshed at `2026-06-27T21:33:59Z`:

- `domain-chip-memory`: `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts` passed and reported 5 normalized contracts, 4 official adapters, and 1 shadow adapter.
- `spark-intelligence-builder`: `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py` passed, `208 passed, 26 subtests passed in 54.04s`.
- `spark-telegram-bot`: `npm test -- --run tests/runnerPreflight.test.ts tests/accessActions.test.ts tests/buildE2E.test.ts`, `npm run build`, and `PYTHONPATH=src python3 -m spark_cli.cli access status --level 5 --json` passed. Live Level 5 proof reports `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `effective_codex_sandbox=danger-full-access`, `missing_or_stale_services=[]`, and `skipped_unstartable_telegram_profiles=["sparkqa-bot"]`. Local head is `d67d0a6288c034a38b5a7d44ae008d3deda3e032` (`d67d0a6 Compact Telegram imports after Level 5 env fix`), including the `/access 5` high-agency activation proof stack, proof-oracle Level 5 runtime validation, the Telegram setup reply guard that refuses to claim full access unless `effective_codex_sandbox=danger-full-access`, operator-chat Level 5 status proof, state-plus-temp runner preflight, and effective Level 5 runtime-env promotion for Telegram subprocesses.
- `spark-voice-comms`: original local proof branch `PYTHONPATH=src python3 -m pytest -q` passed, `80 passed`; prepared local owner-lane branch `release/r30-voice-trace-governor` at `c502ec096cefb48839e3279d3392343231884415` passed, `132 passed`.
- `spawner-ui`: focused Codex sandbox lane tests passed, `20 passed` for the refreshed Level 5 worker-env slice; `npm run build` passed. Local head is `3042f8acbdde`, including direct-client, PRD auto-dispatch, PRD bridge, persisted Spawner-env Level 5 Codex sandbox fixes, shared effective-env worker access/path validation, and Codex worker env propagation.

Fresh voice owner-lane proof at `2026-06-27T21:54:18Z`:

- `spark-voice-comms` prepared release lane `release/r30-voice-trace-governor` at `c502ec096cefb48839e3279d3392343231884415`: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`.
- Delta over public owner base `c74490d68ece65ffad21dc5b88f44602e1afa703`: `src/voice_comms_chip/runtime_state.py`, `src/voice_comms_chip/spark_hook.py`, `tests/test_runtime_state.py`, and `tests/test_spark_hook.py`.
- Remote audit still shows `main` and `spark-ship-2026-06-26` at `c74490d68ece65ffad21dc5b88f44602e1afa703`; no remote `release/r30-voice-trace-governor` branch exists. This is fresh local proof only, not registry or source-owner truth.

Required terminal subjects preserved in the local runtime artifact manifest:

- `spark-telegram-bot`: `Add Telegram rich draft streaming controls`, `Package Telegram control release evidence`, `Prove Telegram Level 5 activation path`, `Fix Level 5 Codex sandbox confirmation`, `Surface effective Level 5 sandbox in Telegram`, `Block Level 5 full-access copy on read-only sandbox`, `Require effective Level 5 sandbox before operator claims`, `Harden Telegram Level 5 sandbox status`, `Harden Telegram Level 5 proof gate`, `Use proof oracle for Telegram Level 5`, `Require effective Level 5 sandbox proof in Telegram`, `Require Level 5 proof for operator access status`, `Harden Telegram Level 5 runtime env`, `Compact Telegram imports after Level 5 env fix`
- `spawner-ui`: `Carry Harness proof refs in PRD traces`, `Add Spawner PRD proof continuity repair`, `Honor Level 5 Codex sandbox in direct client`, `Honor Level 5 sandbox in PRD Codex lanes`, `Honor persisted Level 5 sandbox in Spawner`, `Honor persisted Level 5 worker access`, `Carry Level 5 env into Codex workers`

These passes prove the local direct-blocker stacks are test-clean. They do not
remove the R30 block until owner-source refs, registry pins, and installed
metadata converge.

## Level 5 Read-Only Regression Boundary

Fresh access hardening run at `2026-06-27T16:07Z`:

- `spark access status --level 5 --json`: local installed state is `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `service_codex_sandbox=danger-full-access`, `effective_codex_sandbox=danger-full-access`, and configured Codex sandbox is `danger-full-access`.
- Live env files checked: `spawner`, base `telegram`, `telegram_profile:primary`, and `telegram_profile:sparkqa-bot` all carry `SPARK_ALLOW_HIGH_AGENCY_WORKERS=1`, `SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=1`, and `SPARK_CODEX_SANDBOX=danger-full-access`.
- New regression: a Level 5 setup with startable `primary` restarted but startable `sparkqa-bot` not restarted must report `activation_state=partial`, `service_enabled=false`, `missing_or_stale_services=["spark-telegram-bot:sparkqa-bot"]`, and effective access Level 4.
- New regression: the same setup with both named Telegram profiles restarted reports `activation_state=active_for_services`, `service_enabled=true`, and effective access Level 5.
- New regression: an inactive stale no-token `sparkqa-bot` profile env file is reported as `skipped_unstartable_telegram_profiles=["sparkqa-bot"]` while active startable profiles can still prove effective access Level 5.
- New regression: normal live-status runtime expectations use the same startable-profile rule, so a no-token `sparkqa-bot` profile remains visible in Telegram profile status but no longer makes `spark live status --json` fail or makes Access 5 look read-only.
- New regression: Spawner Codex launchers must inherit persisted `spawner-ui.env` Level 5 guardrails when the service process env is stale, and must still fail closed when the persisted env bundle is partial.
- New regression: Spawner worker path approval, external-project permission, project-path validation, direct Codex client cwd resolution, Spark harness cwd resolution, command-runner validation, and `/api/spark/run` mission path creation all resolve against the same effective Level 5 env. This prevents the split where `SPARK_CODEX_SANDBOX` becomes `danger-full-access` from persisted service guardrails but a stale process env still treats the worker as workspace-bound/read-only.
- New regression: if env/profile proof is green but the final live access payload reports `effective_codex_sandbox=read-only`, `r30_access_level5_codex_sandbox` fails with `live_level5_effective_codex_sandbox_is_danger_full_access`.

This closes the read-only drift class where Telegram `/access 5` or a lower-level-to-Level-5 promotion could look globally active while one named bot profile was still running with stale sandbox settings, or while the final effective Codex sandbox was still read-only/workspace-bound.

Additional proof refresh at `2026-06-27T21:42:58Z`:

- `PYTHONPATH=src python3 -m pytest -q tests/test_access.py`: passed, `29 passed, 9 subtests passed`, including transitions from lower access levels to Level 5.
- Telegram `npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts`: passed.
- Spawner `npm test -- --run src/lib/server/prd-auto-dispatch.test.ts src/routes/api/prd-bridge/write/clarification-policy.test.ts src/lib/server/provider-clients/codex-cli-client.test.ts src/lib/services/spark-agent-bridge.test.ts src/lib/server/provider-clients/spark-harness-client.test.ts src/lib/server/high-agency-workers.test.ts`: passed, `57` tests. The known local relay stderr from stopped `sparkqa-bot`/live relay secret did not fail the tests.
- Spawner `npm run check`: passed, 0 Svelte errors and 0 warnings.

Additional read-only/access drift hardening at `2026-06-27T21:57:16Z`:

- Telegram local commit `bb38eca` (`Require effective Level 5 sandbox proof in Telegram`) removed the user-facing fallback from configured/service Codex sandbox to effective Codex sandbox in the Level 5 setup reply. Follow-up local commit `97dd34d` (`Require Level 5 proof for operator access status`) makes operator chats ask `spark access status --level 5 --json` and strengthens runner preflight to state-plus-temp write/read/delete proof.
- New regression: if `service_codex_sandbox=danger-full-access` and `configured_codex_sandbox=danger-full-access` are present but `effective_codex_sandbox` is missing, the Telegram reply must say full access is blocked and must not say whole-computer operator mode is active.
- Telegram `npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts`: passed.
- Telegram `npm run build`: passed.
- CLI `PYTHONPATH=src python3 -m pytest -q tests/test_access.py`: passed, `29 passed, 9 subtests passed`.
- Spawner focused Level 5 Codex sandbox tests passed, `50 passed`; known local relay stderr from stopped `sparkqa-bot`/live relay secret did not fail the tests.
- `spark access status --level 5 --json`: passed with `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `service_codex_sandbox=danger-full-access`, `effective_codex_sandbox=danger-full-access`, `missing_or_stale_services=[]`, and `skipped_unstartable_telegram_profiles=["sparkqa-bot"]`.

Additional CLI R30 gate hardening at `2026-06-28T02:11Z`:

- `spark-cli` local commit `d59f533` (`Require effective sandbox proof in R30 access gate`) made the executable R30 Access 5 gate reject Telegram source evidence that reads `configured_codex_sandbox` as the proof for full access. The gate now requires Telegram source evidence to read `effective_codex_sandbox`, and the checked Telegram test evidence must name `effective_codex_sandbox: 'danger-full-access'`.
- New regression: a fixture with otherwise healthy Spawner/PRD Level 5 evidence but Telegram source code reading `String(state.configured_codex_sandbox || '')` fails `r30_access_level5_codex_sandbox` with `telegram_level5_reply_reports_active_sandbox` and `telegram_level5_reply_reads_cli_level5_sandbox`.
- `PYTHONPATH=src python3 -m pytest -q tests/test_cli.py -k "r30_access_level5_codex_sandbox_status"`: passed, `6 passed`.
- `PYTHONPATH=src python3 -m pytest -q tests/test_access.py`: passed, `29 passed, 9 subtests passed`.
- Telegram `npm test -- --run tests/accessActions.test.ts tests/accessPolicy.test.ts tests/telegramCommandAuthority.test.ts`: passed.
- Spawner Level 5 focused tests passed, `43 passed`; the local relay stderr from stopped/unauthorized relay endpoints did not fail the tests.
- Clean-tree `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`: still fails only for publication truth (`release_lane`, `r30_voice_registry_decision`, `registry_pins`, and R29 installer pins), while `r30_access_level5_codex_sandbox` reports `ok=true`, `issues=[]`, `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, and `effective_codex_sandbox=danger-full-access`.

Additional Telegram runtime-env hardening at `2026-06-27T23:05:41Z`:

- Telegram local commit `464cce4` (`Harden Telegram Level 5 runtime env`) added a shared effective Level 5 env resolver for Telegram. If a Telegram process is still carrying stale `SPARK_CODEX_SANDBOX=read-only` but the persisted Telegram Level 5 env files carry the full guardrail bundle, Spark CLI checks, access setup/restart helpers, and local LLM/provider subprocesses inherit `SPARK_CODEX_SANDBOX=danger-full-access`.
- New regression: a stale read-only Telegram process env plus complete persisted Level 5 guardrails must promote to effective `danger-full-access`; a partial persisted bundle must not promote.
- Telegram `npm test -- --run tests/level5RuntimeEnv.test.ts tests/accessPolicy.test.ts tests/accessActions.test.ts tests/runnerPreflight.test.ts tests/buildE2E.test.ts`: passed.
- Telegram `npm run build`: passed.
- Live `spark access status --level 5 --json`: passed with `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `effective_codex_sandbox=danger-full-access`, `workspace_preflight.writable=true`, and `missing_or_stale_services=[]`.

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
- component: `telegram_runtime`
- event type: `tool_call_ledger_recorded`
- status/severity: `blocked` / `high`
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

Do not solve this by pinning to `c74490d` if R30 claims the current Spark OS voice trace proof. The owner handoff packet records why: local installed voice has two additional trace/governor commits that must land or be replaced by equivalent owner-source proof first. The R30 voice gate now requires their full hashes, `8a246af1eb0732aec432d88e4e4c2b6411023b7c` and `7555a363d7638537b1a9ec1ee377e460d2343323`, in the structured voice owner handoff manifest. A local owner-lane port is prepared at `c502ec096cefb48839e3279d3392343231884415`, but it is not pushed/tagged, not installed metadata truth, and not registry truth.

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
