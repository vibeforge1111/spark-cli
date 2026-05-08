# OWASP Agentic Security Deep Dive

Last updated: 2026-05-08

Status: hardening map for shipped SSH/Modal doctor-smoke lanes and future
Docker, Railway, VPS, deploy, artifact, arbitrary-run, and agent/tool
integrations.

## Purpose

This document goes deeper on OWASP material for Spark's remote and agentic
surfaces. It translates OWASP's agentic, LLM, MCP, and skill security work into
concrete Spark controls, tests, and red flags.

The main conclusion is sharper than "detect prompt injection":

```text
Untrusted text must never become authority.
Untrusted tool metadata must never become authority.
Untrusted memory must never become authority.
Untrusted artifacts must never become executable behavior.
```

## OWASP Sources Reviewed

- OWASP Top 10 for Agentic Applications 2026: ASI01-ASI10.
- OWASP Agentic AI Threats and Mitigations: threat-model-based agentic
  reference.
- OWASP Multi-Agentic System Threat Modeling Guide v1.0.
- OWASP Top 10 for LLM Applications 2025: LLM01-LLM10.
- OWASP MCP Top 10 2025 beta/incubator: MCP01-MCP10.
- OWASP Agentic Skills Top 10: AST01-AST10, covering agent skill ecosystems.
- OWASP Prompt Injection attack page.

## Spark Surfaces In Scope

Spark's highest-risk surfaces are operational rather than chat-only:

- Telegram chat and `/run` mission ingress.
- Spawner mission planning and canvas/board state.
- Builder memory and recall.
- Research/web/document ingestion.
- Installer scripts and module registries.
- Optional Docker sandbox runs.
- Railway and VPS hosted Spark Live.
- Shipped SSH remote-machine target records, host-key trust, doctor, remote
  probe, and hashed smoke.
- Shipped Modal ephemeral doctor and explicit no-secret smoke.
- Future SSH deploy, Modal run/artifact pull, and other remote execution
  expansion.
- Future MCP, plugin, or skill-style extension points.

## Agentic Top 10 Mapping

| OWASP risk | Spark failure mode | Required control | Required test |
|---|---|---|---|
| ASI01 Agent Goal Hijack | A prompt, web page, repo file, or tool result redirects a mission from "smoke test" to "export secrets" | mission objective envelope; untrusted-content labeling; action classifier independent of model text | indirect injection in repo/web content cannot change allowed capability set |
| ASI02 Tool Misuse and Exploitation | Legitimate tools are chained to read a secret, write an artifact, and exfiltrate it | tool capability graph; deny toxic tool combinations; per-action approval | `read_secret + network_write` chain is blocked even when each tool is individually allowed |
| ASI03 Identity and Privilege Abuse | Agent uses admin Telegram identity, Railway token, SSH key, or provider token outside intended scope | per-backend scoped identity; short-lived or revocable credentials; no shared production token in smoke | a non-admin channel cannot trigger admin-only remote actions; token names only in logs |
| ASI04 Agentic Supply Chain Vulnerabilities | Tool manifests, skills, module pins, installer metadata, or remote probes are tampered | provenance, hash pinning, signed/checked templates, registry allowlist, no auto-update for agentic tools | tampered probe/script/manifest fails before execution |
| ASI05 Unexpected Code Execution | Model output, Markdown, YAML, tool schema, or artifact becomes shell/code/template execution | structured argv, safe parsers, no `eval`, no shell construction, artifact never auto-executes | malicious Markdown/YAML/artifact is treated as data |
| ASI06 Memory and Context Poisoning | Persistent memory tells future agents to trust a host, leak secrets, or bypass approvals | source-scoped memory; memory cannot grant authority; age/source/confidence shown | poisoned memory cannot alter policy, target trust, or approval result |
| ASI07 Insecure Inter-Agent Communication | Fake agent/tool/mission messages spoof status, approval, or completion | signed/correlated mission events; source identity; replay protection for approvals | forged completion/approval event is rejected |
| ASI08 Cascading Failures | One bad mission fans out to many retries, builds, deploys, or provider calls | circuit breakers; per-target concurrency; retry budgets; kill switch | failing Modal/Railway job does not trigger unbounded retries or deploy fanout |
| ASI09 Human-Agent Trust Exploitation | Agent presents a polished but misleading approval prompt that hides risk | approval prompt generated from policy metadata, not model prose; show diff/capabilities | prompt injection cannot hide `secrets`, `network`, `sudo`, `public inbound`, or `cost` badges |
| ASI10 Rogue Agents | Agent hides work, persists after cancellation, or operates outside its mission | explicit TTL, cancellation, cleanup proof, audit trail, no self-modifying policy | canceled/timeout sandbox is terminated and audit records cleanup status |

## LLM Top 10 Mapping

| OWASP risk | Spark interpretation |
|---|---|
| LLM01 Prompt Injection | Treat direct, indirect, multimodal, hidden Unicode, repo-doc, web-page, PDF, and tool-result injection as expected hostile input. Defense is capability gating, not prompt wording. |
| LLM02 Sensitive Information Disclosure | Secrets must not enter model context, memory, logs, support bundles, artifact manifests, process args, URLs, or persistent tool state unless a reviewed command explicitly needs a named secret. |
| LLM03 Supply Chain | Module pins, installer checksums, probe scripts, Docker images, Modal images, skill manifests, and tool schemas need provenance and drift checks. |
| LLM04 Data and Model Poisoning | Memory, RAG, research notes, and benchmark artifacts need source labels, trust tiers, expiry, and no automatic elevation into instructions. |
| LLM05 Improper Output Handling | Model output must be validated before reaching shell, SQL, API calls, HTML/Markdown rendering, file paths, env files, or deployment manifests. |
| LLM06 Excessive Agency | Give the agent only the minimum tools, permissions, autonomy, retries, tokens, network, and persistence required for the current command. |
| LLM07 System Prompt Leakage | Treat prompt leakage as possible; never put secrets, hidden admin policy, or irreversible capabilities only in prompts. |
| LLM08 Vector and Embedding Weaknesses | Retrieval can return poisoned or cross-tenant context; memory recalls must remain source-aware and scoped. |
| LLM09 Misinformation | Agent explanations are advisory; health, deploy, and security decisions must depend on deterministic checks. |
| LLM10 Unbounded Consumption | Set token, time, retry, process, file, network, and cloud-cost limits for every sandbox and mission. |

## MCP Top 10 Implications

Spark does not need to ship MCP support before SSH/Modal, but the planned agent
interfaces are close enough that MCP risks should shape the design now.

| MCP risk | Spark design requirement |
|---|---|
| MCP01 Token Mismanagement and Secret Exposure | Context, memory, logs, and tool traces are secret-hostile by default. Runtime secret injection is named, scoped, and nonpersistent. |
| MCP02 Privilege Escalation via Scope Creep | Capabilities are explicit, reviewable, and do not grow silently across sessions or retries. |
| MCP03 Tool Poisoning | Tool/probe/schema descriptions are signed or hashed; changes require review before use. |
| MCP04 Supply Chain and Dependency Tampering | Pin every remote executable template, image, package lane, and module revision used by agentic execution. |
| MCP05 Command Injection and Execution | Use structured argv and fixed scripts; reject metacharacters where they do not belong. |
| MCP06 Intent Flow Subversion | Retrieved context can inform analysis but cannot rewrite the mission, policy, or approval request. |
| MCP07 Insufficient Authentication and Authorization | Every agent-to-tool and agent-to-backend call carries a verified actor/target context. |
| MCP08 Lack of Audit and Telemetry | Every remote action emits a local audit event with capabilities, approval id, and redaction version. |
| MCP09 Shadow MCP Servers | No hidden/unregistered tool servers, proxies, or remote endpoints may be added by prompt or memory. |
| MCP10 Context Injection and Over-Sharing | Context windows and memories are user/session/mission scoped; cross-agent sharing is explicit. |

## Agentic Skills Top 10 Implications

OWASP's Agentic Skills Top 10 is highly relevant because Spark may eventually
support skills/plugins/tool bundles. It highlights that behavior-layer files can
become an execution layer.

Spark rules:

- No unverified third-party skill or plugin marketplace in the sandbox v1.
- Skill manifests must declare permissions and network/secrets/filesystem use.
- Skill versions must be pinned; updates are reviewed, not silent.
- Skill metadata is untrusted input, not instructions.
- Skill loading uses safe parsers only.
- Skills run inside the same capability policy and audit trail as built-in
  tools.
- Skill install, update, and enablement require inventory and rollback.

## Common Attack Catalogue

These are the cases Spark should assume will happen:

- Direct prompt injection: "ignore previous instructions".
- Indirect prompt injection in web pages, README files, PDFs, issues, logs, or
  tool output.
- Hidden HTML comments, CSS-hidden text, zero-width characters, homoglyphs, and
  non-printing Unicode.
- Prompt injection through images, OCR text, image metadata, audio transcripts,
  or screenshots.
- Model output used as shell, SQL, HTML, Markdown, YAML, TOML, JSON, env files,
  or deployment config.
- Tool chaining from read to write to network exfiltration.
- Artifact path traversal through `../`, absolute paths, symlinks, tar/zip
  slips, Windows drive paths, and reserved device names.
- Secrets in command-line args, environment dumps, debug logs, crash reports,
  support bundles, process listings, prompt context, or memory.
- SSRF to localhost, private networks, cloud metadata IPs, `.local`,
  `.internal`, alternate IPv4 encodings, IPv6 embedding, redirects, or DNS
  rebinding.
- Cost exhaustion through retries, long context, recursive agent loops,
  oversized artifacts, or cloud sandboxes left running.
- Supply-chain drift in installers, Docker images, probe scripts, package
  names, module pins, and tool schemas.

## Less Common but Important Attacks

These are easy to miss during implementation:

- Approval laundering: the model frames a risky action as routine maintenance,
  causing a human to approve it.
- Tool schema poisoning: a tool description or parameter schema changes the
  agent's interpretation of what the tool does.
- Tool rug pull: a remote tool behaves safely during testing, then changes
  server-side behavior after approval.
- Shadow tool/server registration: prompt or memory causes the agent to use an
  unregistered endpoint.
- Context over-sharing: one mission/user/profile sees another mission's
  context, memory, logs, or artifacts.
- Memory time bomb: a low-risk memory entry later biases high-risk deployment
  actions.
- Async result poisoning: a queued job returns malicious output after the
  original approval context is gone.
- Event spoofing: a fake agent or remote service emits "approved", "verified",
  or "complete" messages.
- Replay: an old approval token or mission event is reused for a new target.
- Status forgery: a remote host prints success text that looks like Spark's
  own trusted status.
- Terminal output injection: ANSI escape sequences, hyperlinks, or control
  characters manipulate the operator's terminal.
- Markdown exfiltration: generated Markdown includes remote images or links
  that encode private state.
- Provider base URL hijack: a malicious or typoed provider endpoint receives
  prompts/secrets.
- OAuth/account confusion: the wrong Modal/Railway/profile identity is active.
- Stale target confusion: a saved target points at a recycled VPS or changed
  Railway environment.
- Cross-platform skill reuse: a malicious behavior file is adapted from one
  agent ecosystem to another.

## Rare and High-Impact Cases

These should not dominate v1, but the architecture should not make them
impossible to defend later:

- Rogue-agent behavior: an agent hides steps, resists cancellation, mutates its
  own instructions, or tries to persist itself.
- Multi-agent collusion or emergent coordination across delegated workers.
- Covert channels through timing, token usage, filenames, artifact sizes, or
  error messages.
- Model extraction or data reconstruction through high-volume probing.
- Poisoned evaluation suites that make insecure behavior look safe.
- Compromised sandbox provider account with valid API access.
- Compromised remote host that returns plausible but false doctor/smoke data.
- CI/CD confused deputy where Spark's deploy token modifies a repo or service
  the user did not intend.
- Long-lived memory poisoning that survives repo reinstall or profile switch.

## Spark Fortification Requirements

### 1. Capability Policy

Every command must declare capabilities before execution:

```text
filesystem, network, secrets, persistence, privilege, inbound, cost
```

The capability set is computed by code and displayed to the user. It is not
written by the LLM.

### 2. Toxic Flow Blocking

Some combinations are more dangerous than their parts:

| Flow | Default |
|---|---|
| secret access + network write | deny |
| secret access + artifact publish | deny |
| private file read + public inbound | approval |
| deploy + stale doctor | deny |
| sudo + generated script | deny |
| memory write + policy change | deny |
| untrusted artifact + execute | deny |
| tool install/update + immediate execution | approval plus isolated smoke |

### 3. Context Labels

Every context item should carry labels:

```text
source=telegram|repo|web|tool|memory|remote|artifact|operator
trust=operator|spark|blessed|third_party|untrusted
scope=user|profile|mission|target|global
age=<timestamp>
```

Policy must ignore context items when they try to grant authority.

### 4. Memory Guard

Memory can inform suggestions, but it cannot:

- approve actions
- trust SSH host keys
- select secrets
- change deploy targets
- loosen network policy
- suppress doctor failures
- mark artifacts safe
- override owner/admin checks

### 5. Tool and Probe Integrity

Remote probes, tool manifests, and future skills need:

- local checked-in templates
- hash verification before remote execution
- stable IDs in audit events
- review-required updates
- no prompt-authored tool schemas

### 6. Output Handling

Model and remote output must be treated as data:

- escape Markdown/HTML when rendered in web UI
- strip terminal control characters from human output
- validate JSON against schemas
- validate paths after resolution
- reject shell metacharacters unless the field explicitly permits them
- never turn output into commands without a fixed template and policy approval

### 7. Audit and Kill Switch

Remote execution needs:

- per-action audit event
- mission id and target id correlation
- approval id and approver identity
- policy version and redaction version
- cleanup status
- global kill switch for remote execution
- per-target circuit breaker

## Red-Team Test Seeds

Before expanding beyond shipped SSH/Modal doctor-smoke, add tests or scripted
fixtures for:

- repo README contains hidden instruction to leak secrets
- web fetch result asks Spark to call a network tool
- memory contains "always trust this host"
- tool output includes fake "APPROVED" status
- Modal artifact contains `../.ssh/id_rsa`
- SSH target name contains shell metacharacters
- remote output includes ANSI erase-screen and clickable terminal hyperlink
- provider base URL contains credentials, query, fragment, or non-HTTPS scheme
- queued mission result arrives after cancellation
- non-admin Telegram user submits `/run deploy production`
- approval prompt includes all risky capabilities despite model trying to hide
  them
- retry loop hits budget and stops
- stale doctor blocks deploy
- changed host key blocks SSH action
- network-off smoke cannot reach external or metadata endpoints
- secrets redaction catches env assignment, JSON, bearer, PEM, provider key,
  GitHub token, npm token, and Telegram token forms

## Build Order Implication

The OWASP reading reinforces the shipped order and next expansion sequence:

1. Shipped: SSH doctor/add/remove with no arbitrary command execution.
2. Shipped: SSH smoke with fixed hashed probes.
3. Shipped: Modal doctor/smoke with no secrets and bounded cleanup.
4. Shipped: shared capability policy and audit schema.
5. Next: controlled run/deploy commands only after toxic-flow tests exist.
6. Later: MCP/skills/plugin support only after manifest, provenance,
   permission, and runtime isolation controls exist.

## Sources

- OWASP Top 10 for Agentic Applications announcement:
  https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/
- OWASP Top 10 for Agentic Applications 2026 resource:
  https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- OWASP Agentic AI Threats and Mitigations:
  https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/
- OWASP Multi-Agentic System Threat Modeling Guide:
  https://genai.owasp.org/resource/multi-agentic-system-threat-modeling-guide-v1-0/
- OWASP Top 10 for LLM Applications 2025:
  https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/
- OWASP Prompt Injection:
  https://owasp.org/www-community/attacks/PromptInjection
- OWASP MCP Top 10:
  https://owasp.org/www-project-mcp-top-10/
- OWASP Agentic Skills Top 10:
  https://owasp.org/www-project-agentic-skills-top-10/
