# Spark R30 Source Owner Audit

Date: 2026-06-27
Status: current-state audit for R30 prep; not a publication record

## Purpose

This audit records the owner-source and registry state R30 must converge before installer pins or hosted metadata can move. It keeps local proof separate from public release truth.

Concrete port/push ranges are recorded in [R30 owner handoff packet](./R30_OWNER_HANDOFF_PACKET_2026-06-27.md).

## Summary

R30 is not ready for installer pin changes yet.

The current Spark stack is clean enough to keep preparing R30, but several R30-relevant changes are still local or ahead of owner-source refs:

- `spark-telegram-bot`: local R30 proof/docs head has no owner remote branch yet; public `spark-ship-2026-06-26` exists at remote `main` but does not contain the local R30 reliability/access stack.
- `spawner-ui`: local branch is ahead of the owner release branch; public `spark-ship-2026-06-26` exists at remote `main` but does not contain the local PRD/Level 5 Codex sandbox stack.
- `spark-voice-comms`: the public `spark-ship-2026-06-26` tag is test-clean, but it does not include the local voice trace/governor commits that make the current Spark OS voice proof truthful.
- `domain-chip-memory` and `spark-intelligence-builder`: local heads are ahead of owner branches.
- Builder trace health still has one historical lifecycle family; the R30 gate now carries it as explicit historical release debt while current windows stay clean and the exact family remains visible.
- `spark-cli`: local R30 prep now includes the executable R30 gate, live-status gate, Access 5 Codex sandbox gate with named-profile env proof (`live_level5_env_files_all_profiled_services_full_access`) and explicit `current_process_codex_sandbox` / `service_codex_sandbox` / `effective_codex_sandbox` fields, the `r30_unattended_identity_guard` fake-token smoke, voice runtime truth gate with `requires_confirmation_for_actions=true`, local runtime artifact handoff gate, structured publication source blockers (`source_truth_blockers`), the R29 hosted/local installer baseline alignment, and the `r30_hosted_publication_contract` check that prevents hosted R29 integrity from being read as R30 publication proof. It has not been published or tagged as R30.

## Current Heads And Pins

| Area | Local installed/source head | Owner remote / release truth | Registry or installer truth | R30 action |
| --- | --- | --- | --- | --- |
| `spark-cli` | current `harness-discipline-ruleset` head; verify with `git rev-parse HEAD` in `~/.spark/tools/spark-cli` | remote R29 tag `7751ef43581c`; remote `master` `a6738be7a97a` | local installer manifest/scripts now match R29 | Keep R30 docs, live-status gate, Access 5 sandbox gate with `live_level5_env_files_all_profiled_services_full_access` plus `effective_codex_sandbox`, `r30_unattended_identity_guard`, voice runtime truth gate with `requires_confirmation_for_actions=true`, local runtime artifact handoff gate, publication-order `source_truth_blockers`, hosted-publication contract, and voice discovery fix local until source release/tag is authorized. |
| `spark-telegram-bot` | `a87f4ebe2298` (`a87f4ebe2298069add925b1f1f5a0806a6979ee8`) on `harness-discipline-line-count-gate` | no matching owner branch found; remote `main` and `spark-ship-2026-06-26` `67ad9e6ed297`; registry baseline tag `spark-ship-2026-06-22` `e5a1bd040986` | registry pin `e5a1bd040986`; classified `local_runtime_test_artifact` | Push/port `a87f4ebe2298` or an equivalent owner release commit onto the current owner release base before changing registry. |
| `spawner-ui` | `e0fbb5b60c22` on `release/stability-2026-06-02-spawner-authority` | owner branch `fdb8fded4744`; remote `main` and `spark-ship-2026-06-26` `451d009aad84`; registry baseline tag `spark-ship-2026-06-22` `19b7d0bff144` | registry pin `19b7d0bff144`; classified `local_runtime_test_artifact` | Push/port the local merge/fix stack, including direct-client, PRD-lane, persisted Level 5 Codex sandbox fixes, and shared effective-env worker access/path validation, onto the current owner release base before changing registry. |
| `spark-voice-comms` | prepared local lane `release/r30-voice-trace-governor` at `c502ec096cef`; original local proof branch `7555a363d763` ahead 2 of owner branch | owner branch `12bddc9bd0bd`; remote `main` and tag `spark-ship-2026-06-26` `c74490d68ece` | registry pin `21a9467e9bd4`; installed state still records `0d6e366fd04d` | Prepared local owner-lane port passed tests, but R30 voice remains blocked until that lane is source-owned remotely and installed/registry truth converge. |
| `domain-chip-memory` | `1fd272e519b5`; ahead 1 | owner branch `3116ccaa3977`; remote `main` and `spark-ship-2026-06-26` `72a660a69c0c`; registry baseline tag `spark-ship-2026-06-22` `f7f16a6ea8ee` | registry pin `f7f16a6ea8ee` | Owner can review/push the vNext memory authority proof against the current owner release base before R30 registry claims. |
| `spark-intelligence-builder` | `f21522accf66`; ahead 43 | owner branch `c94eac853fed`; remote `main` and `spark-ship-2026-06-26` `9d7bdefaa9a0`; registry baseline tag `spark-ship-2026-06-22` `e7f80fbf03bd` | registry pin `e7f80fbf03bd` | Owner can review/push or port the merge/fix stack against the current owner release base. The Builder historical trace lifecycle is carried as explicit historical release debt, not hidden closure. |

## Fresh Remote Ref Audit

Fresh `git ls-remote` audit on 2026-06-27 confirmed newer public owner refs that are not yet registry truth for R30. Rechecked on 2026-06-28 local time; the direct-blocker owner refs below still matched the packet:

| Repo | Fresh public owner ref | R30 local/proof ref | Registry/install truth |
| --- | --- | --- | --- |
| `spark-telegram-bot` | `main` / `spark-ship-2026-06-26` at `67ad9e6ed297` | local `a87f4ebe2298` | registry `e5a1bd040986` |
| `spawner-ui` | `main` / `spark-ship-2026-06-26` at `451d009aad84`; owner release branch `fdb8fded4744` | local `e0fbb5b60c22` | registry `19b7d0bff144` |
| `spark-voice-comms` | `main` / `spark-ship-2026-06-26` at `c74490d68ece`; owner branch `12bddc9bd0bd` | prepared local owner-lane `c502ec096cef`; original local proof branch `7555a363d763` | registry `21a9467e9bd4`; installed metadata `0d6e366fd04d` |
| `domain-chip-memory` | `main` / `spark-ship-2026-06-26` at `72a660a69c0c`; owner branch `3116ccaa3977` | local `1fd272e519b5` | registry `f7f16a6ea8ee` |
| `spark-intelligence-builder` | `main` / `spark-ship-2026-06-26` at `9d7bdefaa9a0`; owner branch `c94eac853fed` | local `f21522accf66` | registry `e7f80fbf03bd` |

This means R30 owner handoff work should not blindly port onto the older registry
baseline. Each owner must choose the correct current release base, prove the
ported stack there, then move installed metadata and registry pins together.

## Voice Registry Decision

Do not update `spark-voice-comms` registry truth to `spark-ship-2026-06-26` as the final R30 voice claim.

Evidence:

- Remote tag `spark-ship-2026-06-26` points at `c74490d68ece65ffad21dc5b88f44602e1afa703`.
- Temporary detached worktree at `c74490d68ece` passed `PYTHONPATH=src python3 -m pytest -q`: `121 passed`.
- Original local voice proof branch at `7555a363d763` passed `PYTHONPATH=src python3 -m pytest -q`: `80 passed`.
- Prepared local owner-lane branch `release/r30-voice-trace-governor` at `c502ec096cefb48839e3279d3392343231884415` passed `PYTHONPATH=src python3 -m pytest -q`: `132 passed`.
- The local branch adds the current Spark OS voice proof pieces over the owner branch:
  - `8a246af Join voice runtime state traces`
  - `7555a36 Accept media transcription governor authority`
- The prepared local owner-lane replacement commits are:
  - `4eef348 Join voice runtime state traces`
  - `c502ec0 Accept media transcription governor authority`
- The local delta over `origin/codex/turnintent-voice-policy-20260531` is limited to:
  - `src/voice_comms_chip/runtime_state.py`
  - `src/voice_comms_chip/spark_hook.py`
  - `tests/test_runtime_state.py`
  - `tests/test_spark_hook.py`

R30 voice path:

1. Port or push the local voice trace/governor commits into owner-source release truth.
2. Cut or select a stable release ref containing those commits.
3. Update `registry.json` to that stable ref and commit.
4. Update installed-state registry truth through the normal install/update path, not by hand-editing local state.
5. Rerun `spark os compile --json` and require source hooks to remain duplex, runtime blockers to be explicit, and `critical_duplicate_truth_count=0`. Current runtime truth is `voice_surface_mode=egress`, `voice_surface_blockers=1` because transcription is not ready.

## Builder Trace Lifecycle

The remaining unresolved historical trace family is:

- component: `telegram_runtime`
- event type: `tool_call_ledger_recorded`
- status/severity: `blocked` / `high`
- latest event: `2026-06-02 09:03:25`
- latest lifecycle state: `latest_open_high_severity`
- current 1h high-open count: `0`
- current 24h high-open count: `0`
- reason code: redacted by the trace index

R30 must not hide this family. It is currently carried as an explicit historical publish handoff while current windows remain clean. Removing it still requires source-owned lifecycle closure evidence after confirming the guardrail is still active.

## Proof Captured

- `spark os compile --json`: green at `2026-06-27T19:16:04Z`, with `dirty_repo_count=0`, `gaps=0`, 2 local runtime test artifacts, and 1 Builder historical lifecycle handoff still visible.
- `spark verify --r30 --json`: after `ea4e020`, `r30_builder_trace_lifecycle` is no longer a source-truth blocker when the exact historical family is carried and current windows remain clean.
- `spark verify --r30 --json`: green for R30 docs, OS compile, live status, owner handoff manifest, local runtime artifact handoff manifest, voice runtime truth, Access 5 sandbox evidence, local installers, and publication order; red for the real source/registry/publish blockers.
- `domain-chip-memory` owner-lane proof at `2026-06-27T21:33:59Z`: `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts` passed and reported 5 normalized contracts, 4 official adapters, and 1 shadow adapter.
- `spark-intelligence-builder` owner-lane proof at `2026-06-27T21:33:59Z`: `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py` passed, `208 passed, 26 subtests passed in 54.04s`.
- `spark-voice-comms` remote tag worktree test: `121 passed`.
- `spark-voice-comms` installed local branch test: `80 passed`.
- Voice temporary worktree was removed after test.

## Next Safe Actions

1. Prepare owner-source handoff branches or PRs for Telegram, Spawner, voice, memory, and Builder.
2. For voice, prefer a new stable release ref that contains `8a246af` and `7555a36` or equivalent source-owned commits.
3. Keep registry pins unchanged until owner-source proof exists remotely.
4. Keep installer manifest/scripts on R29 locally until source and registry convergence are green for R30.
5. Re-run the full R30 gate after owner-source movement.
