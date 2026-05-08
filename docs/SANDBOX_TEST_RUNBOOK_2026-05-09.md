# Sandbox Test Runbook For 2026-05-09

Status: operator test plan for real-time SSH, Modal, Railway/VPS, and Telegram
Spark Live sandbox validation.

Use this on Saturday, May 9, 2026 before pushing the bundled Spark release.
This runbook is intentionally detailed so a Spark agent or human operator can
run the same checks, record the same evidence, and avoid accidental secret,
cost, or production-risk drift.

## Test Goals

Prove these things in order:

1. Spark CLI unit and release gates pass locally.
2. Shareable diagnostics do not leak local paths, key paths, tokens, or raw
   secret values.
3. SSH sandbox doctor/probe/smoke works against a real user-owned host.
4. Modal doctor/smoke behaves correctly with no auth and with auth, if
   available.
5. Railway/VPS Spark Live stays protected from public unauthenticated access.
6. Authenticated Railway/VPS smoke works from the production-linked worktrees.
7. Telegram `/diagnose` and a tiny `/run` mission prove the live relay path.
8. Any failure is classified as code, config, credential, provider, network,
   auth, or expected environment limitation.

Do not push during this runbook. Record evidence first.

## Required Inputs

Fill these before starting:

```text
Date: 2026-05-09
Operator:
Spark CLI branch:
Spark CLI commit:
Paired repo branches/commits:
Railway public URL:
Railway Spark Live worktree:
Railway Telegram bot worktree:
SSH target name:
SSH host:
SSH user:
SSH identity file path:
Modal auth available: yes/no
Telegram bot profile:
Evidence file:
```

Use [SANDBOX_TEST_EVIDENCE_TEMPLATE.md](./SANDBOX_TEST_EVIDENCE_TEMPLATE.md)
for the evidence record.

## Security Rules

Do not paste or record:

- private key contents
- BotFather tokens
- LLM/provider API keys
- Railway, Modal, cloud, GitHub, npm, or Hugging Face tokens
- `.env` files
- browser profile paths
- raw support bundles before local review
- screenshots that show secrets, tokens, cookies, or private URLs

Do not run:

- `StrictHostKeyChecking=no`
- SSH agent forwarding for Spark sandbox work
- arbitrary SSH shell through Spark
- Modal runs with provider secrets
- remote deploy commands unless this runbook explicitly reaches the Railway
  smoke step
- force push, hard reset, recursive delete, or destructive cleanup

Stop immediately if:

- a token, private key path, raw home path, or private IP appears in shareable
  output;
- a protected Spawner route is public without auth;
- SSH reports a host-key mismatch;
- a Modal run unexpectedly receives project files or Spark secrets;
- Railway logs print raw secret values;
- a test requires broadening permissions just to pass.

If a stop condition occurs, mark the result as `security-fail`, preserve only
redacted evidence, rotate affected secrets if needed, and fix before continuing.

## Phase 0: Workspace Snapshot

Purpose: prove what code and local state were tested.

Commands:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline -8
```

Expected:

- branch is the intended release-prep branch;
- no unexpected tracked changes;
- unrelated `PROJECT.md`, if present, remains untracked and untouched;
- recent commits include sandbox hardening, task tracker, registry pin, and
  sandbox guidance docs.

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | Only expected untracked files are present. |
| Block | Tracked files changed unexpectedly. |
| Block | Branch is not the intended release branch. |

## Phase 1: Local Release Gate

Purpose: prove the repo is healthy before touching remote accounts.

Commands:

```powershell
python -m pytest
python -m spark_cli.cli verify --installers --json
python -m spark_cli.cli verify --installers --hosted-installers --json
python -m spark_cli.cli verify --registry-pins --json
python -m spark_cli.cli verify --provenance --json
python -m spark_cli.cli verify --sandboxes --json
git diff --check
```

Expected:

- `pytest` passes with only known skips;
- installer and hosted installer checks are OK;
- registry pins match remote HEAD for blessed modules;
- provenance reports commit pins and attestation metadata present;
- sandbox verification is OK when no SSH target is configured;
- Modal auth may be an optional warning on machines without Modal auth;
- no whitespace errors.

Current expected baseline from May 8, 2026:

```text
python -m pytest -> 497 passed, 5 skipped
verify --installers --json -> OK
verify --installers --hosted-installers --json -> OK
verify --registry-pins --json -> OK
verify --provenance --json -> OK
verify --sandboxes --json -> OK
git diff --check -> OK
```

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | Every required gate is green; Modal auth warning is optional. |
| Block | Unit tests, installer integrity, registry pins, provenance, or diff check fail. |
| Warn | Modal auth is missing locally but Modal smoke is not part of this machine's run. |

## Phase 2: Shareable Diagnostic Leak Scan

Purpose: prove support/debug outputs are safe to paste after review.

Commands:

```powershell
$commands = @(
  'status --json',
  'support bundle --json',
  'security audit --json',
  'verify --hosted --json',
  'live verify --json'
)
$patterns = @(
  'C:\Users\USER',
  'C:/Users/USER',
  '~\.spark',
  '~/.spark',
  '.ssh',
  'id_rsa',
  'secrets.local.json'
)
foreach ($cmd in $commands) {
  $output = & python -m spark_cli.cli @($cmd -split ' ') 2>&1 | Out-String
  $hits = @()
  foreach ($pattern in $patterns) {
    if ($output.Contains($pattern)) { $hits += $pattern }
  }
  if ($hits.Count) {
    "LEAK $cmd :: $($hits -join ', ')"
  } else {
    "OK $cmd"
  }
}
```

Expected:

- no raw Windows home path;
- no `~/.spark` or `~\.spark` in shareable JSON;
- Spark-owned paths use `<spark-home>`;
- non-Spark local paths use `<local-path>/...`;
- no private key filenames, token values, auth headers, or URL credentials;
- `verify --hosted` and `live verify` may fail locally because hosted provider
  or hosted API keys are not configured, but their output must still be
  redacted.

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | All checked outputs report `OK`. |
| Block | Any raw home path, SSH key path, token, or secret filename appears in shareable output. |
| Warn | Generic docs mention `~/.spark` outside shareable JSON; docs are not the leak target. |

## Phase 3: Public Endpoint Smoke

Purpose: prove the public docs/install surface is reachable and protected Spark
Live routes are not public.

Commands:

```powershell
$urls = @(
  'https://agent.sparkswarm.ai/docs',
  'https://agent.sparkswarm.ai/install.sh',
  'https://agent.sparkswarm.ai/install.ps1',
  'https://agent.sparkswarm.ai/install/checksums.txt',
  'https://agent.sparkswarm.ai/install/release-manifest.json',
  'https://agent.sparkswarm.ai/install/commands.json',
  'https://spark-live-production.up.railway.app/',
  'https://spark-live-production.up.railway.app/kanban',
  'https://spark-live-production.up.railway.app/api/providers'
)
foreach ($url in $urls) {
  $code = & curl.exe -L -s -o NUL -w "%{http_code}" --max-time 20 $url
  "$code $url"
}
```

Expected:

- `agent.sparkswarm.ai` docs and installer metadata return `200`;
- Spark Live protected root/kanban/provider routes return `401` unless a valid
  authenticated session/API key is supplied;
- a public `401` is a good sign for protected Spawner routes.

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | Public docs/install are `200`; protected Spark Live routes are `401`. |
| Block | Installer URLs are unavailable or stale. |
| Block | Protected Spawner routes return public `200` without auth. |

## Phase 4: SSH Sandbox Real-Time Test

Purpose: prove SSH compatibility against a real user-owned host without
shipping arbitrary remote execution.

Preconditions:

- user owns the host;
- SSH key exists locally as a file path;
- no private key contents are pasted into chat or docs;
- remote account is non-root, preferably `spark`;
- host fingerprint can be confirmed if possible;
- remote host is not a production database or irreplaceable machine.

Commands:

```powershell
python -m spark_cli.cli sandbox ssh add odyssey-vps `
  --host <host> `
  --user spark `
  --identity-file <path> `
  --json

python -m spark_cli.cli sandbox ssh list --json
python -m spark_cli.cli sandbox ssh doctor odyssey-vps --json
python -m spark_cli.cli sandbox ssh trust odyssey-vps --json
python -m spark_cli.cli sandbox ssh doctor odyssey-vps --remote-probe --json
python -m spark_cli.cli sandbox ssh smoke odyssey-vps --json
python -m spark_cli.cli verify --sandboxes --json
```

Expected:

- add stores target metadata, not key contents;
- list output does not reveal private key material;
- doctor confirms local SSH client, identity file, strict SSH argv options, and
  non-root user;
- trust pins a host-key fingerprint in Spark-owned known hosts;
- remote probe uses a fixed read-only command;
- smoke runs a bounded hashed temp probe and cleans up;
- audit references are relative/safe, not raw absolute local paths.

Negative checks to run only if safe:

```powershell
python -m spark_cli.cli sandbox ssh doctor missing-target --json
python -m spark_cli.cli sandbox ssh add bad/name --host <host> --user spark --identity-file <path> --json
```

Expected negative results:

- invalid target names fail;
- missing target fails with a clear repair hint;
- no stack trace;
- no secret/path leak.

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | Trust, remote probe, and smoke pass with no leaks. |
| Warn | Doctor passes but remote probe fails due network/firewall/key authorization. |
| Block | Host key mismatch, root-only target, secret/path leak, or arbitrary command path appears. |

Cleanup after test, if the target was temporary:

```powershell
python -m spark_cli.cli sandbox ssh remove odyssey-vps --json
```

Do not remove the target if it is the shared target for tomorrow's continued
testing; instead record that it remains configured.

## Phase 5: Modal Sandbox Real-Time Test

Purpose: prove Modal behaves safely before and after auth is configured.

### 5A: No-Auth Baseline

Run this first on a machine without Modal auth, or after confirming no auth is
available.

```powershell
python -m spark_cli.cli sandbox modal doctor --json
python -m spark_cli.cli verify --sandboxes --json
```

Expected:

- Modal SDK/CLI checks report their true local state;
- missing Modal auth is clear;
- `verify --sandboxes` remains OK because Modal is optional;
- no tokens are printed.

### 5B: Authenticated Smoke

Run only if Modal auth is available and the operator accepts possible small
cloud cost.

```powershell
python -m spark_cli.cli sandbox modal doctor --json
python -m spark_cli.cli sandbox modal smoke --json
python -m spark_cli.cli verify --sandboxes --json
```

Expected:

- doctor sees auth without printing tokens;
- smoke uses no Spark secrets, no Modal Secrets, and no project files by
  default;
- smoke has short timeout and bounded output;
- no artifact persistence or provider-secret passthrough happens.

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | Doctor and no-secret smoke pass with auth. |
| Warn | Missing auth on a machine where Modal testing was optional. |
| Block | Token value printed, project folder mounted unexpectedly, or secret passthrough appears. |

## Phase 6: Railway/VPS Operator-Side Smoke

Purpose: prove split Railway services are reachable and authenticated service
paths work.

Preconditions:

- Railway CLI is installed and logged in;
- worktrees are linked to the intended Railway projects;
- production credentials are available in Railway, not pasted locally;
- `SPARK_UI_API_KEY` and `SPARK_BRIDGE_API_KEY` exist in the hosted
  environment;
- user has accepted that hosted deep checks can spend real LLM credits.

Public protection check:

```powershell
curl.exe -L -s -o NUL -w "%{http_code}" --max-time 20 https://spark-live-production.up.railway.app/
curl.exe -L -s -o NUL -w "%{http_code}" --max-time 20 https://spark-live-production.up.railway.app/kanban
curl.exe -L -s -o NUL -w "%{http_code}" --max-time 20 https://spark-live-production.up.railway.app/api/providers
```

Expected: `401` for protected routes without auth.

Production smoke:

```powershell
.\scripts\railway-production-smoke.ps1 `
  -SparkLiveCwd C:\path\to\spark-cli-prod-worktree `
  -TelegramBotCwd C:\path\to\spark-telegram-bot `
  -PublicUrl https://spark-live-production.up.railway.app
```

Expected:

- public health check passes for the route the script expects;
- `spark live status` inside Railway reports OK;
- installed Spawner registry pin exists;
- Telegram bot `npm run health:runtime` passes;
- bot service can call Spawner health/providers/mission-board with configured
  service auth;
- no raw secrets in logs.

If the script fails:

| Failure | Likely Cause | Next Step |
|---|---|---|
| Public health unauthorized | Route may now require auth | Confirm intended route and update smoke script only if protection is expected. |
| Railway SSH unavailable | Railway CLI/session/project link | Re-login or relink worktree. |
| Spawner auth 401 from bot service | bridge/UI key mismatch | Compare Railway variable names, not values, across services. |
| Mission board unreachable | Spawner down or wrong URL | Check `SPAWNER_UI_URL` and service logs. |
| Provider timeout | Provider/model/API key issue | Treat separately from relay health. |

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | Script passes and public protected routes stay protected. |
| Warn | Provider timeout only, while relay and mission board are healthy. |
| Block | Public protected route open, auth mismatch, Spark Live down, or raw secret in logs. |

## Phase 7: Telegram Live Mission Smoke

Purpose: prove the real user path from Telegram to Spawner to mission execution.

Commands to send in Telegram:

```text
/diagnose
```

Expected:

- bot mission relay reachable;
- Spawner UI reachable;
- current user allowed/admin;
- routing matches intended provider;
- mission board reachable;
- provider ping either succeeds or gives a specific provider timeout/error.

Then send:

```text
/run Build a tiny static HTML page called Spark Production Smoke. It should have one file, index.html, with a dark Mission Control panel, a green "Spark Live OK" status, and the text "Telegram to Spawner relay worked on May 9, 2026". Do not add package files, do not install dependencies, and keep it simple enough to finish fast.
```

Expected:

- Spark acknowledges the build;
- canvas link is produced;
- plan has constrained static steps;
- mission board shows completion;
- generated workspace includes exactly the simple static deliverable;
- no `package.json`, `node_modules`, dependency install, or overbuilt app unless
  the agent explicitly explains why.

Pass/fail:

| Result | Meaning |
|---|---|
| Pass | `/diagnose` healthy enough and static mission completes. |
| Warn | Plain chat provider timeout but mission provider path succeeds. |
| Block | User not allowed, relay down, Spawner unreachable, mission board unreachable, or build fails. |

## Phase 8: Post-Test Support Bundle

Purpose: prove failed and successful sandbox tests can be summarized safely.

Commands:

```powershell
python -m spark_cli.cli support bundle --json
python -m spark_cli.cli security audit --json
```

Expected:

- output uses `<spark-home>` and `<local-path>`;
- no raw home path;
- no key path;
- no token;
- no private IP unless redacted;
- support bundle says local review is required.

Optional local archive after manual review:

```powershell
python -m spark_cli.cli support bundle
```

Do not upload the archive automatically. Review locally first.

## Final Decision

Use this decision table before pushing with the paired Spark repos:

| Decision | Criteria |
|---|---|
| Ready to bundle | Local gates pass, registry/provenance pass, SSH or intentionally skipped, Modal pass or intentionally skipped, Railway smoke pass, Telegram smoke pass. |
| Ready except optional sandbox | Local gates pass; optional SSH or Modal unavailable for environment reasons and recorded as skipped. |
| Not ready | Any secret leak, public protected route open, registry pin drift, failed unit gate, failed installer integrity, or unresolved production auth mismatch. |

Final required note:

```text
Push decision:
Reason:
Remaining blockers:
Evidence file:
Operator:
Date:
```
