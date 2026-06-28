# Spark R30 Voice Registry Decision

Date: 2026-06-27
Status: blocked before registry or installer publication

## Decision

Do not move the R30 `spark-voice-comms` registry pin to the existing public
`spark-ship-2026-06-26` tag as the final R30 voice claim.

R30 may only claim the current Spark OS voice proof after the voice
trace/governor commits are present in owner-source release truth, installed
runtime metadata, and registry pins.

## Evidence

Current facts recorded by the R30 gate:

- registry pin: `21a9467e9bd4eebd54b06a72a4c21afcfcd316ee`
- remote `main` and public tag `spark-ship-2026-06-26`: `c74490d68ece65ffad21dc5b88f44602e1afa703`
- prepared local owner-lane voice head: `c502ec096cefb48839e3279d3392343231884415`
- original local voice proof branch head: `7555a363d7638537b1a9ec1ee377e460d2343323`
- installed metadata still records: `0d6e366fd04d68a00c4d6afb515f3ddee49a2ae3`
- fresh remote audit at `2026-06-27T23:33:53Z`: no remote `refs/heads/release/r30-voice-trace-governor` branch exists; `refs/heads/main` and `refs/tags/spark-ship-2026-06-26` still point at `c74490d68ece65ffad21dc5b88f44602e1afa703`, and `refs/heads/codex/turnintent-voice-policy-20260531` still points at `12bddc9bd0bdd719df6ae7d4701779e7b7adfdd4`
- structured handoff manifest: [R30 voice owner handoff manifest](./R30_VOICE_OWNER_HANDOFF_MANIFEST_2026-06-27.json)

Local voice proof is test-clean, but not yet public release truth:

- public tag worktree at `c74490d68ece`: `PYTHONPATH=src python3 -m pytest -q` passed with `121 passed`
- original local proof branch at `7555a363d763`: `PYTHONPATH=src python3 -m pytest -q` passed with `80 passed`
- local prepared release lane `release/r30-voice-trace-governor` at `c502ec096cefb48839e3279d3392343231884415`: `PYTHONPATH=src python3 -m pytest -q` passed with `132 passed`
- fresh recheck at `2026-06-27T21:54:18Z`: local prepared release lane `release/r30-voice-trace-governor` still passes `PYTHONPATH=src python3 -m pytest -q` with `132 passed`
- fresh recheck at `2026-06-27T22:58:58Z`: local prepared release lane `release/r30-voice-trace-governor` still passes `PYTHONPATH=src python3 -m pytest -q` with `132 passed`
- fresh recheck at `2026-06-27T23:38:48Z`: local prepared release lane `release/r30-voice-trace-governor` still passes `PYTHONPATH=src python3 -m pytest -q` with `132 passed`
- fresh recheck at `2026-06-28T00:54:49Z`: local prepared release lane `release/r30-voice-trace-governor` still passes `PYTHONPATH=src python3 -m pytest -q` with `132 passed`

The current local voice proof depends on two commits beyond the owner branch:

- `8a246af1eb0732aec432d88e4e4c2b6411023b7c` (`8a246af Join voice runtime state traces`)
- `7555a363d7638537b1a9ec1ee377e460d2343323` (`7555a36 Accept media transcription governor authority`)

Prepared local owner-lane port, not yet pushed/tagged or registry truth:

- base: `c74490d68ece65ffad21dc5b88f44602e1afa703`
- branch: `release/r30-voice-trace-governor`
- port commit: `4eef348bae135ca3c0d85d4921bf3d4bc28f5e4f` (`Join voice runtime state traces`)
- port commit: `c502ec096cefb48839e3279d3392343231884415` (`Accept media transcription governor authority`)
- changed files: `src/voice_comms_chip/runtime_state.py`, `src/voice_comms_chip/spark_hook.py`, `tests/test_runtime_state.py`, and `tests/test_spark_hook.py`
- diffstat over public owner base `c74490d68ece65ffad21dc5b88f44602e1afa703`: 4 files changed, 731 insertions, 8 deletions
- proof: `PYTHONPATH=src python3 -m pytest -q` -> `132 passed`
- fresh proof: `2026-06-27T21:54:18Z`, `132 passed`
- fresh proof: `2026-06-27T22:58:58Z`, `132 passed`
- fresh proof: `2026-06-27T23:38:48Z`, `132 passed`
- fresh proof: `2026-06-28T00:54:49Z`, `132 passed`
- owner handoff patch: `docs/r30/patches/r30-voice-trace-governor.patch`
  with SHA256 `f4fc2e654b227c4ec53aef8dc013aaf409eab29196c54bd531e522a872c15dff`
  applies to the public base and produces tree
  `e3e1f881497011917fd9baa4f56db811ebccff7e`; this is an apply/review
  artifact, not publication authority.
- current remote audit: no remote `release/r30-voice-trace-governor` branch exists; `main` and `spark-ship-2026-06-26` remain at `c74490d68ece65ffad21dc5b88f44602e1afa703`

This prepared lane reduces the owner-source handoff gap, but it does not clear
the R30 voice registry decision until the release ref is source-owned remotely,
installed metadata is updated through the normal path, and registry pins
converge.

The R30 gate checks the structured handoff manifest so these exact commits,
full commit hashes, changed-file inventory, diffstat, owner branch/public tag
identities, installed metadata drift, proof commands, required post-update voice
runtime truth, and the rejection of the existing public tag as the final R30
voice claim cannot drift out of the release packet unnoticed.

## Required R30 Path

1. Create or select a stable voice owner release ref from the current public
   owner base, `refs/heads/main` at `c74490d68ece65ffad21dc5b88f44602e1afa703`.
2. Port or push the two voice trace/governor commits, or equivalent
   source-owned commits, into that voice owner release lane.
3. Update `registry.json` to that stable ref and commit only after source-owner
   proof exists.
4. Update installed runtime metadata through the normal install/update path.
5. Rerun:

```bash
PYTHONPATH=src python3 -m pytest -q
spark os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```

Concrete owner-lane recipe, before any push/tag:

```bash
cd ~/.spark/modules/spark-voice-comms/source
git fetch origin --tags
git switch -c release/r30-voice-trace-governor c74490d68ece65ffad21dc5b88f44602e1afa703
git cherry-pick 8a246af1eb0732aec432d88e4e4c2b6411023b7c
git cherry-pick 7555a363d7638537b1a9ec1ee377e460d2343323
PYTHONPATH=src python3 -m pytest -q
```

If those commits do not cherry-pick cleanly onto current owner truth, make an
equivalent source-owned port that preserves the same runtime-state trace join
and media-transcription governor authority proof, then record the replacement
commit hashes before touching registry or installer truth.

Required result before installer movement:

- `spark-voice-comms` has no registry pin drift
- installed metadata matches registry truth
- `voice_surface_mode=egress`
- `voice_surface_blockers=1`
- `voice_surface_blocker`: voice transcription is not ready
- `requires_confirmation_for_actions=true`
- voice remains action-confirmation-bound
- R30 installer pins still remain unchanged until the full source/registry lane
  is green
