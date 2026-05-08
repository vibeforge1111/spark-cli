# Remote Sandbox Implementation Plan

Last updated: 2026-05-08

Status: SSH doctor/smoke, Modal doctor/smoke, and shared sandbox verification
are implemented. Deploy and arbitrary run commands remain intentionally out of
scope.

## Goal

Ship secure remote sandbox compatibility without turning Spark into a generic
remote shell.

The first usable outcome is:

```bash
spark sandbox ssh add <name> --host <host> --user <user> --identity-file <path>
spark sandbox ssh doctor <name> --json
spark sandbox ssh doctor <name> --remote-probe --json
spark sandbox ssh smoke <name> --json
spark verify --sandboxes --json
```

Then:

```bash
spark sandbox modal doctor --json
spark sandbox modal smoke --json
```

Deploy and arbitrary run commands come later, only after the policy and audit
layer is proven.

Agent-facing sandbox guidance now lives in
[SAFE_SANDBOX_AGENT_GUIDE.md](./SAFE_SANDBOX_AGENT_GUIDE.md). Future initial
installer options are scoped in
[FUTURE_INSTALLER_SANDBOX_OPTIONS.md](./FUTURE_INSTALLER_SANDBOX_OPTIONS.md);
they are intentionally not shipped yet.

## Current Repo Shape

Implementation should respect the existing structure:

- `src/spark_cli/cli.py` owns argparse and command dispatch. It is already large,
  so new logic should not accumulate there.
- `src/spark_cli/runtime_policy.py` already centralizes safe argv execution for
  local runtime commands.
- `src/spark_cli/security/approval.py` already classifies sensitive command
  actions.
- `src/spark_cli/security/url_policy.py` already owns URL safety checks.
- `tests/test_cli.py` is the main integration/unit test surface.

## Architecture

Add small modules:

```text
src/spark_cli/sandbox/
  __init__.py
  audit.py
  capabilities.py
  output.py
  paths.py
  ssh.py
  modal.py
```

Keep `cli.py` changes limited to:

- parser registration for `spark sandbox ...`
- `cmd_sandbox(args)` dispatcher
- short human/JSON rendering calls

### Shared Contracts

`capabilities.py`:

- `CapabilityManifest`
- `ActionClassification`
- toxic-flow decisions
- human risk badge strings

`audit.py`:

- append-only JSONL under `~/.spark/logs/remote/<backend>/*.jsonl`
- redacted event writer
- public audit references use relative log names, not absolute local paths
- audit log files are made private where the OS supports chmod
- event schema version

`paths.py`:

- Spark-owned remote config paths
- Spark-owned SSH known-hosts path
- safe target-name validation
- safe artifact/output path helpers

`output.py`:

- bounded stdout/stderr capture
- terminal control character stripping for human output
- secret redaction helpers reused by SSH and Modal

## Command Tree

```text
spark sandbox
  ssh
    add <name> --host <host> --user <user> --identity-file <path> [--port 22]
    list [--json]
    trust <name> [--fingerprint <sha256>] [--json]
    doctor <name> [--remote-probe] [--json]
    smoke <name> [--json] [--keep-debug-files]
    remove <name> [--json]
  modal
    doctor [--json]
    smoke [--json]
spark verify --sandboxes [--json]
```

Do not add `ssh run`, `ssh deploy`, `modal run`, or artifact pull in the first
implementation slice.

## Phase 1: Shared Remote Safety Primitives

Status: shipped.

Files:

- `src/spark_cli/sandbox/__init__.py`
- `src/spark_cli/sandbox/capabilities.py`
- `src/spark_cli/sandbox/output.py`
- `src/spark_cli/sandbox/paths.py`
- tests in `tests/test_cli.py` or a new focused test file if the suite becomes
  unwieldy

Build:

- target-name validation: lowercase letters, digits, hyphen, no path separators
- capability manifest dataclass
- action classification dataclass
- toxic-flow blocker
- control-character stripping
- bounded output helper
- redaction helper for env, auth headers, cookies, PEM, provider keys,
  URL credentials, signed URL query params, JWT-shaped blobs,
  GitHub/GitLab/npm/Hugging Face/Slack/cloud tokens, and Telegram tokens

Acceptance tests:

- invalid target names fail
- secret-like values redact in output and audit payloads
- terminal control sequences are stripped from human output
- toxic flows deny `secret_access + network_write`
- capability JSON is stable and readable

Commit after this phase.

## Phase 2: SSH Target Store and Add/List/Remove

Status: shipped.

Files:

- `src/spark_cli/sandbox/ssh.py`
- parser hooks in `src/spark_cli/cli.py`
- tests

Build:

- target records at `~/.spark/config/ssh_targets.json`
- Spark-owned known-hosts at `~/.spark/config/ssh_known_hosts`
- key path stored as a path only, never contents
- identity file existence and permission checks where the OS exposes them
- `ssh-keyscan` fingerprint discovery if available
- guided trust flow for interactive use
- `--json` payloads for automation

Security defaults:

```text
BatchMode=yes
IdentitiesOnly=yes
ForwardAgent=no
RequestTTY=no
StrictHostKeyChecking=yes after add
UserKnownHostsFile=<spark-owned-known-hosts>
ServerAliveInterval=10
ServerAliveCountMax=3
```

Acceptance tests:

- parser accepts expected commands
- target store round trip
- private key contents never written
- invalid host/user/name/key path rejected
- remote workspace paths reject traversal, spaces, shell metacharacters, and
  unsupported `~other` home expansion
- normal operations use `StrictHostKeyChecking=yes`
- guided add is the only path allowed to write known-hosts
- `PROJECT.md` or unrelated files remain untouched

Commit after this phase.

## Phase 3: SSH Doctor

Status: shipped, including guided host-key trust and optional fixed
`--remote-probe` login reachability.

Build `spark sandbox ssh doctor <name>`.

Shipped checks:

- local SSH client available
- target record validates
- identity file exists
- Spark known-hosts entry exists
- connection command is constructed safely as argv
- target user is configured as non-root
- optional `--remote-probe` runs a fixed login reachability command
- no secrets appear in output

Future richer preflight can add remote OS/arch, disk/memory, optional Docker
availability, workspace readiness, and port checks.

Implementation rule:

- No arbitrary remote command input.
- Only fixed read-only probe ids.
- Every subprocess call uses `shell=False`.

Acceptance tests:

- generated ssh argv has the required security options
- host-key missing and host-key mismatch fail closed
- root remote user reports a warning/failure
- command timeout returns a bounded failure
- output redaction works
- JSON payload contains `ok`, `checks`, `target`, `capabilities`, and `audit`

Commit after this phase.

## Phase 4: SSH Smoke With Hashed Probe

Status: shipped.

Build `spark sandbox ssh smoke <name>`.

Probe model:

1. Render checked-in probe content from code, not prompt text.
2. Hash locally.
3. Copy to remote temp path with fixed name prefix.
4. Verify hash remotely.
5. Execute with fixed arguments.
6. Capture bounded output.
7. Remove temp files unless `--keep-debug-files`.

Smoke proves:

- remote temp write
- fixed probe execution
- cleanup
- no secret passthrough
- stable audit event

Acceptance tests:

- tampered probe hash blocks execution
- cleanup runs on success and failure
- keep-debug flag keeps temp file and says so
- stdout/stderr limits apply
- probe command cannot include user-supplied shell syntax

Commit after this phase.

## Phase 5: Modal Doctor and Smoke

Status: shipped. Smoke is still explicit because it can touch Modal cloud
resources; `spark verify --sandboxes` only runs Modal doctor.

Files:

- `src/spark_cli/sandbox/modal.py`
- parser hooks
- tests with Modal calls mocked

Build:

- `spark sandbox modal doctor`
- `spark sandbox modal smoke`

Doctor checks:

- Modal SDK import or CLI availability
- auth appears configured without printing token material or local config paths
- configured default timeout/resource caps
- can create a tiny no-secret sandbox when smoke runs

Smoke defaults:

- no Spark secrets
- no project upload
- no persistent volume
- short timeout
- sanitized subprocess env without Spark/provider secrets, local `PYTHONPATH`,
  or local virtualenv inheritance
- explicit cleanup/terminate
- network policy displayed
- bounded output

Acceptance tests:

- no env passthrough by default
- Modal auth status redacts token material
- timeout triggers terminate/cleanup
- network/secrets/cost capabilities are visible
- SDK/CLI failure gives exact next command

Commit after this phase.

## Phase 6: Shared Verification

Status: shipped.

Add report-only verification hooks:

```bash
spark verify --sandboxes --json
```

If adding a new flag feels too broad, defer this phase and keep verification at
`spark sandbox ssh doctor` and `spark sandbox modal doctor`.

Checks:

- sandbox docs exist
- local Docker optional workbench still verifies
- SSH configured targets have fresh doctor status if any exist
- Modal auth is reported without requiring a smoke

Acceptance tests:

- no configured remote targets returns green/neutral
- broken configured target returns repair hints
- hosted installer/provenance checks remain unchanged

Commit after this phase.

## Phase 7: Do Not Build Yet

These wait until doctor/smoke are stable:

- `spark sandbox ssh prepare`
- `spark sandbox ssh deploy-live`
- `spark sandbox modal run`
- Modal artifact pull
- remote log tailing
- persistent Modal volumes
- secret passthrough
- public inbound service setup
- MCP/plugin/skill execution

## UX Standard

Every command should say:

- target
- mode: read-only, dry-run, or mutating
- capabilities crossed
- whether secrets are sent
- timeout/resource limits
- cleanup status
- next command on failure

Every JSON result should include:

```json
{
  "ok": true,
  "target": "name",
  "backend": "ssh",
  "mode": "read_only",
  "capabilities": {},
  "checks": [],
  "audit": {}
}
```

## Security Red Lines

Do not merge code that introduces:

- arbitrary SSH shell
- `shell=True`
- `StrictHostKeyChecking=no`
- `ForwardAgent=yes`
- root remote user by default
- SSH private key contents in config
- secrets in args, URLs, logs, or audit payloads
- network-on Modal smoke by default if avoidable
- implicit project upload to Modal
- artifact auto-execution
- policy decisions made by model text, memory, tool metadata, or remote output

## Test Commands

Run after each phase:

```bash
python -m pytest tests/test_cli.py -q
python -m spark_cli.cli verify --installers --json
python -m spark_cli.cli verify --sandboxes --json
git diff --check
```

The default suite mocks SSH and Modal subprocesses. Only run real SSH or Modal
smoke against an explicitly named test target/account.

## First Build Slice

The first slice was intentionally small:

```text
shared safety primitives + tests + parser skeleton for `spark sandbox`
```

That kept parsing, target storage, subprocess execution, redaction, and audit
from landing as one large risky diff. The shipped follow-up slices now cover
SSH target records, host-key trust, doctor, remote probe, hashed smoke, Modal
doctor/smoke, and shared `spark verify --sandboxes`.
