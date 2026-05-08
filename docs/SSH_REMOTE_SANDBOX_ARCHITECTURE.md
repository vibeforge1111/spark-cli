# SSH Remote Sandbox Architecture

Last updated: 2026-05-08

Status: implemented for target records, guided host-key trust, doctor,
optional fixed remote probe, and hashed smoke. Prepare/deploy remains future
work.

## Purpose

The SSH lane lets Spark work with a user-owned VPS, GPU box, home server, or
bare-metal machine without asking the user to keep everything on their laptop.

SSH expands compatibility. It is not a sandbox by itself. The security boundary
comes from the remote account, filesystem permissions, command policy, host-key
verification, secrets handling, and Spark's own approval/audit layer.

## User Promise

Spark should make remote machines feel calm:

1. Add a machine.
2. Prove the identity of the machine.
3. See what Spark can safely do there.
4. Run a tiny smoke.
5. Only then opt into deploy or runtime work.

The user should never need to paste a long SSH command from a random answer into
a terminal before Spark explains what will happen.

## Command UX

Shipped doctor/smoke commands are read-only or bounded remote temp probes:

```bash
spark sandbox ssh add <name> --host <host> --user <user> --identity-file <path>
spark sandbox ssh doctor <name>
spark sandbox ssh doctor <name> --remote-probe
spark sandbox ssh trust <name>
spark sandbox ssh smoke <name>
spark sandbox ssh remove <name>
```

Future controlled changes can add:

```bash
spark sandbox ssh prepare <name> --dry-run
spark sandbox ssh prepare <name>
spark sandbox ssh deploy-live <name> --dry-run
spark sandbox ssh deploy-live <name>
spark sandbox ssh rollback-plan <name>
```

No v1 command should expose an arbitrary remote shell. A later expert command
can be considered only after the audit and approval system is strong enough.

## Happy Path

```text
spark sandbox ssh add odyssey-vps --host 203.0.113.10 --user spark --identity-file ~/.ssh/spark_odyssey
  -> writes target config under Spark config
  -> stores no private key material

spark sandbox ssh trust odyssey-vps
  -> scans the host key
  -> records the pinned fingerprint in Spark-owned known_hosts

spark sandbox ssh doctor odyssey-vps
  -> checks ssh client, key file, host-key record, strict argv options, and target metadata
  -> optional --remote-probe verifies login with a fixed read-only command
  -> prints a human report plus JSON

spark sandbox ssh smoke odyssey-vps
  -> uploads a tiny signed/hashed probe script to a temp directory
  -> runs it as the configured non-root user
  -> deletes temp files
  -> prints pass/fail and next steps
```

## Secure Architecture

This design follows the shared remote-execution research and checklist:

- [Agentic remote sandbox security research](./AGENTIC_REMOTE_SANDBOX_SECURITY_RESEARCH.md)
- [OWASP agentic security deep dive](./OWASP_AGENTIC_SECURITY_DEEP_DIVE.md)
- [Remote sandbox security checklist](./REMOTE_SANDBOX_SECURITY_CHECKLIST.md)
- [Remote sandbox implementation plan](./REMOTE_SANDBOX_IMPLEMENTATION_PLAN.md)

### Local State

Store remote target records under Spark config, for example:

```text
~/.spark/config/ssh_targets.json
~/.spark/config/ssh_known_hosts
~/.spark/logs/remote/ssh/<target>.jsonl
```

Each target record should contain:

- target name
- host and port
- user
- identity file path, never key contents
- expected host-key fingerprint
- remote workspace root
- allowed command profile
- created and last verified timestamps

The Spark-owned `ssh_known_hosts` file prevents Spark from silently mutating the
user's global `~/.ssh/known_hosts`.

### SSH Client Defaults

Use explicit options for every SSH invocation:

```text
BatchMode=yes
IdentitiesOnly=yes
ForwardAgent=no
RequestTTY=no
StrictHostKeyChecking=yes
UserKnownHostsFile=<spark-owned-known-hosts>
ServerAliveInterval=10
ServerAliveCountMax=3
```

Use the dedicated `spark sandbox ssh trust <name>` flow to scan and pin a host
fingerprint. Normal doctor, smoke, and deploy commands must use
`StrictHostKeyChecking=yes`.

Do not enable agent forwarding, X11 forwarding, dynamic forwarding, remote
forwarding, or broad port forwarding by default.

### Remote Account Defaults

Recommend a dedicated non-root account:

```text
user: spark
home: /home/spark
workspace: /home/spark/spark-live or /opt/spark owned by spark
sudo: not required for doctor/smoke
```

Phase 1 should not require `sudo`. If a future prepare step needs packages or a
system service, Spark should show a dry-run and ask the user before any elevated
action.

### Command Execution Model

Do not build remote commands by concatenating user input into shell strings.

Preferred execution pattern:

1. Render a local probe script from a checked-in template.
2. Hash it locally.
3. Copy it to a Spark temp directory on the remote host.
4. Verify its hash remotely.
5. Execute the script with fixed arguments.
6. Capture bounded stdout/stderr.
7. Remove the temp script unless `--keep-debug-files` is set.

For future richer read-only probes, use fixed argv-style commands where
possible:

```text
uname -a
id -u
df -Pk <workspace>
docker version --format ...
```

Never pass provider API keys or Telegram tokens in command arguments. If a
future command needs secrets, use an explicit env allowlist and redact logs.

## Attack Vectors and Mitigations

| Attack vector | Risk | Mitigation |
|---|---|---|
| Host impersonation / MITM | Spark sends commands or secrets to the wrong host | Show fingerprint on add, store expected fingerprint, use `StrictHostKeyChecking=yes` after add |
| Changed host key | Existing server replaced or DNS hijacked | Fail closed, print fingerprint mismatch, require explicit re-trust command |
| Compromised remote host | Remote can read any secret sent to it | Do not send secrets by default; scoped env allowlist; separate revocable service keys |
| Private key theft | Spark exposes or copies SSH key | Store only key path internally; never copy private keys; hide identity paths from public JSON, previews, checks, and audit output; validate file path and permissions |
| SSH agent abuse | Remote uses forwarded agent to reach other machines | `ForwardAgent=no` always in v1 |
| Shell injection | Host/user/path/prompt changes remote command | validate fields; no raw shell; fixed scripts; quote only trusted paths |
| Privilege escalation | Spark runs as root or broad sudo | non-root user by default; no sudo in phase 1; approval-gated phase 2 |
| Port exposure | Remote forwarding exposes local services publicly | no remote/dynamic forwarding by default; explicit later command only |
| Log/secret leakage | env, tokens, project names appear in output | bounded logs; redaction; never run `env`; support bundle rules apply |
| ANSI/control output | Remote output manipulates terminal display | strip control characters in human output; raw logs stay local |
| Path traversal | Target name or remote root writes outside expected area | strict target-name regex; remote root allowlist; resolve paths before mutation |
| Stale target config | Spark deploys to old host or wrong user | show target summary before actions; require `doctor` freshness for deploy |
| Dependency drift | Host lacks Docker or has unsafe runtime | preflight reports version, rootless/non-root status, disk, ports, kernel |
| Denial of wallet/time | Remote command hangs | per-command timeout, server alive settings, bounded retries |

## Preflight Checks

`spark sandbox ssh doctor <name>` should check:

- local SSH binary available
- target config exists and validates
- identity file exists and is not world-readable when the OS exposes permissions
- expected host key exists in Spark known-hosts
- remote connection works in `BatchMode`
- remote user is not root unless an explicit expert override exists

Future richer preflight can add:

- remote OS and architecture
- free disk and memory
- Docker availability and permission, if Docker lane is requested
- remote workspace exists or can be created by the remote user
- required ports are free for planned Spark Live mode
- no Spark secrets are present in command output

The command should print both:

- human summary with green/yellow/red checks
- `--json` payload for agents and CI

## Great UX Details

- The first screen should say whether Spark is only checking or about to change
  the remote host.
- Every mutating command defaults to dry-run when the target is new or stale.
- Error messages should name the exact next command.
- Host-key mismatch should be scary and specific, not a generic SSH failure.
- Missing Docker should say whether Docker is optional for the requested action.
- SSH key permission problems should explain the fix per OS.
- Logs should show a short tail by default and explain how to request more.
- The target name should appear in every prompt and audit line.

## Rollout Plan

### Phase 0: Documentation

Status: shipped.

### Phase 1: SSH Doctor

Status: shipped.

Build only:

```bash
spark sandbox ssh add
spark sandbox ssh trust
spark sandbox ssh doctor
spark sandbox ssh remove
```

Success criteria:

- no arbitrary remote command input
- host fingerprint stored and enforced
- non-root recommendation visible
- JSON and human output
- tests for command construction and redaction

### Phase 2: SSH Smoke

Status: shipped for hashed smoke. `preflight` and `logs` remain future
commands; v1 keeps the first live remote action limited to a fixed temporary
probe.

Build:

```bash
spark sandbox ssh smoke
```

Success criteria:

- bounded remote probes
- probe script hash verification
- no secret passthrough
- logs redacted and line-limited

### Phase 3: SSH Prepare and Deploy

Build only after phases 1 and 2 are stable:

```bash
spark sandbox ssh prepare --dry-run
spark sandbox ssh deploy-live --dry-run
spark sandbox ssh rollback-plan
```

Actual prepare/deploy remains approval-gated.

## Explicit Non-Goals for v1

- No arbitrary SSH shell.
- No root-login setup flow.
- No automatic sudo package installation.
- No Docker socket mounting from the local machine.
- No copying personal `~/.spark`, `~/.codex`, browser profiles, cloud keys, or
  SSH private keys to the remote host.
- No public port forwarding setup without a separate reviewed design.

## Sources

- Spark `docs/AGENTIC_REMOTE_SANDBOX_SECURITY_RESEARCH.md` for the broader
  Hermes/OpenClaw/Codex/Modal/OpenSSH/OWASP threat model.
- OpenSSH `ssh_config(5)`: `BatchMode`, `StrictHostKeyChecking`,
  `UserKnownHostsFile`, forwarding behavior.
- OpenSSH `sshd_config(5)`: `AllowTcpForwarding`, `ChrootDirectory`,
  `ForceCommand`, `PermitRootLogin`, `PermitTTY`, and forwarding controls.
- Spark `docs/OPTIONAL_DOCKER_WORKBENCH.md` and
  `docs/SPARK_LIVE_DOCKER_RAILWAY.md` for existing sandbox and hosted-live
  boundaries.
