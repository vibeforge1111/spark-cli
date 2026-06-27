# Spark R30 Source Owner Audit

Date: 2026-06-27
Status: current-state audit for R30 prep; not a publication record

## Purpose

This audit records the owner-source and registry state R30 must converge before installer pins or hosted metadata can move. It keeps local proof separate from public release truth.

Concrete port/push ranges are recorded in [R30 owner handoff packet](./R30_OWNER_HANDOFF_PACKET_2026-06-27.md).

## Summary

R30 is not ready for installer pin changes yet.

The current Spark stack is clean enough to keep preparing R30, but several R30-relevant changes are still local or ahead of owner-source refs:

- `spark-telegram-bot`: local R30 proof/docs head has no owner remote branch yet.
- `spawner-ui`: local branch is ahead of the owner release branch.
- `spark-voice-comms`: the public `spark-ship-2026-06-26` tag is test-clean, but it does not include the local voice trace/governor commits that make the current Spark OS voice proof truthful.
- `domain-chip-memory` and `spark-intelligence-builder`: local heads are ahead of owner branches.
- Builder trace health still has one historical lifecycle family that must remain visible until source-owned closure exists.
- `spark-cli`: local R30 prep now includes the executable R30 gate, live-status gate, Access 5 Codex sandbox gate, voice runtime truth gate, local runtime artifact handoff gate, and the R29 hosted/local installer baseline alignment. It has not been published or tagged as R30.

## Current Heads And Pins

| Area | Local installed/source head | Owner remote / release truth | Registry or installer truth | R30 action |
| --- | --- | --- | --- | --- |
| `spark-cli` | `34f0c346a7b1` on `harness-discipline-ruleset` | remote R29 tag `7751ef43581c`; remote `master` `a6738be7a97a` | local installer manifest/scripts now match R29 | Keep R30 docs, live-status gate, Access 5 sandbox gate, voice runtime truth gate, local runtime artifact handoff gate, and voice discovery fix local until source release/tag is authorized. |
| `spark-telegram-bot` | `fa4c8884bb83` on `harness-discipline-line-count-gate` | no matching owner branch found; remote `main` `67ad9e6ed297`; tag `spark-ship-2026-06-22` `e5a1bd040986` | registry pin `e5a1bd040986`; classified `local_runtime_test_artifact` | Push/port `fa4c8884bb83` or an equivalent owner release commit before changing registry. |
| `spawner-ui` | `7110dce4030a` on `release/stability-2026-06-02-spawner-authority` | owner branch `fdb8fded4744`; remote `main` `451d009aad84`; tag `spark-ship-2026-06-22` `19b7d0bff144` | registry pin `19b7d0bff144`; classified `local_runtime_test_artifact` | Push/port the local merge/fix stack, including direct-client and PRD-lane Level 5 Codex sandbox fixes, before changing registry. |
| `spark-voice-comms` | `7555a363d763` on `codex/turnintent-voice-policy-20260531`; ahead 2 of owner branch | owner branch `12bddc9bd0bd`; remote `main` and tag `spark-ship-2026-06-26` `c74490d68ece` | registry pin `21a9467e9bd4`; installed state still records `0d6e366fd04d` | Do not pin R30 voice to `c74490d` if R30 claims current voice trace proof. Port/tag local trace/governor commits first, then update registry and installed state truth together. |
| `domain-chip-memory` | `1fd272e519b5`; ahead 1 | owner branch `3116ccaa3977`; remote `main` `72a660a69c0c`; tag `spark-ship-2026-06-22` `f7f16a6ea8ee` | registry pin `f7f16a6ea8ee` | Owner can review/push the vNext memory authority proof before R30 registry claims. |
| `spark-intelligence-builder` | `f21522accf66`; ahead 43 | owner branch `c94eac853fed`; remote `main` `9d7bdefaa9a0`; tag `spark-ship-2026-06-22` `e7f80fbf03bd` | registry pin `e7f80fbf03bd` | Owner can review/push or port the merge/fix stack; Builder historical trace lifecycle remains a separate handoff. |

## Voice Registry Decision

Do not update `spark-voice-comms` registry truth to `spark-ship-2026-06-26` as the final R30 voice claim.

Evidence:

- Remote tag `spark-ship-2026-06-26` points at `c74490d68ece65ffad21dc5b88f44602e1afa703`.
- Temporary detached worktree at `c74490d68ece` passed `PYTHONPATH=src python3 -m pytest -q`: `121 passed`.
- Installed local voice branch at `7555a363d763` passed `PYTHONPATH=src python3 -m pytest -q`: `80 passed`.
- The local branch adds the current Spark OS voice proof pieces over the owner branch:
  - `8a246af Join voice runtime state traces`
  - `7555a36 Accept media transcription governor authority`
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

R30 must not hide this family. Either add source-owned lifecycle closure evidence after confirming the guardrail is still active, or keep this as an explicit historical publish handoff.

## Proof Captured

- `spark os compile --json`: green at `2026-06-27T14:43:44Z`, with `dirty_repo_count=0`, `gaps=0`, 2 local runtime test artifacts, and 1 Builder historical lifecycle handoff still visible.
- `spark verify --r30 --json`: green for R30 docs, OS compile, live status, owner handoff manifest, local runtime artifact handoff manifest, voice runtime truth, Access 5 sandbox evidence, local installers, and publication order; red for the real source/registry/publish blockers.
- `spark-voice-comms` remote tag worktree test: `121 passed`.
- `spark-voice-comms` installed local branch test: `80 passed`.
- Voice temporary worktree was removed after test.

## Next Safe Actions

1. Prepare owner-source handoff branches or PRs for Telegram, Spawner, voice, memory, and Builder.
2. For voice, prefer a new stable release ref that contains `8a246af` and `7555a36` or equivalent source-owned commits.
3. Keep registry pins unchanged until owner-source proof exists remotely.
4. Keep installer manifest/scripts on R29 locally until source and registry convergence are green for R30.
5. Re-run the full R30 gate after owner-source movement.
