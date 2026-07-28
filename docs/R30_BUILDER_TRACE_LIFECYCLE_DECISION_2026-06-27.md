# Spark R30 Builder Trace Lifecycle Decision

Date: 2026-06-27
Status: explicit historical handoff, not closed

## Decision

Do not hide or silently clear the Builder historical high-severity trace family
for R30.

Current windows are clean, but the historical lifecycle family remains visible
until Builder owner-source closure evidence exists. R30 may proceed with this
family explicitly carried as historical release debt only while the current
unresolved high-severity count stays `0` and the release packet preserves the
exact family identity.

## Evidence

Current `spark verify --r30 --json` publish-handoff summary reports:

- family: `builder_trace_health`
- flag: `historical_open_high_severity_events`
- component: `telegram_runtime`
- event type: `tool_call_ledger_recorded`
- status/severity: `blocked` / `high`
- unresolved high-severity open count: `1`
- current unresolved high-severity open count: `0`
- unresolved high-severity source group count: `1`
- latest unresolved high-severity event: `2026-06-02 09:03:25`

Interpretation:

- This is not a fresh current-window high-severity failure.
- It is still not closed release truth.
- R30 must not use a green-looking release summary that drops the historical
  lifecycle state.

## Required Closure Path

1. Builder owner inspects the historical trace family in the Builder-owned
   evidence lane.
2. If the guardrail is still active and the lifecycle can be closed, record
   source-owned closure evidence in Builder.
3. Recompile Spark OS from `spark-cli`:

```bash
spark os compile --json
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
```

Required result before removing this handoff:

- `builder_trace_health` no longer appears in `publish_handoffs.families`, or
  an owner-approved release note explicitly carries it as historical
  non-blocking debt.
- `current_unresolved_high_severity_open_count=0`
- `critical_duplicate_truth_count=0`
- R30 source/registry truth remains green before installer pins move.

## R30 Carry Decision

For R30, this is carried as explicit historical handoff, not hidden release
truth and not owner-approved closure. The gate remains red if current unresolved
high-severity evidence returns, if the exact family identity disappears from the
release packet, or if anyone tries to remove this document without Builder
owner-approved closure evidence from Builder owner source.
