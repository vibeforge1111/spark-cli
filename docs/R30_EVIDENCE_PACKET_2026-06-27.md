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

Fresh access/reliability refresh at `2026-06-28T05:33:54Z`:

- Telegram `npm run control:proof:live-trace`: `Status: clean`; live route proof `ready (5/4)`, no-action route proof `ready (5/4)`, safe prompt proof `ready (4/4)`, and stale live route evidence `0`.
- Telegram `npm run control:proof:reliability`: passed. Fresh-strict audit remains actionable/blocking/latest clean; legacy proof gaps are still backed only in `telegram_route_confidence`, `builder_gateway`, and `spawner_prd_trace`.
- Telegram `npm run build`: passed.
- Telegram `npm run check:line-count`: passed with `13` baselined god-files, `2` shrinking, `0` growing, and `0` new over cap.
- `spawner-ui` active Level 5 execution-lane proof: commit `029c2086efcf48444865696333ccc6c756290d83` makes the live Spawner access API report active Level 5 as `level5_operator`, `automatic`, `auto_safe` instead of a read-only lane. Focused Spawner tests passed with `22 passed`; `npm run build` passed. This remains local runtime artifact proof until owner-source and registry truth converge.

Fresh CLI proof refresh at `2026-06-28T04:37:39Z`:

- `PYTHONPATH=src python3 -m spark_cli.cli os compile --json`: `ok=true`, `gaps=0`
- `PYTHONPATH=src python3 -m spark_cli.cli live status --json`: `ok=true`; all listed Spark modules healthy, including Telegram relay runtime
- `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json`: `ok=false`; only failing module remains `spark-voice-comms`
- `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json`: `ok=true`
- `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json`: `ok=true`

Fresh access/full-permission refresh at `2026-06-28T05:46:02Z`:

- Telegram access/read-only focused suite passed: `npm test -- --run tests/accessPolicy.test.ts tests/accessActions.test.ts tests/accessLevel5Natural.test.ts tests/level5RuntimeEnv.test.ts tests/profileEnv.test.ts tests/recursiveLevel5RuntimeEnv.test.ts tests/runnerPreflight.test.ts tests/accessRepairE2E.test.ts`.
- Spawner access/provider focused suite passed: `44 passed` across access execution lanes, API integration, Codex CLI client, Spark agent bridge, and Spark harness client tests.
- CLI access Level 5 suite passed: `18 passed, 12 deselected, 6 subtests passed`.
- Live `spark access status --level 5 --json` still proves `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `service_codex_sandbox=danger-full-access`, `effective_codex_sandbox=danger-full-access`, `service_can_operate_whole_computer=true`, and `missing_or_stale_services=[]`.
- Live Spawner access API reports active Level 5 as `level5_operator`, `setupMode=automatic`, `available=true`, and `runPolicy=auto_safe`.
- Telegram `npm run build` passed; Spawner `npm run build` passed.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` remains honestly red only for `release_lane`, `r30_voice_registry_decision`, `registry_pins`, and pre-R30 installer pins.

Fresh proof-gate refresh at `2026-06-28T05:58:40Z`:

- `PYTHONPATH=src python3 -m spark_cli.cli os compile --json`: `ok=true`, `gaps=0`, `voice_surface_mode=egress`, and `voice_surface_blockers=1`.
- `PYTHONPATH=src python3 -m spark_cli.cli live status --json`: `ok=true`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json`: `ok=false`; the only failing module remains `spark-voice-comms`, with registry pin `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee` lagging `refs/heads/main` at `c74490d68ece65ffad21dc5b88f44602e1afa703`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json`: `ok=true`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json`: `ok=true`.
- Telegram `npm run control:proof:reliability`: passed; trace audit is actionable/blocking/fresh-strict clean, live trace join is clean, live route proof is `ready (5/4)`, no-action route proof is `ready (5/4)`, safe prompt proof is `ready (4/4)`, and stale live route evidence is `0`.
- Telegram `npm run build`: passed.
- Telegram `npm run check:line-count`: passed with `13` baselined god-files, `2` shrinking, `0` growing, and `0` new over cap.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --hosted-installers --json`: `ok=true`; hosted `agent.sparkswarm.ai` remains self-consistent for R29 at `spark-cli-public-installer-2026-06-26-r29`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --hosted-installers --json`: `ok=false`; `r30_hosted_publication_contract` says hosted verification is baseline-only because source/registry truth is not green (`release_lane`, `r30_voice_registry_decision`, `registry_pins`) and local installer pins are still R29.

Fresh release-truth refresh at `2026-06-28T06:16:06Z`:

- `spark-cli` was on `harness-discipline-ruleset` with pre-refresh baseline `3bc788158c535b6a8eb0353e00797d11f39cd064` (`3bc7881 Refresh R30 hosted installer evidence`) when this release-truth sweep began. The live head is intentionally read from `git rev-parse HEAD` and the `release_lane` row in `verify --r30`, because each committed evidence refresh advances the local docs/verifier lane.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`: `ok=false` by design. Passing checks include R30 docs, OS compile, live status, publish-handoff classification, owner handoff manifests, local runtime artifact handoff, CLI owner handoff docs, voice runtime truth, Access 5 sandbox evidence, unattended identity guard, local installers, and publication order.
- Top-level source truth remains blocked by exactly `release_lane`, `r30_voice_registry_decision`, and `registry_pins`; `source_truth_ready=false` and `installer_pins_are_r30=false`.
- `release_lane`: `0` dirty release repos, `5` direct R30 blockers, and `0` supporting hygiene rows. The direct blockers remain `domain-chip-memory`, `spark-intelligence-builder`, `spark-telegram-bot`, `spark-voice-comms`, and `spawner-ui`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json`: `ok=false`; the only failing module is `spark-voice-comms`, with registry pin `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee` lagging `refs/heads/main` at `c74490d68ece65ffad21dc5b88f44602e1afa703`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json`: `ok=true`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json`: `ok=true`; local installer metadata remains the self-consistent R29 baseline, `spark-cli-public-installer-2026-06-26-r29`.
- Live `spark access status --level 5 --json`: `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `service_can_operate_whole_computer=true`, `effective_codex_sandbox=danger-full-access`, `missing_or_stale_services=[]`, and `skipped_unstartable_telegram_profiles=["sparkqa-bot"]`.
- No registry pin, installer pin, hosted metadata, source tag, deploy, publish, or remote merge was changed during this refresh.

Fresh proof sweep at `2026-06-28T06:29:24Z`:

- `PYTHONPATH=src python3 -m spark_cli.cli os compile --json`: `ok=true`, `gaps=0`, `voice_surface_mode=egress`, and `voice_surface_blockers=1`.
- `PYTHONPATH=src python3 -m spark_cli.cli live status --json`: `ok=true`; unhealthy modules `[]`; Telegram profiles remain `primary` running and `sparkqa-bot` stopped/unstartable; repair hints `[]`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json`: `ok=false`; the only failing module is still `spark-voice-comms`, with pin `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee` against `refs/heads/main` at `c74490d68ece65ffad21dc5b88f44602e1afa703` (`pin_drift`).
- `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json`: `ok=true`.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json`: `ok=true`; local installer release remains `spark-cli-public-installer-2026-06-26-r29`.
- Telegram `npm run control:proof:reliability`: passed. Generated at `2026-06-28T06:27:24Z`; actionable, blocking, and fresh-strict trace audit statuses are clean; live trace join is clean; live route proof is `ready (5/4)`, no-action route proof is `ready (5/4)`, safe prompt proof is `ready (4/4)`, stale live route evidence is `0`, and legacy proof gaps remain backed-only in `telegram_route_confidence`, `builder_gateway`, and `spawner_prd_trace`.
- Telegram `npm run build`: passed.
- Telegram `npm run check:line-count`: passed with `13` baselined god-files, `2` shrinking, `0` growing, and `0` new over cap.
- `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`: `ok=false` by design; `source_truth_ready=false`; `source_truth_blockers=["release_lane","r30_voice_registry_decision","registry_pins"]`; `installer_pins_are_r30=false`; `release_lane` reports `dirty_repo_count=0`, `critical_duplicate_truth_count=0`, `5` direct R30 blockers, and `0` supporting hygiene rows. Direct blockers remain `domain-chip-memory`, `spark-intelligence-builder`, `spark-telegram-bot`, `spark-voice-comms`, and `spawner-ui`. `owner_handoff_manifest`, `r30_access_level5_codex_sandbox`, `r30_voice_runtime_truth`, `publication_order`, and local installer checks are green.
- No registry pin, installer pin, hosted metadata, source tag, deploy, publish, or remote merge was changed during this sweep.

| Gate | Result | Evidence |
| --- | --- | --- |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` | FAIL | Executable R30 gate is present and honest. Passing checks: R30 docs, OS compile, live status, publish-handoff classification, owner/local handoff docs, voice runtime truth, Access 5 sandbox evidence, unattended identity guard, local installer integrity, and publication order. Source-truth blockers are exactly `release_lane`, `r30_voice_registry_decision`, and `registry_pins`; installer pins intentionally remain pre-R30. |
| `spark os compile --json` | PASS | `ok=true`, `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`, `voice_surface_mode=egress`, `voice_surface_blockers=1` because transcription is not ready. |
| `spark live status --json` | PASS | `ok=true`; primary Telegram profile is running; stale no-token `sparkqa-bot` remains visible but stopped/unstartable; Spawner UI healthy; voice importable; no repair hints. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json` | FAIL | Only failing module is `spark-voice-comms`: registry pin `21a9467e9bd4...` diverges from remote `refs/heads/main` at `c74490d68ece...`. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json` | PASS | `ok=true`; commit pins and attestation metadata present; signed commit enforcement remains report-only. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json` | PASS | Local installer manifest/scripts are internally consistent for R29. This does not claim R30 readiness. |
| Telegram `npm run control:proof:reliability` | PASS | Fresh-strict audit clean for actionable/latest gaps; live trace clean; render firewall, capsules, evals, legacy prompt surface, capability evidence, and surface eval all clean. |
| Telegram `npm run build` | PASS | TypeScript compile passed. |
| Telegram `npm run check:line-count` | PASS | `R-21 LINE-COUNT GATE: PASS`; 13 baselined god-files, 2 shrinking, 0 growing, 0 new over cap. `src/index.ts` shrank `10804 -> 10801`; `src/recursive.ts` shrank `3198 -> 3197`. |
| Level 5 named-profile service proof | PASS | `PYTHONPATH=src python3 -m pytest -q tests/test_access.py -k "level5"` passed with regressions proving startable Telegram profiles must restart after Level 5 guardrail setup. If one startable profile is stale or missing, Level 5 reports `partial`, `service_enabled=false`, and effective access stays at Level 4. A stale no-token profile file is reported as `skipped_unstartable_telegram_profiles` instead of downgrading the whole install. |
| R30 unattended identity setup smoke | PASS as guarded refusal | `SPARK_HOME=/tmp/spark-r30-smoke-3umCTp spark setup --non-interactive --bot-token fake-token --admin-telegram-ids 12345 ...` exited `2` before writes. Output classified the command as `identity_access_mutation` and told the operator to rerun in an interactive terminal. The temp home remained empty; secret/dashboard scan found no matches. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --hosted-installers --json` | PASS | Hosted `agent.sparkswarm.ai` and local committed installer truth agree on R29. Hosted script bytes match hosted checksum metadata; hosted command metadata and release manifest match R29. This does not claim R30 readiness. |

## Spark OS Compile Details

Latest CLI proof refresh: `2026-06-28T05:58:40Z`; Spark OS compile was re-run during the same proof sweep.

Important fields:

- `ok=true`
- `gaps=0`
- `voice_surface_mode=egress`
- `voice_surface_blockers=1`
- `voice_surface_blocker`: voice transcription is not ready
- `requires_confirmation_for_actions=true`

The broad release-lane dirty/supporting counts are proven by
`PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`, not by the
top-level Spark OS compile payload. The latest clean-tree R30 gate reports `0`
dirty release repos, `5` direct R30 release-lane issues, and `0` supporting
hygiene rows.

Publish handoff families:

- `local_runtime_test_artifacts`: `spark-telegram-bot`, `spawner-ui`
- `builder_trace_health`: `historical_open_high_severity_events`

## R30 Release Gate Details

Fresh clean-tree run of `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` after the latest blocker-set evidence refresh, with the live `spark-cli` head verified by the `release_lane` row:

- `r30_docs`: pass
- `owner_handoff_manifest`: pass on a clean tree; the manifest matches the live release-lane classification and commit metadata
- `r30_local_runtime_artifacts_handoff`: pass; the structured Telegram/Spawner local runtime artifact manifest matches live release-lane owners, expected registry commits, local heads, installed registry commits, proof commands, required terminal subjects, exact patch inventory, and fresh owner refs from the 2026-06-28 remote audit. The handoff remains visible as carried publication-bound evidence while owner-source and registry truth converge.
- `r30_local_runtime_handoff_docs`: pass; the R30 release, source-owner, owner-handoff, and evidence docs preserve the structured artifact module heads, ranges, commit counts, required terminal subjects, and proof commands from the local runtime artifact manifest.
- `r30_owner_action_packet`: pass; the R30 gate exposes a read-only owner action packet for the five direct blockers with module issues, next action, proof commands, owner refs, handoff patch path, base commit, expected tree, SHA256, and `registry_movement_allowed=false`.
- `owner_handoff_manifest`: pass only when the recorded owner refs still match live remote refs. The R30 gate now runs `git ls-remote` for memory, Builder, Telegram, voice, and Spawner owner bases, release tags, owner branches, and registry baselines before treating the handoff packet as current.
- `r30_owner_handoff_patch_apply`: pass; the R30 gate now creates temporary Git worktrees from the recorded owner bases, applies every owner handoff patch, and requires `git write-tree` to match the recorded target tree before source truth can be considered ready.
- `os_compile`: pass, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`
- `r30_live_status`: pass, Spark live status is green
- `publish_handoffs`: pass for R30 source-truth blocking, with open families carried as explicit evidence: `local_runtime_test_artifacts` and `builder_trace_health`. The gate now separates `blocking_families=[]` from `carried_families=["local_runtime_test_artifacts", "builder_trace_health"]` so documented historical/publication-bound handoffs do not look like fresh unresolved work.
- `release_lane`: fail, `0` dirty release repos and `5` release-lane issue rows, classified as `5` direct R30 blockers and `0` supporting hygiene rows
- `r30_voice_registry_decision`: fail by design until `spark-voice-comms` trace/governor commits are source-owned and registry/installed truth converge; the structured voice owner handoff manifest is present and checked for exact full commit hashes, proof commands, rejection of the existing public tag as the final R30 voice claim, and live remote-ref agreement for `main`, `spark-ship-2026-06-26`, the owner branch, and the absent R30 voice release branch
- `r30_voice_runtime_truth`: pass, R30 docs match compiled voice runtime truth with `voice_surface_mode=egress`, `voice_surface_blockers=1`, blocker `voice transcription is not ready`, and `requires_confirmation_for_actions=true`
- `r30_builder_trace_lifecycle`: carried as explicit historical release debt while current windows remain clean. The decision gate checks that the release packet preserves the exact historical family identity: `historical_open_high_severity_events`, component `telegram_runtime`, event type `tool_call_ledger_recorded`, status/severity `blocked` / `high`, and latest event `2026-06-02 09:03:25`; owner-approved closure evidence is still required before removing the handoff.
- `r30_access_level5_codex_sandbox`: pass, CLI transition proof plus installed Spawner and Telegram sources prove `/access 5` activates high-agency guardrails and all known Codex lanes inherit Level 5 `danger-full-access`. The R30 gate also checks live installed env/profile state through `live_level5_env_files_all_profiled_services_full_access`: `spawner`, `telegram`, `telegram_profile:primary`, and `telegram_profile:sparkqa-bot` all exist with the Level 5 env bundle. Service proof now requires every startable or already-running Telegram profile to be active after guardrail configuration; `missing_or_stale_services=[]` while `skipped_unstartable_telegram_profiles=["sparkqa-bot"]` records the stale no-token profile file without downgrading the primary bot or Spawner. The access payload now names `current_process_codex_sandbox`, `service_codex_sandbox`, and `effective_codex_sandbox` separately, and the R30 gate fails if the final live payload does not report `effective_access_level=5`, `service_can_operate_whole_computer=true`, and `effective_codex_sandbox=danger-full-access`.
- `r30_unattended_identity_guard`: pass, `verify --r30` now runs the isolated fake-token setup smoke and requires exit code `2`, `identity_access_mutation` output, no generated module/setup/installed/secret state files, and no fake-token/dashboard/private-key residue.
- `registry_pins`: fail
- `local_installers`: pass
- `publication_order`: pass, because source/registry truth is not green yet and installer pins have not been advanced to R30. The structured `source_truth_blockers` list keeps the hold explicit without hiding carried handoffs: `release_lane`, `r30_voice_registry_decision`, and `registry_pins`. The R30 gate exposes `source_truth_ready=false`, `source_truth_blockers=["release_lane","r30_voice_registry_decision","registry_pins"]`, `installer_pins_are_r30=false`, and `publish_handoff_blockers` at the top level so release audits can read the publication hold without digging into nested check payloads.
- Source-truth readiness now also includes the CLI owner handoff docs and local runtime handoff docs. If either handoff packet goes stale, `source_truth_ready` must stay false before installer pins can move.
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

- `domain-chip-memory`: owner handoff patch `docs/r30/patches/r30-memory-authority-proof.patch` has SHA256 `58640eacefecf560df09e99a077cbbd767d37dadc37614da9d927445ec6dac83`; applying the tree-diff patch to owner branch base `3116ccaa3977` produces tree `ae30034f03ac`. Fresh proof at `2026-06-28T03:06:53Z`: `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts` passed and reported 5 normalized contracts, 4 official adapters, and 1 shadow adapter. This is review/apply material only, not registry or publication authority.
- `spark-intelligence-builder`: owner handoff patch `docs/r30/patches/r30-builder-trace-proof-stack.patch` has SHA256 `48ee6c2658d571026831c0efc311d8d58303694d732b49c4b18439c79130797d`; applying the tree-diff patch to owner branch base `c94eac853fed` produces tree `a9aedb619481`. `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py` passed, `208 passed, 26 subtests passed in 53.29s`. This is review/apply material only, not registry or publication authority.
- `spark-telegram-bot`: `npm test -- --run tests/accessLevel5Natural.test.ts tests/runnerPreflight.test.ts tests/accessActions.test.ts tests/buildE2E.test.ts`, `npm run build`, `npm test -- --run tests/healthPolling.test.ts tests/profileEnv.test.ts tests/accessActions.test.ts`, `npm test -- --runTestsByPath tests/accessActions.test.ts tests/level5RuntimeEnv.test.ts tests/accessPolicy.test.ts`, and `PYTHONPATH=src python3 -m spark_cli.cli access status --level 5 --json` passed. Fresh 2026-06-28 proof also ran the broad Telegram test runner, `npm run build`, `npm run check:line-count`, and `npm run control:proof:reliability`. Live Level 5 proof reports `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `effective_codex_sandbox=danger-full-access`, `missing_or_stale_services=[]`, and `skipped_unstartable_telegram_profiles=["sparkqa-bot"]`. Local head is `e825f0239593b62531e63af936ff69777ebf901c` (`e825f02 Harden Telegram Level 5 proof agreement`), including the `/access 5` high-agency activation proof stack, proof-oracle Level 5 runtime validation, the Telegram setup reply guard that refuses to claim full access unless `effective_codex_sandbox=danger-full-access`, operator-chat Level 5 status proof, state-plus-temp runner preflight, effective Level 5 runtime-env promotion for Telegram and Recursive bridge subprocesses, health-token preservation fix, active Telegram profile stale read-only env proof, startup profile-env refresh over stale read-only process env, Telegram Level 5 full-permission proof, the Level 5 full-permission audit doc, and natural confirmed Level 1/3/4 to Level 5 proof preservation.
- `spark-telegram-bot`: owner handoff tree-diff patch `docs/r30/patches/r30-telegram-control-reliability-stack.patch` has SHA256 `e43206fa2b52360fccdb5709a9b7fc71ddd7ca8bed2dd196aa0efb84bfd57bda`; applying it to public owner base `67ad9e6ed297` produces tree `ed24604ec558`, carrying local proof head `e825f0239593` as review/apply material only, not registry or publication authority.
- `spark-voice-comms`: original local proof branch `PYTHONPATH=src python3 -m pytest -q` passed, `80 passed`; prepared local owner-lane branch `release/r30-voice-trace-governor` at `c502ec096cefb48839e3279d3392343231884415` passed, `132 passed`.
- `spark-voice-comms`: owner handoff patch `docs/r30/patches/r30-voice-trace-governor.patch` has SHA256 `f4fc2e654b227c4ec53aef8dc013aaf409eab29196c54bd531e522a872c15dff`; applying it to public base `c74490d68ece` produces tree `e3e1f8814970` and `PYTHONPATH=src python3 -m pytest -q` passes with `132 passed`.
- `spawner-ui`: focused access-lane/Codex sandbox tests passed, `22 passed` for the refreshed Level 5 execution-lane slice; `npm run build` passed. Local head is `029c2086efcf`, including the stale read-only default Codex launch proof plus direct-client, PRD auto-dispatch, PRD bridge, persisted Spawner-env Level 5 Codex sandbox fixes, shared effective-env worker access/path validation, Codex worker env propagation, and active Level 5 full-access lane classification.
- `spawner-ui`: owner handoff tree-diff patch `docs/r30/patches/r30-spawner-runtime-artifact-tree.patch` has SHA256 `20ceb275a6f691d0c482f4947bf92dfc1890cf97cec0f992978a308c4b17c223`; applying it to owner base `fdb8fded4744` produces tree `4e685e6206f7`. Fresh proof at `2026-06-28T03:04:29Z`: the refreshed Spawner access-lane proof passed with `22 passed` and `npm run build` passed; the earlier broader Spawner check lane remains recorded as passing before the active Level 5 lane classification refresh. The known local relay stderr from stopped/unauthorized relay endpoints did not fail the focused tests. This is review/apply material only, not registry or publication authority; the tree-diff form is intentional because the local Spawner range contains a merge-shaped history.

Fresh voice owner-lane proof at `2026-06-28T07:12:13Z`; remote owner refs were rechecked at `2026-06-28T07:12:13Z`:

- `spark-voice-comms` prepared release lane `release/r30-voice-trace-governor` at `c502ec096cefb48839e3279d3392343231884415`: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`.
- Rechecked at `2026-06-28T00:54:49Z` on the same prepared local lane: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`.
- Rechecked at `2026-06-28T01:50:12Z` on the same prepared local lane: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`.
- Rechecked at `2026-06-28T03:29:13Z` on the same prepared local lane: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`; applying `docs/r30/patches/r30-voice-trace-governor.patch` to public base `c74490d68ece65ffad21dc5b88f44602e1afa703` produced tree `e3e1f881497011917fd9baa4f56db811ebccff7e` and passed `132 passed`.
- Rechecked at `2026-06-28T04:41:25Z` on the same prepared local lane: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`.
- Rechecked at `2026-06-28T07:12:13Z` on the same prepared local lane: `PYTHONPATH=src python3 -m pytest -q` passed, `132 passed`.
- Delta over public owner base `c74490d68ece65ffad21dc5b88f44602e1afa703`: `src/voice_comms_chip/runtime_state.py`, `src/voice_comms_chip/spark_hook.py`, `tests/test_runtime_state.py`, and `tests/test_spark_hook.py`.
- Remote audit at `2026-06-28T07:12:13Z` still shows `main` and `spark-ship-2026-06-26` at `c74490d68ece65ffad21dc5b88f44602e1afa703`; no remote `release/r30-voice-trace-governor` branch exists. This is fresh local proof only, not registry or source-owner truth.
- Executable remote-ref audit at `2026-06-28T03:50:55Z` passed inside `verify --r30`: `refs/heads/main` and `refs/tags/spark-ship-2026-06-26` still resolve to `c74490d68ece65ffad21dc5b88f44602e1afa703`, `refs/heads/codex/turnintent-voice-policy-20260531` still resolves to `12bddc9bd0bdd719df6ae7d4701779e7b7adfdd4`, and `refs/heads/release/r30-voice-trace-governor` is still absent.

Fresh Builder/Spawner handoff verifier result at `2026-06-28T05:06:40Z`:

- `spark-intelligence-builder` local proof head is now `ca21e183c6c04a658260b218e22fad7b67e02cc7`; regenerated `docs/r30/patches/r30-builder-trace-proof-stack.patch` has SHA256 `48ee6c2658d571026831c0efc311d8d58303694d732b49c4b18439c79130797d` and applies to owner base `c94eac853fed935ac09bed1c56912968f3365c14`, producing tree `a9aedb619481ffc9fa22d6289e82df47400948cf`. Builder proof passed: `208 passed, 26 subtests passed`.
- `spawner-ui` local proof head is now `029c2086efcf48444865696333ccc6c756290d83`; regenerated `docs/r30/patches/r30-spawner-runtime-artifact-tree.patch` has SHA256 `20ceb275a6f691d0c482f4947bf92dfc1890cf97cec0f992978a308c4b17c223` and applies to owner base `fdb8fded47447417dbf146130bddd0967e1f6bc0`, producing tree `4e685e6206f788d28d40bc13a86b87285c1982da`. Spawner access-lane focused proof passed: `22 passed`; build passed.
- Clean `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json` after the hosted-baseline evidence refresh still reports `ok=false`, by design, with `source_truth_blockers=["release_lane","r30_voice_registry_decision","registry_pins"]`. `owner_handoff_manifest`, `r30_owner_handoff_patch_apply`, `r30_access_level5_codex_sandbox`, hosted R29 baseline evidence, and `publication_order` are green; `release_lane` reports `0` dirty release repos and `5` direct R30 blockers.

Executable owner-handoff patch apply verification at `2026-06-28T03:42:45Z`:

- `domain-chip-memory`, `spark-intelligence-builder`, `spark-telegram-bot`,
  `spark-voice-comms`, and `spawner-ui` handoff patches all apply inside
  temporary Git worktrees from their recorded owner bases and produce the
  recorded target trees.
- The Telegram patch still emits the known one-line blank-EOF whitespace
  warning during `git apply`; the resulting tree still matches
  `ed24604ec5580347cf25adfc40e662d135fd9936`.
- This proof is now part of `PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json`.
  It is handoff material verification only and does not authorize registry, tag,
  installer, hosted, or installed-metadata movement.

Executable owner-ref remote audit at `2026-06-28T03:56:05Z`:

- `verify --r30` now runs live `git ls-remote` checks for the direct-blocker
  owner refs recorded in the R30 owner handoff manifest. Memory, Builder,
  Telegram, voice, and Spawner all matched their recorded `main`,
  `spark-ship-2026-06-26`, owner-branch, and registry-baseline refs.
- This is freshness proof only. It does not authorize source pushes, registry
  movement, installer pins, or hosted publication.

Required terminal subjects preserved in the local runtime artifact manifest:

- `spark-telegram-bot`: `Add Telegram rich draft streaming controls`, `Package Telegram control release evidence`, `Prove Telegram Level 5 activation path`, `Fix Level 5 Codex sandbox confirmation`, `Surface effective Level 5 sandbox in Telegram`, `Block Level 5 full-access copy on read-only sandbox`, `Require effective Level 5 sandbox before operator claims`, `Harden Telegram Level 5 sandbox status`, `Harden Telegram Level 5 proof gate`, `Use proof oracle for Telegram Level 5`, `Require effective Level 5 sandbox proof in Telegram`, `Require Level 5 proof for operator access status`, `Harden Telegram Level 5 runtime env`, `Compact Telegram imports after Level 5 env fix`, `Harden Recursive Level 5 runtime env`, `Preserve Telegram token during profile health checks`, `Harden Telegram profile Level 5 env proof`, `Refresh Telegram Level 5 profile env`, `Require Telegram Level 5 full permission proof`, `Document Level 5 full permission audit`, `Preserve natural Level 5 confirmations`, `Harden Telegram Level 5 proof agreement`
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
- Spark CLI local commit `34c0cce` makes that anti-read-only contract executable in the R30 Access 5 gate, including the stale read-only lower-to-Level-5 regression, Telegram effective runtime-env proof, and Recursive bridge subprocess env-inheritance proof.
- Spark CLI local commit `79789df` adds the Telegram R30 owner handoff patch gate, `d5a97c0` makes the direct owner handoff manifest require the Telegram and Spawner patch artifacts as publication-bound review/apply material, and the current verifier lane executes every recorded owner handoff patch apply proof inside temporary worktrees.
- Spark CLI local commit `3e8d607` makes the voice registry decision gate require the prepared local voice release lane to record both ported commits with full hashes and their source commit hashes.
- Spark CLI local docs/verifier lane carries the R30 owner handoff docs, manifests, Telegram patch artifact, Spawner proof command list, final Telegram Level 5 full-permission audit, natural confirmed Level 1/3/4 to Level 5 proof preservation, active Spawner Level 5 full-access lane classification, and hosted R29 baseline evidence as part of the publication-bound handoff. Use `git rev-parse HEAD` plus the clean `verify --r30` release-lane row for the exact current local checkpoint.
- New regression: a stale read-only Telegram process env plus complete persisted Level 5 guardrails must promote to effective `danger-full-access`; a partial persisted bundle must not promote.
- Telegram `npm test -- --run tests/level5RuntimeEnv.test.ts tests/accessPolicy.test.ts tests/accessActions.test.ts tests/runnerPreflight.test.ts tests/buildE2E.test.ts`: passed.
- Telegram `npm run build`: passed.
- Live `spark access status --level 5 --json`: passed with `effective_access_level=5`, `activation_state=active_for_services`, `service_enabled=true`, `effective_codex_sandbox=danger-full-access`, `workspace_preflight.writable=true`, and `missing_or_stale_services=[]`.

Supporting release-hygiene rows are now clear locally. `domain-chip-spark-qa-evidence-lane`, `spark-character`, `spark-harness-core`, `spark-researcher`, and `spark-skill-graphs` were converged to their verified registry pins through normal `spark update` runs with install commands skipped and no live restart.

## Hosted Installer Details

Hosted verification was refreshed after moving the local installer baseline to R29.

Current hosted truth:

- hosted release: `spark-cli-public-installer-2026-06-26-r29`
- hosted ref: `spark-cli-public-installer-2026-06-26-r29`
- hosted commit: `a6738be7a97a7254a5b09e06ce08692d99967bd6`
- hosted verified at: `2026-06-28T06:01:24Z`
- local committed manifest release/ref: `spark-cli-public-installer-2026-06-26-r29`

Hosted self-consistency:

- `install.sh` hosted byte hash matches hosted checksum metadata.
- `install.ps1` hosted byte hash matches hosted checksum metadata.
- `/install/commands.json` matches hosted installer hashes.
- `/install/release-manifest.json` reports the hosted R29 release/ref.
- `verify --r30 --hosted-installers --json` correctly fails
  `r30_hosted_publication_contract` while source truth is blocked and local
  installer pins remain R29.

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

Fresh reliability run generated at `2026-06-28T04:37:12Z` /
`2026-06-28T04:37:13Z`.

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

Fresh proof refresh at `2026-06-28T04:37:39Z`:

- Telegram `npm run build`: passed.
- Telegram `npm run check:line-count`: passed, `R-21 LINE-COUNT GATE: PASS`; 13 baselined god-files, 2 shrinking, 0 growing, 0 new over cap. `src/index.ts` shrank `10804 -> 10801`; `src/recursive.ts` shrank `3198 -> 3197`.
- Telegram `npm run control:proof:live-trace`: passed with `Status: clean`, 16 structurally joined rows, 4 joined live rows, 0 gap rows, live route proof 4/4, no-action route proof 4/4, and safe prompt proof 4/4.
- Telegram `npm run control:proof:reliability`: passed. Fresh-strict trace audit remains clean for actionable/blocking/latest gaps; legacy proof gaps remain backed and non-release-blocking in `telegram_route_confidence`, `builder_gateway`, and `spawner_prd_trace`; render firewall, proof capsules, eval coverage, legacy prompt surface, capability evidence, and surface eval are all clean.

## Registry Pin Blocker

The registry pin gate is red for `spark-voice-comms`.

Current evidence:

- registry pin: `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee`
- remote ref checked: `refs/heads/main`
- remote head: `c74490d68ece65ffad21dc5b88f44602e1afa703`
- installed metadata: `0d6e366fd04d68a00c4d6afb515f3ddee49a2ae3`
- prepared local owner-lane head: `c502ec096cefb48839e3279d3392343231884415`
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
