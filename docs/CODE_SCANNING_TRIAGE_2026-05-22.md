# Code Scanning Triage - 2026-05-22

This records the default-branch code scanning cleanup after the Spark jury gate
was enabled. The goal is to keep CodeQL as the source-code security scanner while
using OpenSSF Scorecard as a required supply-chain CI check, not as a noisy
second code-scanning feed.

## Decisions

- Keep `codeql-python` required on `master`.
- Keep `scorecard` required on `master`.
- Stop uploading Scorecard SARIF to code scanning; the Spark jury/CI gate should
  use the Scorecard workflow result for supply-chain posture.
- Move CodeQL `security-events: write` to the CodeQL job only.
- Record any alert dismissal with the exact GitHub alert number, reason, and
  system/jury triage rationale.

## Reviewed Alerts

| Alerts | Tool | Rule | Decision |
| --- | --- | --- | --- |
| #1-#25, #51-#52 | CodeQL | `py/clear-text-logging-sensitive-data` | False positive after source review. The locations print secret labels, masked values, setup guidance, or an explicit local `spark secrets get --reveal` value. They do not print stored secret values by default. |
| #26 | CodeQL | `py/clear-text-storage-sensitive-data` | False positive after source review. The secret file backend stores DPAPI-protected values on Windows and is disabled on non-Windows unless explicitly opted into for disposable tests. |
| #27 | CodeQL | `py/clear-text-storage-sensitive-data` | Used in tests. The fixture writes manifest secret IDs, not live secret values. |
| #31 | Scorecard | `TokenPermissionsID` | Fixed in workflow YAML by moving write permission to the CodeQL job. |
| #32, #34 | Scorecard | `PinnedDependenciesID` | Existing Docker Python base images are not digest-pinned. Track through the Scorecard workflow result instead of code scanning. |
| #33 | Scorecard | `PinnedDependenciesID` | Existing Docker Node base image is not digest-pinned. Track through the Scorecard workflow result instead of code scanning. |
| #35-#38, #40-#44 | Scorecard | `PinnedDependenciesID` | Existing Docker/CI pip install commands are not hash-pinned. Track through the Scorecard workflow result instead of code scanning. |
| #39 | Scorecard | `PinnedDependenciesID` | Existing Docker npm global install is not hash-pinned. Track through the Scorecard workflow result instead of code scanning. |
| #45 | Scorecard | `CodeReviewID` | Accepted competition-system tradeoff: GitHub PR review is replaced by required `spark-jury-approval` plus CI gates. |
| #46 | Scorecard | `MaintainedID` | Accepted repository-age signal. The repository was created within 90 days; not a merge blocker by itself. |
| #47 | Scorecard | `SecurityPolicyID` | Addressed by adding a private vulnerability reporting path to `SECURITY.md` and enabling GitHub private vulnerability reporting for the repository. |
| #48 | Scorecard | `CIIBestPracticesID` | Accepted phased hardening item. OpenSSF Best Practices badge work is outside this immediate code-scanning cleanup. |
| #49 | Scorecard | `SASTID` | Existing history signal. CodeQL is now a required `master` and PR gate; old unchecked commits do not block this cleanup. |
| #50 | Scorecard | `FuzzingID` | Accepted phased hardening item. Fuzzing is not yet part of the Spark CLI gate and should be tracked separately. |

## Follow-Up Rules

- New CodeQL alerts must be fixed or triaged before `spark-jury-approval`.
- New Scorecard regressions must be read from the workflow result; they should
  not automatically create code-scanning alerts.
- Dismissing a CodeQL alert is allowed only when the source path is inspected by
  the jury/CI process and the dismissal comment states why it is false positive,
  used in tests, or intentionally accepted.
- `spark-jury-approval` remains the replacement for separate human approval in
  this competition system.
