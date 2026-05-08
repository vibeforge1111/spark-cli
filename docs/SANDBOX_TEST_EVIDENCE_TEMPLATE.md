# Sandbox Test Evidence Template

Use this with [SANDBOX_TEST_RUNBOOK_2026-05-09.md](./SANDBOX_TEST_RUNBOOK_2026-05-09.md).

Do not paste secrets. Replace sensitive values with `<redacted>`,
`<spark-home>`, `<local-path>`, `<ssh-key-path>`, or `<private-url>` as needed.

## Test Session

```text
Date:
Start time:
End time:
Operator:
Machine:
OS:
Shell:
Spark CLI branch:
Spark CLI commit:
Paired repo commits:
Evidence reviewer:
```

## Safety Confirmation

```text
Private keys pasted? no
Provider keys pasted? no
Bot tokens pasted? no
Railway/Modal/cloud tokens pasted? no
Raw .env pasted? no
Raw support bundle uploaded? no
Destructive commands run? no
Unexpected public access found? yes/no
```

Notes:

```text

```

## Phase 0: Workspace Snapshot

```text
Branch:
Commit:
Git status:
Recent commits:
Pass/warn/block:
Notes:
```

## Phase 1: Local Release Gate

| Check | Result | Notes |
|---|---|---|
| `python -m pytest` |  |  |
| `verify --installers --json` |  |  |
| `verify --installers --hosted-installers --json` |  |  |
| `verify --registry-pins --json` |  |  |
| `verify --provenance --json` |  |  |
| `verify --sandboxes --json` |  |  |
| `git diff --check` |  |  |

Failure detail, if any:

```text

```

## Phase 2: Shareable Diagnostic Leak Scan

| Output | Result | Leak Pattern If Any | Notes |
|---|---|---|---|
| `status --json` |  |  |  |
| `support bundle --json` |  |  |  |
| `security audit --json` |  |  |  |
| `verify --hosted --json` |  |  |  |
| `live verify --json` |  |  |  |

## Phase 3: Public Endpoint Smoke

| URL | Expected | Actual | Result |
|---|---|---|---|
| `https://agent.sparkswarm.ai/docs` | `200` |  |  |
| `https://agent.sparkswarm.ai/install.sh` | `200` |  |  |
| `https://agent.sparkswarm.ai/install.ps1` | `200` |  |  |
| `https://agent.sparkswarm.ai/install/checksums.txt` | `200` |  |  |
| `https://agent.sparkswarm.ai/install/release-manifest.json` | `200` |  |  |
| `https://agent.sparkswarm.ai/install/commands.json` | `200` |  |  |
| Spark Live root | `401` or intended auth behavior |  |  |
| Spark Live `/kanban` | `401` or intended auth behavior |  |  |
| Spark Live `/api/providers` | `401` or intended auth behavior |  |  |

## Phase 4: SSH Sandbox Real-Time Test

Target metadata:

```text
Target name:
Host recorded? yes/no
User:
Port:
Identity file path redacted as:
Remote account non-root? yes/no
Host key trust method:
```

| Check | Result | Notes |
|---|---|---|
| `ssh add` |  |  |
| `ssh list` |  |  |
| `ssh doctor` |  |  |
| `ssh trust` |  |  |
| `ssh doctor --remote-probe` |  |  |
| `ssh smoke` |  |  |
| `verify --sandboxes` after SSH |  |  |
| negative missing target |  |  |
| negative invalid target name |  |  |

SSH safety notes:

```text
Private key contents absent from output:
Key path redacted in shareable output:
Audit reference safe:
Temp files cleaned:
```

## Phase 5: Modal Sandbox Real-Time Test

Modal state:

```text
Modal SDK present:
Modal CLI present:
Modal auth present:
Modal account/profile/environment, if safe:
Cloud cost accepted by operator:
```

| Check | Result | Notes |
|---|---|---|
| `modal doctor` no-auth or pre-auth |  |  |
| `verify --sandboxes` with no auth |  |  |
| `modal doctor` with auth |  |  |
| `modal smoke` with auth |  |  |
| `verify --sandboxes` after Modal |  |  |

Modal safety notes:

```text
No Spark secrets sent:
No project folder mounted:
No Modal token printed:
Network policy as expected:
Timeout/cost bounded:
```

## Phase 6: Railway/VPS Operator-Side Smoke

Environment:

```text
Public URL:
Spark Live service:
Telegram bot service:
Spark Live worktree:
Telegram bot worktree:
Railway project/environment:
```

Public protection:

| Route | Expected | Actual | Result |
|---|---|---|---|
| root | `401` or intended auth behavior |  |  |
| `/kanban` | `401` or intended auth behavior |  |  |
| `/api/providers` | `401` or intended auth behavior |  |  |

Production smoke script:

| Check | Result | Notes |
|---|---|---|
| public health |  |  |
| `spark live status` |  |  |
| spawner registry pin |  |  |
| bot runtime health |  |  |
| bot to Spawner API |  |  |

Railway safety notes:

```text
No raw secrets in logs:
Protected pages not public:
Provider timeout separate from relay health:
```

## Phase 7: Telegram Live Mission Smoke

Telegram context:

```text
Bot/profile:
Admin user allowed:
Mission provider:
Chat provider:
```

`/diagnose` summary:

```text

```

`/run` smoke:

```text
Mission id:
Pipeline id:
Canvas URL:
Mission board URL:
Plan steps:
Completed tasks:
Failed tasks:
Generated files:
Expected text found:
Unexpected dependency/package files:
```

## Phase 8: Post-Test Support Bundle

| Check | Result | Notes |
|---|---|---|
| `support bundle --json` redacted |  |  |
| `security audit --json` redacted |  |  |
| local archive created, if needed |  |  |
| archive reviewed before sharing |  |  |

## Final Classification

Choose one:

```text
[ ] Ready to bundle
[ ] Ready except optional sandbox skipped
[ ] Not ready
```

Reason:

```text

```

Remaining blockers:

```text

```

Follow-up commits needed:

```text

```

Push decision:

```text
Push now? no/yes
Why:
Approver:
Date:
```
