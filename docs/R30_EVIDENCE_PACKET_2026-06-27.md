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
| `spark os compile --json` | PASS | `ok=true`, `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`, `critical_duplicate_truth_count=0`, `voice_surface_mode=duplex`, `voice_surface_blockers=0`. |
| `spark live status --json` | PASS | `ok=true`; primary Telegram and QA Telegram profiles running; Spawner UI healthy; voice importable; no repair hints. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json` | FAIL | Only failing module is `spark-voice-comms`: registry pin `21a9467e9bd4...` diverges from remote `refs/heads/main` at `c74490d68ece...`. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json` | PASS | `ok=true`; commit pins and attestation metadata present; signed commit enforcement remains report-only. |
| `PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json` | PASS | Local installer manifest/scripts are internally consistent for R28. This does not claim R30 readiness. |
| Telegram `npm run control:proof:reliability` | PASS | Fresh-strict audit clean for actionable/latest gaps; live trace clean; render firewall, capsules, evals, legacy prompt surface, capability evidence, and surface eval all clean. |
| Telegram `npm run build` | PASS | TypeScript compile passed. |
| Telegram `npm run check:line-count` | PASS | `R-21 LINE-COUNT GATE: PASS`; 13 baselined god-files, 0 growing, 0 new over cap. |

## Spark OS Compile Details

Generated at `2026-06-27T10:00:59Z`.

Important fields:

- `ok=true`
- `gaps=0`
- `dirty_repo_count=0`
- `blocked_release_count=0`
- `duplicate_truth_count=2`
- `critical_duplicate_truth_count=0`
- `voice_surface_mode=duplex`
- `voice_surface_blockers=0`

Publish handoff families:

- `local_runtime_test_artifacts`: `spark-telegram-bot`, `spawner-ui`
- `builder_trace_health`: `historical_open_high_severity_events`

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
