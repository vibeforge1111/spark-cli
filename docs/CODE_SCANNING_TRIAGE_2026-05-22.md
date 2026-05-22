# Code Scanning Triage - 2026-05-22

This records the default-branch code scanning cleanup after the Spark jury gate
was enabled. The goal is to keep CodeQL as the source-code security scanner while
using OpenSSF Scorecard as a required supply-chain CI check, not as a noisy
second code-scanning feed.

## Decisions

- Keep `codeql-python` required on `master`.
- Keep `scorecard` required on `master`.
- Stop uploading Scorecard SARIF to code scanning; reviewers should use the
  Scorecard workflow result for supply-chain posture.
- Move CodeQL `security-events: write` to the CodeQL job only.
- Record any alert dismissal with the exact GitHub alert number, reason, and
  reviewer rationale.

## Reviewed Alerts

| Alerts | Tool | Rule | Decision |
| --- | --- | --- | --- |
| #1-#25, #51-#52 | CodeQL | `py/clear-text-logging-sensitive-data` | False positive after source review. The locations print secret labels, masked values, setup guidance, or an explicit local `spark secrets get --reveal` value. They do not print stored secret values by default. |
| #26 | CodeQL | `py/clear-text-storage-sensitive-data` | False positive after source review. The secret file backend stores DPAPI-protected values on Windows and is disabled on non-Windows unless explicitly opted into for disposable tests. |
| #27 | CodeQL | `py/clear-text-storage-sensitive-data` | Used in tests. The fixture writes manifest secret IDs, not live secret values. |
| #31 | Scorecard | `TokenPermissionsID` | Fixed in workflow YAML by moving write permission to the CodeQL job. |
| #32-#50 | Scorecard | Various | Treat as Scorecard workflow findings, not code-scanning alerts. Some are accepted tradeoffs for this competition phase, such as replacing GitHub PR review with `spark-jury-approval`. |

## Follow-Up Rules

- New CodeQL alerts must be fixed or triaged before merge approval.
- New Scorecard regressions must be read from the workflow result; they should
  not automatically create code-scanning alerts.
- Dismissing a CodeQL alert is allowed only when the source path is inspected and
  the dismissal comment states why it is false positive, used in tests, or
  intentionally accepted.
- `spark-jury-approval` remains the replacement for separate human approval in
  this competition system.
