# Agentic Remote Sandbox Security Research

Last updated: 2026-05-08

Status: source-backed design notes for shipped SSH/Modal doctor-smoke lanes and
future Docker, Railway, VPS, deploy, and arbitrary-run execution lanes.

## Purpose

This document captures the security lessons Spark borrows from Hermes,
OpenClaw, Codex, Modal, OpenSSH, Docker, gVisor, Firecracker, OWASP, and NCSC
for the shipped SSH/Modal doctor-smoke lanes and for broader Railway/VPS,
deploy, artifact, and arbitrary-run execution that remains future work.

The core rule is:

```text
LLM proposes. Spark policy gates. Backend adapter executes.
```

Prompt text, model judgment, route metadata, and remote host output are not
security boundaries. Deterministic policy and least-privilege runtime design are
the boundary.

## Systems Reviewed

### Hermes

Local files reviewed in a disposable research checkout:

- `hermes-agent/tools/environments/base.py`
- `hermes-agent/tools/environments/ssh.py`
- `hermes-agent/tools/approval.py`
- `hermes-agent/website/docs/user-guide/security.md`

Useful patterns:

- A shared environment interface keeps `local`, `docker`, `ssh`, `modal`, and
  other backends from leaking backend-specific behavior into the agent loop.
- Dangerous command detection is centralized and session-aware.
- Gateway and CLI approval flows are separate from the command runner.
- Security docs explain backend differences, not just commands.

Spark should borrow the environment-adapter split and approval centralization.
Spark should not copy the part where SSH exposes broad command strings early.
Our SSH v1 should use fixed doctor/smoke probes, not arbitrary shell.

### OpenClaw

Local files reviewed in a disposable research checkout:

- `openclaw/src/agents/tool-policy.ts`
- `openclaw/src/agents/tool-fs-policy.ts`
- `openclaw/src/infra/net/ssrf.ts`
- `openclaw/src/agents/tools/web-guarded-fetch.ts`
- `openclaw/src/media/inbound-path-policy.ts`
- `openclaw/src/logging/redact.ts`
- `openclaw/src/commands/doctor-sandbox.ts`

Useful patterns:

- Tool policy is resolved before tools execute.
- Owner-only tools are hidden from non-owner senders and still guarded if
  invoked.
- Filesystem access can be constrained to workspace-only mode.
- SSRF guards block localhost, private networks, special-use IPs, and DNS
  rebinding through pinned lookups.
- Inbound file paths are validated against allowed roots.
- Redaction covers env assignments, JSON secrets, CLI secret flags, bearer
  headers, PEM keys, common token prefixes, and Telegram bot tokens.
- Sandbox doctor checks produce practical repair hints.

Spark should borrow policy-before-tool execution, SSRF/path guards, redaction
patterns, and doctor-first onboarding.

### Codex

OpenAI Codex docs emphasize two layers: sandbox mode defines what the agent can
technically do, and approval policy defines when the agent must ask before
acting. The default model is workspace-limited writes, no network by default,
and approval prompts for actions that leave the sandbox or use network access.
Codex cloud also separates setup with network access from an offline agent phase
and removes configured secrets before the agent phase.

Spark should borrow:

- workspace-bound defaults
- network-off by default
- approval for boundary crossing
- protected paths for `.git`, `.agents`, `.codex`, `.env`, and secret files
- fail-closed automatic review behavior for risky approvals

### Modal

Modal Sandboxes are designed for untrusted user or agent code. Their docs state
that default sandboxes cannot accept incoming network connections or access
Modal resources, and that outbound access can be blocked or restricted with
CIDR allowlists.

Spark should borrow:

- no secrets by default
- no inbound network by default
- network blocked for smoke where supported
- CIDR allowlists for explicit network-on runs
- terminate/cleanup as part of the command contract

### OpenSSH

OpenSSH client configuration supports script-friendly `BatchMode=yes`,
identity scoping with `IdentitiesOnly=yes`, host key checking, agent selection
with `IdentityAgent`, and connection sharing through `ControlMaster`. The
manual recommends control sockets live in directories not writable by other
users. OpenSSH server config defaults `PermitTunnel=no` and
`PermitUserEnvironment=no`; enabling user environment processing can bypass
some access restrictions.

Spark should borrow:

- Spark-owned known-hosts
- strict host-key checking after guided add
- no SSH agent forwarding
- no X11/remote/dynamic forwarding in v1
- control sockets under a private Spark runtime directory
- no remote user environment trust

### Docker, gVisor, and Firecracker

Docker rootless mode reduces daemon/runtime privilege by running both inside a
user namespace. Docker seccomp docs describe the default seccomp profile as an
allowlist that blocks many kernel-sensitive syscalls and recommend keeping it.

gVisor provides a stronger isolation layer than native containers by moving
application-facing kernel behavior into a per-sandbox userspace kernel, with a
tradeoff in compatibility and syscall-heavy performance.

Firecracker microVMs provide KVM-based isolation with a minimal device model and
smaller attack surface than general-purpose virtual machines.

Spark should treat these as a ladder:

1. Docker workbench: good developer isolation and smoke testing.
2. gVisor-backed containers: stronger hosted untrusted-code lane when available.
3. Firecracker/microVMs: future high-isolation lane for multi-tenant or hostile
   workloads.

### OWASP and NCSC

OWASP's 2026 Agentic Top 10 is the closest fit for Spark because Spark agents
plan, use tools, call providers, run sandboxes, keep memory, and coordinate
missions. The relevant risk set is broader than prompt injection: goal hijack,
tool misuse, identity abuse, agentic supply chain, unexpected code execution,
memory/context poisoning, insecure inter-agent communication, cascading
failures, human-agent trust exploitation, and rogue-agent containment.

OWASP LLM06 defines Excessive Agency as excessive functionality, excessive
permissions, and excessive autonomy. Its mitigations map directly onto Spark:
minimize tools, avoid open-ended extensions, minimize permissions, run in the
user context, require human approval for high-impact actions, and enforce policy
outside the LLM.

OWASP's MCP Top 10 adds useful controls even before Spark ships MCP support:
avoid contextual secret leakage, scope tool privileges tightly, defend against
tool poisoning, reject command injection, audit tool calls, and prevent context
over-sharing. OWASP's Agentic Skills Top 10 is also relevant to any future
plugin or skill lane: behavior-layer files can become execution-layer supply
chain risk.

NCSC frames prompt injection as an "inherently confusable deputy" problem. The
important design consequence is that Spark must reduce the impact of a confused
model, not pretend that a prompt can reliably prevent confusion.

See [OWASP agentic security deep dive](./OWASP_AGENTIC_SECURITY_DEEP_DIVE.md)
for the Spark-specific ASI/LLM/MCP/skill mapping and red-team test seeds.

## Spark Threat Model

Assume at least one of these can be hostile or compromised:

- Telegram user text or forwarded content
- Spawner mission prompts
- repository files read by the agent
- generated code or install scripts
- remote host output
- web pages fetched by tools
- artifacts produced by sandboxes
- provider/model output
- stale config from a previous Spark run
- network path between Spark and SSH/Modal/Railway

High-impact attack paths:

| Attack path | Example | Spark control |
|---|---|---|
| Prompt injection to tool action | Repo doc asks Spark to exfiltrate tokens | deterministic action classifier, least tool set, no secrets by default |
| Tool poisoning | Tool description or schema silently changes behavior | hashed/signed templates, tool inventory, review before use |
| Memory time bomb | Old memory says to trust a target or bypass approval | memory cannot grant authority; source/age/scope labels |
| Approval laundering | Agent hides risk in polished human prompt | approval UI generated from policy metadata, not model prose |
| Event spoofing/replay | Fake agent says a remote action was approved or complete | signed/correlated events, nonce/mission ids, replay rejection |
| Excessive agency | Agent gets generic shell and broad credentials | fixed commands first, explicit capability manifest, approval gates |
| SSH MITM | DNS points VPS name at attacker | host fingerprint confirmation, Spark-owned known_hosts, fail closed |
| Remote host compromise | VPS prints fake success and reads secrets | no default secrets, bounded probes, separate revocable service keys |
| SSRF | Tool fetches cloud metadata or localhost | strict URL/IP/DNS guard before fetch |
| Path traversal/symlink escape | Artifact pull writes outside output dir | resolved path checks, workspace roots, no symlink-follow writes |
| Secret leakage | Env or bearer token printed in logs | never pass secrets as args, redaction, bounded logs, support bundle rules |
| Sandbox persistence | Old job keeps service or credentials alive | short TTL, terminate on timeout, cleanup command, stale-job doctor |
| Cost exhaustion | Modal/Railway job loops | timeouts, CPU/memory caps, max retries, cost-risk prompt |
| Supply chain | Installer downloads unsigned runtime | checksums, pinned sources, provenance verify, no pipe-to-shell docs |

## Required Architecture

Every backend should expose a capability manifest before it can run work:

```text
backend: ssh | modal | docker | railway | local
filesystem: none | temp | workspace | project | host
network: off | allowlist | on
secrets: none | named-env | provider-secret | host-env
persistence: ephemeral | session | named-target
privilege: non-root | rootless-container | root | sudo-gated
inbound: none | authenticated | public
cost: free-local | bounded-cloud | metered-cloud
```

Every action should be classified before execution:

```text
read_only
write_workspace
network_read
network_write
secret_access
remote_execute
deploy
destructive
privileged
public_inbound
metered_cost
```

The policy engine decides whether the action is allowed, denied, or requires
approval. Backends receive only already-approved, structured actions.

Some capability combinations are denied even when each individual capability
can be valid alone:

| Toxic flow | Default decision |
|---|---|
| secret access + network write | deny |
| secret access + artifact publish | deny |
| memory write + policy change | deny |
| untrusted artifact + execute | deny |
| tool install/update + immediate execution | approval plus isolated smoke |
| deploy + stale doctor | deny |

## Baseline Controls

- No arbitrary remote shell in SSH v1.
- No default Spark secrets in Modal, SSH, Docker, or Railway smoke jobs.
- No provider keys in CLI args, process titles, URLs, logs, or support bundles.
- No implicit project upload to Modal.
- No SSH root user by default.
- No `ForwardAgent`, X11 forwarding, dynamic forwarding, or remote forwarding
  by default.
- No `StrictHostKeyChecking=no`.
- No network-on sandbox unless a command explicitly asks for it.
- No local/private/special-use URL fetches unless a trusted internal endpoint
  policy names the host.
- No writing outside Spark-owned config, workspace, or selected artifact output.
- No execution of pulled artifacts.
- No long-running cloud sandbox without TTL and cleanup visibility.
- No mutation after stale doctor; run doctor again.
- No memory, retrieved context, tool description, or remote output can grant
  authority, trust a target, approve an action, or change policy.
- No hidden/unregistered tool server, skill, plugin, or remote endpoint can be
  added by prompt or memory.

## UX Requirements

Security should feel like clarity, not paperwork:

- The first line of every remote command says whether it is read-only, dry-run,
  or mutating.
- Risk summaries name concrete capabilities: network, secrets, public port,
  cost, sudo, persistence.
- The user sees target identity before mutation: backend, host/environment,
  user, workspace, last doctor time.
- Errors include the next command to fix the issue.
- Host-key mismatch is a dedicated, scary error with fingerprint comparison.
- Missing Docker/Modal/SSH setup explains whether it is optional or required.
- Approval prompts show exactly which capability is being crossed.
- JSON output exists for agents and CI; human output stays concise.

## Implementation Gates

Before SSH doctor lands:

- command construction tests prove no prompt/user field becomes shell syntax
- host-key add and mismatch tests exist
- target-name/path validation tests exist
- log redaction tests cover env, bearer, PEM, Telegram, and provider tokens

Before SSH smoke lands:

- probe script hash verification tests exist
- timeout and cleanup tests exist
- no-secret-passthrough test exists
- bounded stdout/stderr tests exist

Before Modal smoke lands:

- Modal SDK/CLI calls are mocked in tests
- no-secrets default is asserted
- network-off or network-policy behavior is represented in the command summary
- timeout triggers terminate/cleanup
- artifact pull refuses absolute or parent-traversal outputs

Before any deploy command lands:

- dry-run is default for new or stale targets
- approval gate covers deploy, public inbound, secrets, sudo, and cost
- rollback plan prints before mutation
- audit event schema is stable
- docs and tests prove what secrets can cross the boundary

Before any MCP, skill, or plugin lane lands:

- manifests declare permissions for filesystem, network, secrets, persistence,
  privilege, inbound access, and cost
- manifest/schema/tool-description changes are pinned and reviewed
- skill metadata is parsed as data, not instructions
- unregistered or shadow tool servers are rejected
- tool calls emit audit events with actor, target, tool id, parameters summary,
  and redaction version

## PR Red Flags

Reject or redesign any PR that introduces:

- `shell=True` or shell string concatenation with user/prompt/remote values
- `StrictHostKeyChecking=no`
- `ForwardAgent=yes`
- remote execution as root by default
- SSH private key contents stored in Spark config
- secrets passed as CLI flags
- `env` dumps in logs or diagnostics
- Docker socket mount into an agent-controlled container
- `--privileged`, `seccomp=unconfined`, or broad capability add
- implicit whole-repo upload to Modal
- network enabled by default for smoke jobs
- artifact auto-execution after pull
- approval decisions made only by an LLM
- memory or retrieved context granting authority
- tool/schema/skill metadata treated as trusted instructions
- hidden tool/server registration from prompt, memory, or repo files
- approval prompts whose risk summary is model-authored instead of policy-authored

## Sources

- OpenAI Codex agent approvals and sandboxing:
  https://developers.openai.com/codex/agent-approvals-security
- Modal Sandboxes:
  https://modal.com/docs/guide/sandboxes
- Modal Sandbox networking/security:
  https://modal.com/docs/guide/sandbox-networking
- Docker rootless mode:
  https://docs.docker.com/engine/security/rootless/
- Docker seccomp:
  https://docs.docker.com/engine/security/seccomp/
- OpenSSH client config:
  https://man.openbsd.org/ssh_config.5
- OpenSSH server config:
  https://man.openbsd.org/sshd_config.5
- gVisor security model:
  https://gvisor.dev/docs/
- Firecracker:
  https://firecracker-microvm.github.io/
- OWASP LLM06 Excessive Agency:
  https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
- OWASP Top 10 for Agentic Applications:
  https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- OWASP MCP Top 10:
  https://owasp.org/www-project-mcp-top-10/
- OWASP Agentic Skills Top 10:
  https://owasp.org/www-project-agentic-skills-top-10/
- NCSC prompt injection guidance:
  https://www.ncsc.gov.uk/blog-post/prompt-injection-is-not-sql-injection
