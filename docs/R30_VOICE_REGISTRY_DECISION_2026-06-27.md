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
- installed local voice head: `7555a363d7638537b1a9ec1ee377e460d2343323`
- installed metadata still records: `0d6e366fd04d68a00c4d6afb515f3ddee49a2ae3`
- structured handoff manifest: [R30 voice owner handoff manifest](./R30_VOICE_OWNER_HANDOFF_MANIFEST_2026-06-27.json)

Local voice proof is test-clean, but not yet public release truth:

- public tag worktree at `c74490d68ece`: `PYTHONPATH=src python3 -m pytest -q` passed with `121 passed`
- local installed branch at `7555a363d763`: `PYTHONPATH=src python3 -m pytest -q` passed with `80 passed`

The current local voice proof depends on two commits beyond the owner branch:

- `8a246af Join voice runtime state traces`
- `7555a36 Accept media transcription governor authority`

The R30 gate checks the structured handoff manifest so these exact commits,
proof commands, and the rejection of the existing public tag as the final R30
voice claim cannot drift out of the release packet unnoticed.

## Required R30 Path

1. Port or push the two voice trace/governor commits, or equivalent
   source-owned commits, into the voice owner release lane.
2. Select or create a stable release ref that contains those commits.
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
