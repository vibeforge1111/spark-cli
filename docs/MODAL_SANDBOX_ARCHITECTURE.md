# Modal Sandbox Architecture

Last updated: 2026-05-08

Status: implemented for doctor and explicit no-secret smoke. Controlled run,
artifact pull, and persistent environments remain future work.

## Purpose

The Modal lane gives Spark an ephemeral cloud sandbox for clean execution,
provider experiments, reproducible smoke tests, and future burst/GPU workloads.

Modal is a better fit than SSH for disposable execution because Modal Sandboxes
are designed for untrusted user or agent code. SSH is better for user-owned
machines. These two lanes should complement each other, not become one blurred
"remote shell" abstraction.

## User Promise

Spark should make Modal feel like a safe temporary workbench:

1. Check Modal auth.
2. Create a tiny sandbox.
3. Run a bounded command.
4. Clean up automatically.
5. Later, opt into artifact pull or controlled runs only after a risk summary.

The user should understand cost, network access, secrets, and cleanup before a
job starts.

## Command UX

Shipped commands:

```bash
spark sandbox modal doctor
spark sandbox modal smoke
```

Future controlled-run commands:

```bash
spark sandbox modal run -- python -c "print('Spark Modal OK')"
spark sandbox modal list
spark sandbox modal cleanup
spark sandbox modal run-build --prompt-file prompt.txt
spark sandbox modal artifacts pull <sandbox-id> --output ./artifacts
spark sandbox modal terminate <sandbox-id>
```

The first implementation should not send Spark secrets or user project folders.
It should prove Modal compatibility with a tiny bounded job.

## Secure Architecture

This design follows the shared remote-execution research and checklist:

- [Agentic remote sandbox security research](./AGENTIC_REMOTE_SANDBOX_SECURITY_RESEARCH.md)
- [OWASP agentic security deep dive](./OWASP_AGENTIC_SECURITY_DEEP_DIVE.md)
- [Remote sandbox security checklist](./REMOTE_SANDBOX_SECURITY_CHECKLIST.md)
- [Remote sandbox implementation plan](./REMOTE_SANDBOX_IMPLEMENTATION_PLAN.md)

### Local State

Store only metadata locally:

```text
~/.spark/config/modal_targets.json
~/.spark/logs/remote/modal/*.jsonl
```

Do not store Modal tokens in Spark config. Let Modal's own CLI/SDK auth own
authentication, and make `spark sandbox modal doctor` report whether auth is
available.

### Sandbox Defaults

Default sandbox policy:

- short timeout
- explicit CPU/memory/disk limits
- no persistent volume
- no secrets
- no project checkout mounted
- no inbound network
- outbound network blocked for pure smoke jobs when possible
- automatic terminate/detach on completion
- bounded stdout/stderr capture

Only enable network, secrets, volumes, or artifact persistence through explicit
flags that print a risk summary first.

### Secret Policy

Modal Secrets are the right primitive for credentials, but Spark should not pass
secrets automatically.

Allowed v1 behavior:

- `spark sandbox modal doctor` detects Modal auth without printing tokens.
- `spark sandbox modal smoke` runs with no Spark secrets.
- A future `spark sandbox modal run --allow-env NAME` can pass explicitly named
  env vars only after showing a dry-run summary.

Deferred:

- mapping Spark provider keys into Modal Secrets
- persistent named Modal environments
- long-lived volumes

### Filesystem and Artifacts

Default file policy:

- create a fresh sandbox workspace
- write only the command/script Spark generated
- copy back an explicit artifact directory
- reject absolute local paths unless a future reviewed mount design allows them
- strip local usernames and private paths from human output

Artifact pull should say:

```text
Pulled 3 files from sandbox <id> to <local-dir>.
Review before sharing. Nothing was uploaded elsewhere by Spark.
```

## Attack Vectors and Mitigations

| Attack vector | Risk | Mitigation |
|---|---|---|
| Secret exfiltration | Sandbox code prints or sends keys | no default secrets; explicit env allowlist; redaction; network-off smoke |
| Network abuse | Untrusted code scans or calls endpoints | default network policy visible; use Modal network blocking/allowlists where supported |
| Cost runaway | Long job consumes paid resources | short default timeout; resource caps; terminate on timeout; show estimated risk |
| Data leakage | Local project or memory uploaded accidentally | no default mounts; prompt files only by explicit path; artifact pull only |
| Sandbox persistence drift | Old sandbox keeps state or service running | auto terminate/detach; `cleanup`; list stale sandboxes |
| Prompt injection | User prompt asks to leak Modal/Spark metadata | no secrets; command templates; output redaction |
| Malicious artifacts | Artifact contains executable or hidden files | pull to review folder; show manifest and sizes; never execute pulled files |
| Log injection | Control chars or huge output confuse terminal | strip control chars; byte and line limits |
| Modal auth confusion | User uses wrong Modal environment/profile | doctor reports active environment/profile without secrets |
| Vendor outage or API drift | Sandbox API fails or changes | doctor detects SDK/CLI versions; graceful fallback; no installer dependency |

## Preflight Checks

`spark sandbox modal doctor` should check:

- Python can import Modal SDK, or Modal CLI is installed
- Modal auth is available
- active Modal environment/profile, without secrets or local config paths
- ability to create a tiny no-secret sandbox
- ability to execute a tiny command
- ability to terminate and detach
- configured default timeout/resource caps
- redaction of stdout/stderr

The command should print human output and `--json`.

## Great UX Details

- Show "no secrets will be sent" on the first smoke.
- Show timeout and resource limits before execution.
- Show sandbox id and cleanup status.
- If Modal auth is missing, give the next command and link to Modal docs.
- If a job times out, terminate it and show whether cleanup succeeded.
- If network is enabled, display that as a yellow risk note.
- If secrets are requested, list names only, never values.

## Rollout Plan

### Phase 0: Documentation

Status: shipped.

### Phase 1: Modal Doctor and Smoke

Status: shipped. `spark verify --sandboxes` reports Modal doctor status without
creating a cloud sandbox; `spark sandbox modal smoke` remains explicit.

Build only:

```bash
spark sandbox modal doctor
spark sandbox modal smoke
```

Success criteria:

- no Spark secrets sent
- bounded runtime
- creates and terminates a sandbox
- human and JSON output
- tests with Modal SDK mocked

### Phase 2: Controlled Run

Build:

```bash
spark sandbox modal run -- <argv>
spark sandbox modal terminate <sandbox-id>
spark sandbox modal cleanup
```

Success criteria:

- argv validated
- timeout required
- logs redacted
- network and env flags explicit

### Phase 3: Build Smoke and Artifacts

Build:

```bash
spark sandbox modal run-build --prompt-file prompt.txt
spark sandbox modal artifacts pull <sandbox-id>
```

Success criteria:

- artifact manifest
- no automatic local execution of artifacts
- no implicit project upload

## Explicit Non-Goals for v1

- No automatic provider-key passthrough.
- No persistent Modal volumes.
- No long-running public services.
- No default network access for smoke jobs when the selected API supports
  network blocking.
- No uploading the user's whole repo by default.
- No replacing Railway/VPS Spark Live; Modal is an execution sandbox, not the
  primary always-on Telegram host.

## Sources

- Spark `docs/AGENTIC_REMOTE_SANDBOX_SECURITY_RESEARCH.md` for the broader
  Hermes/OpenClaw/Codex/Modal/OpenSSH/OWASP threat model.
- Modal Sandbox guide and `modal.Sandbox` reference for sandbox lifecycle,
  command execution, filesystem APIs, terminate/detach, and timeouts.
- Modal Sandbox networking/security docs for default isolation, incoming network
  behavior, network blocking, and CIDR allowlists.
- Modal Secrets docs for secret injection as environment variables and why Spark
  should require explicit secret allowlists.
- Spark `docs/OPTIONAL_DOCKER_WORKBENCH.md` and
  `docs/SPARK_LIVE_DOCKER_RAILWAY.md` for existing sandbox and hosted-live
  boundaries.
