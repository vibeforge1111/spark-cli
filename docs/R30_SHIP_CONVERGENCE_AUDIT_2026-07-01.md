# R30 Ship Convergence Audit

Date: 2026-07-01
Artifact packet: `/Users/alchemistab/.spark/release-artifacts/r30-ship-2026-07-01T161555Z`
Summary JSON: `/Users/alchemistab/.spark/release-artifacts/r30-ship-2026-07-01T161555Z/r30-ship-audit-summary.json`
Artifact manifest: `/Users/alchemistab/.spark/release-artifacts/r30-ship-2026-07-01T161555Z/artifact-sha256.txt`

## Verdict

R30 is still **no-ship**.

The fresh gate packet proves that local installer integrity, provenance, Spark Live, and OS compile are healthy, but the public R30 installer/runtime release is still blocked by source truth, registry pins, release-lane dirt/off-pin heads, voice registry drift, builder trace lifecycle health, and missing hosted installer proof.

Do not advance installer pins, registry pins, hosted scripts, tags, broad activation, or publication from this state.

## Fresh Gate Results

| Gate | Exit | Result |
| --- | ---: | --- |
| `spark verify --r30 --json` | 1 | Fail |
| `spark verify --registry-pins --json` | 1 | Fail |
| `spark verify --installers --json` | 0 | Pass |
| `spark verify --provenance --json` | 0 | Pass |
| `spark live status --json` | 0 | Pass |
| `spark os compile --json` | 0 | Pass |

R30 release id in the verifier: `spark-cli-public-installer-2026-06-27-r30`

Current installer pins still point at `spark-cli-public-installer-2026-06-26-r29`.

## Primary Blockers

- `source_truth_ready = false`
- `installer_pins_are_r30 = false`
- `registry_pins.ok = false`
- `hosted = false`
- `publish_handoff_blockers.ok = false`
- `owner_handoff_manifest.ok = false`
- `local_runtime_artifacts_handoff.ok = false`
- `owner_handoff_patch_apply.ok = false`
- `voice_registry_decision.ok = false`
- `builder_trace_lifecycle.ok = false`

## Release-Lane Direct Blockers

| Module | Current state | Required next action |
| --- | --- | --- |
| `domain-chip-memory` | Clean, but local head `1fd272e519b562afc118ca46ff7da175d735dc44` differs from registry `f7f16a6ea8eee47566140fab5e1cd8142a8ff20a`. | Review/push the vNext memory write authority proof against the current owner release base or replace it with equivalent owner-source proof before registry movement. |
| `spark-intelligence-builder` | Dirty, ahead 44, local head `ca21e183c6c04a658260b218e22fad7b67e02cc7` differs from registry `e7f80fbf03bda196fe7b40a49b8ce5a69ff21131`. | Curate dirty work, close or carry builder trace lifecycle evidence, then rerun Builder proof commands before registry movement. |
| `spark-telegram-bot` | Dirty, local head `e86b84afcd43afd141f858698dca0af1b1a172ee` differs from registry `e5a1bd0409865ddb3024c15ed35ccd0038e31776`. | Curate dirty work and port/push the Telegram reliability stack including the R30 loop-status route fix before registry movement. |
| `spark-voice-comms` | Clean, but local head `c502ec096cefb48839e3279d3392343231884415`, installed metadata `0d6e366fd04d68a00c4d6afb515f3ddee49a2ae3`, and registry `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee` disagree. | Create or select a stable voice owner release ref from the current public owner base, port local trace/governor commits or equivalent owner-source proof, then update registry and installed metadata. |
| `spawner-ui` | Clean, but local head `946a152061ccd16191d7136a2e6d49fa5b5b5457` differs from registry `19b7d0bff14471f2df7d6f0790d72146e9825d95`. | Port or push the Spawner R30 Loop Engineering proof stack, then rerun Spawner checks before registry movement. |

## Supporting Hygiene

| Module | Current state | Required next action |
| --- | --- | --- |
| `spark-cli` | Dirty tracked files: `docs/r30/patches/r30-telegram-control-reliability-stack.patch`, `src/spark_cli/cli.py`, `tests/test_cli.py`. | Curate or commit the verifier/patch changes before final R30 publication. |
| `domain-chip-spark-qa-evidence-lane` | Detached HEAD with dirty tracked files and six untracked source files. | Curate the evidence-lane worktree before claiming Spark-wide source truth. |

Post-audit update:

- Commit `4c9ad8210f119357eec7d8b3c4b0e415997ad6ec` isolated named Telegram profile runtime tokens so a named profile cannot inherit the default bot token.
- Focused proof passed: `PYTHONPATH=src python3 -m pytest -q tests/test_cli.py -k 'named_telegram_profile_runtime_env'` returned `2 passed`.
- Post-fix R30 verifier output is captured in `spark-verify-r30-after-cli-token-fix.json`.
- R30 remains no-ship. `spark-cli` still has one dirty tracked file: `docs/r30/patches/r30-telegram-control-reliability-stack.patch`.

## Registry Pin Drift

`spark verify --registry-pins --json` has one failing check:

- `spark-voice-comms`
  - pinned commit: `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee`
  - remote ref: `refs/heads/main`
  - remote head: `c74490d68ece65ffad21dc5b88f44602e1afa703`
  - status: `pin_drift`

Do not update the voice registry pin until the voice owner-source decision is resolved.

## Handoff / Runtime Blockers

- Owner handoff manifest has supporting hygiene, commit metadata, and owner handoff patch mismatches.
- Local runtime artifact handoff has local runtime owner and artifact metadata mismatches.
- Telegram owner handoff patch apply proof has `expected_tree_mismatch`.
- Publish handoff blockers remain in three families: `repo_release_blocks`, `local_runtime_test_artifacts`, and `builder_trace_health`.
- Builder trace lifecycle has one current unresolved high-severity event and remains a publish blocker.

## Installer State

Local installer integrity is green for the current R29 pins:

- `install.sh` hash matches the committed installer manifest.
- `install.ps1` hash matches the committed installer manifest.
- release metadata is internally consistent.

This is not R30 readiness. The installer must stay R29 until source truth and registry truth converge.

Hosted installer proof is absent.

## Safe Convergence Order

1. Curate dirty worktrees without reverting unrelated user work.
2. For each direct blocker, decide whether the current local head is the intended R30 source truth or whether an owner-source equivalent should replace it.
3. Push or otherwise prove stable owner-source refs for direct blockers.
4. Resolve `spark-voice-comms` owner-source and registry decision before touching voice registry pins.
5. Close or explicitly carry the builder trace lifecycle blocker with owner evidence.
6. Refresh owner handoff and local runtime artifact handoff manifests against the settled source heads.
7. Update registry pins only after remote source refs are stable and proof-backed.
8. Update R30 installer pins, manifests, and checksums only after registry truth is green.
9. Produce hosted installer proof.
10. Rerun the full R30 gate packet plus Spawner/Telegram Loop Engineering smoke regressions.
11. Send the final packet to independent release jury before any public ship call.

## Owner-Proof Commands Captured

These commands reduce uncertainty about local behavior, but they do not make R30 shippable until source heads, dirty worktrees, registry pins, handoff manifests, and installer pins converge.

| Module | Command | Exit | Result artifact |
| --- | --- | ---: | --- |
| `domain-chip-memory` | `PYTHONPATH=src python3 -m domain_chip_memory.cli benchmark-contracts` | 0 | `domain-chip-memory-benchmark-contracts.log` |
| `spark-voice-comms` | `PYTHONPATH=src python3 -m pytest -q` | 0 | `spark-voice-comms-pytest.log` (`132 passed`) |
| `spark-intelligence-builder` | `PYTHONPATH=src python3 -m pytest -q tests/test_bridge_authority.py tests/test_memory_orchestrator.py tests/test_gateway_ask_telegram.py tests/test_user_instructions_authority.py` | 0 | `spark-intelligence-builder-focused-pytest.log` (`208 passed`, `26` subtests passed) |
| `domain-chip-spark-qa-evidence-lane` | `PYTHONPATH=src python3 -m pytest -q` | 0 | `domain-chip-spark-qa-evidence-lane-pytest.log` (`206 passed`) |

## Current Recommendation

Continue convergence work. Do not ship R30 yet.
