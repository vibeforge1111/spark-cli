# What We Borrow From Hermes, OpenClaw, and SOTA

> Source of truth: `docs/harness-discipline/`. Grounded in the 2026-06-24 Spark harness audit (51 offenders) + Hermes/OpenClaw/Anthropic/OSS research (51 lessons).

This document is the **external evidence base** for the discipline layer. Where `01_RULESET.md` mints the Red Lines (`RL-01`..`RL-18`) and Rules (`R-01`..`R-28`), this document shows *where those rules come from in the wider state of the art* and *why they are not opinions*. Every move here is drawn from a real, shipped, sometimes painfully-CVE'd system. Spark is not inventing harness governance; it is the late mover, and the cheapest lessons are the ones other people already paid for.

The throughline maps to the founder's two pains:

1. **Deterministic hotfixes that became shadow authority** — every reference below has either built the antidote (Hermes' single guard spine, OpenClaw's policy-as-data, Anthropic's workflow/agent split) or paid for the disease (OpenClaw's 60+ advisories, the `hotfix-debt-theory` literature on shotgun surgery and normalization of deviance).
2. **CUAs that drifted into local hotfixes instead of cooperating with a higher-intelligence planner** — the `cua-orchestration` and `oss-harness-comparison` references converge on one shape: a bounded worker that *escalates often* under a planner that owns strategy.

Read this alongside `02_REAL_FIX_PLAYBOOK.md` (how a fix must be shaped) and `03_CUA_ESCALATION_PROTOCOL.md` (how the CUA must hand up). `04_AUDIT_FINDINGS_AND_BACKLOG.md` holds the offender backlog these lessons are aimed at.

A note on grounding: every Spark code claim below cites an offender from the 2026-06-24 audit by exact `file:line`. Every external claim cites the research reference's own `source_url`. Nothing here is invented.

---

## 1. The six references

### 1.1 Hermes Agent (NousResearch) — *brutal honesty about where authority lives*

**Summary.** Hermes Agent is Nous Research's open-source, MIT-licensed, self-improving messaging-gateway agent (CLI + Telegram/Discord/Slack) with ~40+ self-registering tools and pluggable execution backends. Its engineering philosophy is the single most aligned-to-Spark posture in the corpus: its `SECURITY.md` states outright that **the only real security boundary against an adversarial LLM is the operating system**, and explicitly demotes every in-process check — approval gate, output redaction, dangerous-pattern regexes — to "heuristics operating on an attacker-influenced string" that catch "cooperative-mode mistakes, not adversarial output." It then makes that demotion *structural*: bypassing those heuristics is declared **out of scope as a vulnerability**, so the project refuses to let a regex denylist masquerade as containment. Authority is centralized in one guard path (`check_all_command_guards`) that every command funnels through; policy is data (`DANGEROUS_PATTERNS`) separated from mechanism (the approval callback); execution backends implement only the low-level `_run_bash` while the `BaseEnvironment` base class owns all guard/interrupt/timeout enforcement so no backend can bypass it. The trust-bypass toggle (`_YOLO_MODE_FROZEN`) is read **once at import** so no in-process skill can flip it at runtime.

This is Spark's pain #1 already solved in another codebase. Hermes is the model.

**Top transferable lessons.**

| # | Lesson | How it applies to Spark | Maps to |
|---|--------|-------------------------|---------|
| H-1 | Name the real authority boundary; refuse to let a heuristic impersonate it. A heuristic may flag/escalate, never own a terminal verdict. | Direct antidote to pain #1. Every regex-authority offender — `routeFirewall.ts:403-521`, `approval.py:137-597`, `providers.py:1828-1830` — is a heuristic that produces a *terminal deterministic response*, which by Hermes' standard is masquerading as the boundary. Add a test that asserts every route detector returns evidence/escalate, never `allow`. | `RL-01`, `RL-02`, `R-02` |
| H-2 | Funnel all execution through one guard path; backends implement only the leaf primitive and cannot add a private bypass. | The 28-round `cli.py` longpath saga and per-route auth paths grew because each surface owned its own guards. Mirror `BaseEnvironment`: one abstract decision spine; the Telegram CUA, the planner, and any new module override only "do the action" and structurally cannot hotfix in a local approval bypass. Kills "CUA drifted into a local hotfix" because there is no local seam. | `RL-03`, `R-03`, `R-25` |
| H-3 | Separate policy (data) from mechanism (code). A new rule is a `DANGEROUS_PATTERNS` row, not a core branch. Issue #5528 pushes even deployment-specific rules to config so users "cannot mark commands as approval-required without patching the source tree." | `approval.py:137-597` is a ~460-line if/elif ladder — policy smeared into mechanism. 28 hotfix rounds should have been 28 data rows behind one engine. This *is* the `ChangeManifestV1` the charter already mandates. | `R-16`, `R-05` |
| H-4 | Anchor the trust-bypass toggle at import so in-process code can't flip it. `_YOLO_MODE_FROZEN` is read once; "reading os.environ on every call would allow any skill to bypass all approval checks." | `SPARK_APPROVAL_ENFORCE` (`cli.py:10976-10977`) is a single env-var kill switch over the only authority check, re-readable at runtime. A self-evolving harness runs agent-authored code in-process; the security toggle must be frozen at process start / signed config, never re-read from mutable state. Define a Spark hardline floor no self-evolution step can cross. | `RL-06`, `RL-17` |
| H-5 | A reviewing LLM must treat the reviewed command as **untrusted input**: strip comments, XML-wrap, instruct the aux LLM to ignore embedded directives, and return approve/deny/**escalate** — uncertainty escalates to a human, never silently passes. | This is the fix for pain #2. The higher-intelligence planner reviewing a CUA's proposed action must frame that action as untrusted *data* and have a first-class escalate verdict — not a binary that pressures it toward a local approve/hotfix. `legacy_turn_intent.py:595-665` does the opposite: it *fabricates* a `human_confirmation` approval_ref from a confidence heuristic. | `RL-12`, `RL-04`, `R-12` |
| H-6 | "Silence is not consent, a denial is a hard halt": on deny/timeout the agent may not retry, rephrase, or substitute an alternative. | Spark's hotfix culture *is* routing-around-the-deny: a symptom is blocked, so the agent invents a fallback that satisfies the surface check. Encode the rule into the Governor: a stop-ship deny or unmet `ChangeManifest` gate hard-halts; substituting a deterministic fallback that masks the unfixed root cause is prohibited. | `RL-13` |
| H-7 | Fail **closed**, uniformly. `check_fn` exception ⇒ tool "unavailable"; missing-callback/timeout/exception all map to "decline." Failure never becomes fake success. | The single line that distinguishes a legitimate defensive fallback from a failure-masking one. Audit every Spark fallback against it: `voice_judge.py:63-72` returns the midpoint `5` on unparseable judge output (fake-pass), `system_map.py:1186-1193` synthesizes an `unknown` verdict instead of quarantining. Both fabricate success. | `RL-08`, `R-06`, `R-12` |
| H-8 | Govern *new* policy needs toward a general pluggable mechanism, not a special-case in core (issue #16475: "the agent provides the interface, the user provides the logic"). Every quick win is explicitly paired with the long-term general fix. | The institutional habit Spark lacks. When a new determinism case appears the reflex is `isBoundedOperatorProbe` with a hardcoded smoke-test path (`routeFirewall.ts:229`/`:235`). The reflex must instead be "extend the general interface," and a stopgap must name its retirement mechanism (the charter's Legacy Plane Retirement). | `R-15`, `R-16` |
| H-9 | Normalize untrusted input to **one canonical form** before any rule fires, instead of stacking per-evasion patches (`_normalize_command_for_detection`: ANSI/Unicode/escape/path normalization). | The 28-round longpath-guard saga is the anti-pattern: each path edge-case spawned another guard (`cli.py:823-855`). One normalization pass upstream of the rules keeps the rule set small and stops `r28` from becoming `r29`. | `R-07` |
| H-10 | Re-authorize at every trust-boundary crossing; session/route IDs are routing handles, not authorization. Approval in one session never authorizes another (context-local state). | Spark's multi-module mesh (CLI → harness-core → telegram-bot → CUAs) crosses many boundaries. `telegramActionAuthority.ts:79-102` treats `routeAuthorizedByTurn` (a routing fact) as an authorization leg. Re-authorize at each hop through the Governor. | `RL-04`, `R-04` |
| H-11 | Unattended/cron execution gets a **separate conservative resolution** (deny-by-default, halt-and-queue) reusing the same detection — "cron jobs run unattended, so pending approvals would hang indefinitely." | Spark's CUAs and self-evolution loops run unattended — exactly where hotfix drift goes unwitnessed. Autonomous runs must halt-and-queue on uncertainty, not auto-resolve via a fallback. | `R-08`, `R-26` |
| H-12 | Pair every deny with its full enforcement surface or it is "unpaired theater": the `write_file` deny is paired with `sed -i`, `tee`, `>`, `cp` coverage "otherwise the deny is unpaired theater." | Spark's determinism fixes are single-path: they patch the observed route and leave siblings open, which is the structural reason `r1..r28` kept coming. A guard that covers one entry point is theater. | `RL-18` |

**Red lines (Hermes).**

- The only real boundary against adversarial model output is the OS — **never** treat an in-process approval gate, redaction, or regex denylist as containment; they were never authority to begin with.
- A heuristic/regex must **never** own terminal execution authority — it may flag/escalate (`RL-01`).
- Security-disabling state must **never** be re-readable from mutable runtime by in-process code — freeze at import (`RL-06`).
- The hardline blocklist (`rm -rf /`, `mkfs`, `dd` to disk, `shutdown`/reboot, fork bombs) is **never** bypassable, even in YOLO mode.
- An aux-LLM reviewing a command must **never** trust the command text as instructions; uncertainty escalates (`RL-12`).
- A denial or timeout is a hard halt — **never** retry/rephrase/substitute around it (`RL-13`).
- Failure must **never** become fake success (`RL-08`).
- Session/route IDs are **never** authorization (`RL-04`).
- No execution backend gets a private bypass (`RL-03`).
- A deny on one path but not its siblings is unpaired theater and is a defect (`RL-18`).

**Citations (full URLs).**

- Hermes Agent — repo: https://github.com/NousResearch/hermes-agent
- `SECURITY.md` (threat model, "only boundary is the OS", heuristics-not-controls): https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md
- `tools/approval.py` (DANGEROUS_PATTERNS, hardline blocklist, YOLO freeze, `_smart_approve`, cron_mode, "silence is not consent"): https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py
- `tools/environments/base.py` (BaseEnvironment abstract contract, uniform guard/interrupt/timeout): https://github.com/NousResearch/hermes-agent/blob/main/tools/environments/base.py
- DeepWiki — Security and Command Approval (YOLO freeze rationale, normalization, smart approval): https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval
- Developer Guide: Architecture (registry self-registration, env abstraction): https://hermes-agent.nousresearch.com/docs/developer-guide/architecture
- Developer Guide: Tools Runtime (`check_fn` fail-safe, dispatch funnel): https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime
- Issue #16475 (pluggable approval hooks; quick-win vs long-term): https://github.com/NousResearch/hermes-agent/issues/16475
- Issue #5528 (configurable/declarative approval-locked patterns): https://github.com/NousResearch/hermes-agent/issues/5528
- User Guide: Security: https://hermes-agent.nousresearch.com/docs/user-guide/security

---

### 1.2 OpenClaw — *the design done right, and the CVE record of doing it wrong*

**Summary.** OpenClaw is a self-hosted, single-operator AI agent gateway built on one axiom: **the LLM is potentially-adversarial input, never a security boundary** ("System prompt guardrails are soft guidance only; hard enforcement comes from tool policy, exec approvals, sandboxing, and channel allowlists"). Its principle is "access control before intelligence" — identity, scope, tool-policy, sandbox evaluated as *ordered layers before the model runs*. It separates **policy** (declarative data in `openclaw.json`) from **enforcement** (code that re-checks at execution), fails closed by default (unresolved `SecretRef`s fail closed rather than fall back), and names every escape hatch with a literal `dangerously` prefix (`dangerouslyAllowPrivateNetwork`) so weakening security is loud and greppable.

OpenClaw is the rare reference that gives Spark *both halves*: its **design** shows policy-as-data + enforce-in-code done right; its **advisory record** (60+ advisories) shows that every place a guard is a string-match instead of a re-validated canonical operation eventually gets bypassed. The cautionary star is **CVE-2026-45001** (CWE-862): an agent tool (`config.apply`/`config.patch`) could mutate the very config governing it — *shadow authority via missing authorization*, which is Spark's pain #1 stated as a CVE.

**Top transferable lessons.**

| # | Lesson | How it applies to Spark | Maps to |
|---|--------|-------------------------|---------|
| OC-1 | Re-validate against a stored canonical plan at execution time; reject on any drift of command/cwd/agentId/file-operand (approval-mismatch = deny). Defeats TOCTOU. | Spark's regex/fallback sites are decision-*time* string matches that then own execution. The Governor should mint a canonical envelope/manifest at decision time and have the executor re-derive authority from *that object*, not re-run a route regex. The shadow-router offenders (`cli.py:17925-17932` re-deriving intent from `sys.argv`) are this antipattern. | `R-01`, `RL-02` |
| OC-2 | Concede an allowlist/regex is **not a complete semantic model** — and refuse rather than guess when coverage is incomplete (`strictInlineEval` forces approval for `python -c`/`node -e`). | Direct antidote to `hotfix/r28-longpath-guard`: each round patched one more bypass of a regex that was never a semantic model. Spark's CUA must treat "my pattern does not fully cover this input" as an **escalate-to-planner / stop-ship** signal, not license to add round `r29`. | `RL-13`, `R-24`, `R-02` |
| OC-3 | A tool must **never** mutate the policy that governs it (CVE-2026-45001). Agent-driven config writes are fail-closed with a narrow allowlist of tunable fields; control-plane changes are explicitly refused in code. | Spark's pain #1 as a CVE. The Governor must hold an explicit allowlist of which fields self-evolution may touch and **hard-refuse** any write to the authority/policy/security layer (`runtime_policy.py`, `security/`, the manifest gate). The audit's `kernel.py:81` `PROTECTED_EVOLUTION_COMPONENTS` is the right shape — but the protected set must be proven to *include* the authority-bearing files (the gap flagged at `mandate-vs-reality` enforcement-gaps). | `RL-14`, `RL-17`, `R-14` |
| OC-4 | Name escape hatches loudly so weakening security is greppable; defaults fail closed. | Spark has silent `962 fallback / 138 canned / 28 "temporary" / 104 HACK` markers. Adopt a loud greppable convention (`unsafe_`/`maskingFallback_`/`shadowAuthority_`) so a CI lint can **count and gate** them — separating legitimate fail-closed defaults from failure-masking ones by forcing the latter to wear a detectable name. | `R-06`, `RL-08` |
| OC-5 | Resolve paths/identities through a trusted **root handle**, not `path.resolve().startsWith()` (`@openclaw/fs-safe`). | `spark-cli`'s longpath-guard saga (`cli.py:823-855`, `cli.py:533/980-984`) and any CUA file boundary should use canonical-handle resolution once, in code — not string-prefix checks accreted per environment. CVE-2026-26329 (paths passed straight to Playwright `setInputFiles`) is exactly the class Spark's CUA file handling will hit. | `R-07` |
| OC-6 | Canonicalize inputs **before** comparing to a policy. OpenClaw's advisories are a parade of canonicalization gaps: IPv4-mapped IPv6 SSRF, trailing-dot hostnames, shell-expansion allowlist widening, transparent command wrappers. | Spark's regex route matchers compare raw, un-normalized strings — the same bug family. Any intent/route/command match must canonicalize first and match **structured fields**, not free text (`buildIntent.ts`, `conversationIntent.ts:76 sites`, `naturalRouteDecision.ts`). | `R-07`, `R-01` |
| OC-7 | Policy-as-data is only safe if a **separate code layer enforces** it at runtime. `openclaw.json` declares posture but "Policy does not enforce tool calls at runtime" — that lint layer is observational; enforcement lives elsewhere. | Spark must split the same way: declarative Risk-Tier/`ChangeManifest` data (the `schemas/*.json`) that humans audit, PLUS one code chokepoint in `kernel.py` every action passes through. The inverse failure — *enforcement masquerading as scattered policy* (the 138 canned replies as the decision layer) — is precisely the `domain-chip-memory` rescue plane (`providers.py:1828-1830`). | `R-03`, `R-16` |
| OC-8 | Rate-limit + anti-truncation-guard config/self-modification writes (`replacePaths`): a patch that shrinks an existing allowlist array is rejected unless explicitly flagged, so a truncated snapshot can't silently clobber routing. | Maps to Spark's failure-masking fallbacks: a degraded model output that silently returns a truncated/empty result must not be allowed to overwrite real state or delete a safety rule. Self-evolution writes must refuse capability/guard *removal* unless explicitly flagged. | `RL-15`, `RL-08` |

**Red lines (OpenClaw).**

- The model is **never** a security/authority boundary; design so manipulation has limited blast radius (`RL-01`).
- A tool/agent must **never** mutate the policy that governs it (post-CVE-2026-45001) (`RL-14`, `RL-17`).
- **Never** trust the approval-time string at execution time — re-validate the canonical plan; drift = deny (`RL-02`).
- When a guard can't semantically cover an input, **refuse** — do not proceed best-effort (`RL-13`).
- Defaults fail closed: unresolved secrets fail closed, auth required, private-network/SSRF blocked unless a `dangerously`-named flag is set (`RL-08`).
- **Never** validate against an un-canonicalized string (`R-07`).
- Path access goes through a trusted root handle; reject symlinks/`..`/absolute paths at the validation layer (`R-07`).

**Citations (full URLs).**

- Gateway Security (model, fail-closed defaults, `dangerously`-flags): https://docs.openclaw.ai/gateway/security
- Gateway Security index (layered model, policy vs enforcement): https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md
- Exec approvals (canonical plan, TOCTOU revalidation, `strictInlineEval`): https://docs.openclaw.ai/tools/exec-approvals
- CLI Policy ("Policy does not enforce tool calls at runtime"): https://docs.openclaw.ai/cli/policy
- CLI Approvals (rate limits, `replacePaths` anti-truncation guard): https://docs.openclaw.ai/cli/approvals
- Secure file operations (`@openclaw/fs-safe` trusted root handle): https://docs.openclaw.ai/gateway/security/secure-file-operations
- GHSA-cv7m-c9jx-vg7q / CVE-2026-26329 (browser upload path traversal): https://github.com/openclaw/openclaw/security/advisories/GHSA-cv7m-c9jx-vg7q
- GHSA-m3mh-3mpg-37hw (ACE via project `.npmrc` git-executable hijack): https://github.com/openclaw/openclaw/security/advisories/GHSA-m3mh-3mpg-37hw
- VulnCheck / CVE-2026-45001 (config mutation guard bypass via agent tool — CWE-862 shadow authority): https://www.vulncheck.com/advisories/openclaw-gateway-config-mutation-guard-bypass-via-agent-tool-access
- Security Advisories index (60+ advisories): https://github.com/openclaw/openclaw/security/advisories

---

### 1.3 Anthropic / Claude SOTA — *site determinism correctly; make every shortcut emit evidence or an actionable error*

**Summary.** Anthropic's published harness doctrine maps almost one-to-one onto Spark's pain. Its spine is a single distinction: **workflows** orchestrate LLMs and tools through *predefined code paths*; **agents** dynamically direct their own processes — you choose deterministic code for predictable, well-defined steps and reserve model reasoning for genuinely open-ended ones. The discipline is to start simple and add agentic layers "only when simpler solutions fall short," because frameworks "make it tempting to add complexity when a simpler setup would suffice." Context is finite and subject to "context rot," so system prompts must sit at the "right altitude" — between hardcoding "complex, brittle logic in their prompts" (Spark's regex/canned-response trap, expressed in code instead of prompt) and vagueness; the fix is canonical examples plus just-in-time retrieval, not edge-case laundry-lists. Tools are a first-class reliability surface ("we actually spent more time optimizing our tools than the overall prompt"): they must return **high-signal, actionable errors**, not "opaque error codes or tracebacks," and be poka-yoke'd so the wrong call is structurally hard. Verification is load-bearing: give the agent "a check it can run," "address root causes, not symptoms," "don't suppress the error," and gate hard via deterministic Stop-hooks and **adversarial fresh-context reviewers** rather than trusting "looks done."

The throughline for Spark: push determinism into typed, inspectable, fail-closed control-flow (Governor/gates/hooks) and *out* of the model's prose; make every deterministic shortcut emit traceable **evidence** or an actionable **error**, never silent authority or a masked failure.

**Top transferable lessons.**

| # | Lesson | How it applies to Spark | Maps to |
|---|--------|-------------------------|---------|
| A-1 | Make the workflow-vs-agent boundary explicit; choose code for predictable steps, the model only for open-ended ones. | Spark's hotfixes are deterministic answers smuggled into the *agentic* plane. The cure is to **site** determinism correctly: a route-specific regex deciding execution (`routeFirewall.ts:403-521`) is a workflow-shaped concern in the wrong place. Classify every shortcut as a typed gate (move into the Governor, like the exemplary `runtime_policy.py` argv allowlist) or model reasoning — never an undeclared third thing that owns authority. | `R-02`, `RL-01` |
| A-2 | Default to simplicity; add layers only when simpler code fails. "Many patterns can be implemented in a few lines of code." | 28+ hotfix rounds and the `962/138/118` smell counts are the measurable signature of accreted complexity. The 17,936-line `cli.py` (`cli.py:1-17936`) is the gravity well where every route-by-route hotfix lands. Ratchet the legacy plane so it only ever shrinks. | `R-21`, `R-15` |
| A-3 | Keep system prompts at the "right altitude" — avoid hardcoding brittle logic AND vagueness; replace edge-case lists with canonical examples + just-in-time retrieval. | Names Spark's exact failure mode: route-specific regexes and canned responses *are* brittle hardcoded logic, in code instead of prompt. Give the higher-intelligence planner strong heuristics + canonical good-trajectory examples, not per-route if-else. Mitigates the context-rot that pushes CUAs toward local hotfixes when context fills. | `R-23`, `R-10` |
| A-4 | Tools are a first-class reliability surface; poka-yoke arguments so "it is harder to make mistakes." | Canned-response drift is usually a tool-design failure: a vague/overlapping tool makes the model invent a canned path around it. Invest in the `ToolCallLedger`/capability schemas as the contract surface so the model never needs a regex shim. The CUA `browser/service.py` helper returns should be typed tool results, not ad-hoc dicts the planner must pattern-match. | `R-22` |
| A-5 | Tools must return **high-signal, actionable errors**, not silent nulls — the precise line between a legitimate defensive fallback and a failure-masking one. GOOD: `kernel.py:352-359` returns an explicit deny with `reason_code: invalid_governor_decision`. BAD: `browser/service.py` silently returns `None`/`''`/`{}` on failure. | The audit rule: a fallback is legitimate only if it (a) fails closed and (b) emits a traceable, actionable reason. A fallback that returns empty-but-success-shaped data is a stop-ship failure-mask. Apply directly to `voice_judge.py:63-72` (midpoint coercion) and `system_map.py:1186-1193` (synthesized `unknown` verdict). | `RL-08`, `R-06`, `R-18` |
| A-6 | Give the agent an objective check it can run; "address root causes, not symptoms," "don't suppress the error," "show evidence rather than asserting success." Hooks are deterministic and guarantee the action happens. | The structural cure for "deterministic answers as hotfixes": a hotfix is what an agent reaches for when it has no real verification loop. Wire `ChangeManifestV1`'s failure-evidence + root-cause + live-proof fields as a Stop-hook-style hard gate on every self-evolution and CUA mission — making symptom-masking fixes mechanically un-promotable. | `R-13`, `R-11`, `R-19` |
| A-7 | Use an **adversarial fresh-context reviewer** that sees only the diff and criteria, not the reasoning that produced it; judge on correct *final state*, not a fixed process. | Directly fixes CUA-vs-planner non-cooperation: the planner grades the CUA's proposed action against long-term-solution criteria *before* execution. Because it sees only proposal + criteria, it isn't captured by the CUA's local framing and refutes local hotfixes. | `RL-12`, `R-12`, `R-25` |
| A-8 | Orchestrator-worker: each subagent gets an objective, output format, tool guidance, and clear boundaries, and returns a distilled summary. Reserve multi-agent for parallelizable/context-exceeding work. | Spark's Telegram-CUA + planner is exactly an orchestrator-worker setup failing because the worker lacks clear objective/output-format/boundaries and isn't returning distilled state. Specify each CUA mission as a charter-style envelope and have the CUA report a condensed result the planner synthesizes. | `R-23`, `R-25` |
| A-9 | Agents are non-deterministic between runs; "minor changes cascade into large behavioral changes." Combine adaptability with deterministic safeguards (retry, checkpoints) plus full production tracing. | Justifies *where* determinism belongs: not as shadow-authority answers, but as the safeguard/observability spine **around** the nondeterministic model. Make full tracing a release gate so failures are root-caused once at source, not patched per-route. | `R-17`, `R-19`, `R-20` |
| A-10 | MCP makes capabilities discoverable, self-describing, schema-typed primitives behind a stable boundary — capability lives in declarative schemas the model reads at runtime, never in brittle per-route code. | The architectural antidote to route-specific regexes: expose capabilities as declarative, discoverable, schema-described tools the Governor authorizes uniformly, collapsing the `118 regex / 138 canned` paths into one capability registry. `legacy_turn_intent.py:688` `_matching_vnext_action` already gestures at this shape — formalize it as the single authority surface. | `R-22`, `R-03` |

**Red lines (Anthropic).**

- **Never** let a route-specific regex, keyword match, or canned classifier own execution authority (`RL-01`).
- **Never** let a tool fail silently into a success-shaped empty result (`RL-08`).
- **Never** mark a run "success" on "looks done" without an objective check the agent can run and show evidence for (`R-11`).
- **Never** suppress a symptom in place of the root cause (`R-05`).
- **Never** let memory, pending state, prior missions, or route history promote themselves to authority — they are evidence only.
- **Never** let self-evolution mutate its verifier, benchmark, model config, or authority policy without explicit human approval (`RL-17`).
- **Never** add a new agentic layer when a few lines of deterministic gate code would do.
- **Never** let a legacy detector run as fallback authority/shadow router; it may emit evidence only, with a named retirement owner (`RL-03`).

**Citations (full URLs).**

- Building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Writing effective tools for agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Effective context engineering for AI agents: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- How we built our multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- Claude Code best practices: https://code.claude.com/docs/en/best-practices
- Model Context Protocol — Architecture overview: https://modelcontextprotocol.io/docs/concepts/architecture

---

### 1.4 OSS harness comparison — *control-flow as policy, durable/replayable, verify-loop, typed escalation*

**Summary.** A survey of OSS agent harnesses converges on four moves load-bearing for Spark's pain: **separate control-flow-as-policy from model reasoning**; make runs **durable/replayable**; **fix via a verify-loop** (Aider, SWE-agent); and make **escalation a typed handoff** (OpenAI Agents SDK handoffs, CrewAI Flows, AutoGen termination). SWE-agent's lint-before-apply rejects syntax-error edits at the mutation boundary; Goose's six-type error classification beats a generic "try again"; LangGraph provides the durable interrupt/checkpoint spine. The summary's discipline: confine determinism to one declared surface, and every fix carries failure evidence plus a verifier.

**Top transferable lessons.**

| # | Lesson | How it applies to Spark | Maps to |
|---|--------|-------------------------|---------|
| O-1 | SWE-agent lint-before-apply rejects bad edits and forces a corrective action: validate at the **mutation boundary**. | Reject self-evolution mutations/ledgers at propose/validate with a verifier that emits root-cause feedback, not a downstream fallback (the `962`-fallback risk). | `R-13`, `R-05` |
| O-2 | Goose: a generic "try again" is poor recovery; classifying errors into six types with specific guidance raised recovery rates. | A CUA reaching for a local hotfix *is* the generic try-again loop. Classify failures and route capability-gap/ambiguity to the planner as an interrupt. The `evaluate_swarm_escalation` (`sync.py:1217-1360`) keyword+word-count gate has no failure/ambiguity class at all. | `R-09`, `R-24`, `R-27` |
| O-3 | Aider runs tests+lint after each change, reflects failures back, re-runs: a real verifier in the loop. Not success until the verifier runs green **live**. | Make the reflection loop a promotion gate; a fake-literal/canned pass is forbidden (the fake `cpm` gate noted in prior progression work; `R-11`). | `R-11`, `R-19` |
| O-4 | OpenAI Agents SDK exposes **handoffs as typed tools** with filtered context and reason/priority/summary metadata, one per destination. | Escalate-to-Governor/planner as a typed handoff with a structured reason; the executor never self-authors authority. The Spark CUA has zero typed escalation today. | `RL-12`, `R-25` |
| O-5 | LangGraph checkpoints per node, persists on interrupt/failure, requires idempotent workflows; `interrupt_before` is a durable approval pause. | Use durable interrupt gates, not volatile pending state (the charter already says "pending state expires as context, not authority"); idempotent side-effects allow rollback instead of patch-over. | `R-26`, `R-08` |

**Red lines (OSS comparison).**

- Reject edits failing a pre-apply check at the mutation boundary; never commit-then-patch (`R-13`).
- A breached guardrail halts via tripwire, never a silent fallback (`RL-08`).
- Not success until the verifier runs green **live** (`R-11`).
- Escalation is an explicit typed handoff; the executor self-authors no authority (`RL-12`, `R-25`).
- Deterministic control lives in ONE named surface; scattered route-specific regexes are prohibited (`RL-01`, `R-02`).

**Citations (full URLs).**

- LangGraph Durable Execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- OpenAI Agents SDK Handoffs: https://openai.github.io/openai-agents-python/handoffs/
- OpenAI Agents SDK Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- Aider Lint/Test: https://aider.chat/docs/usage/lint-test.html
- SWE-agent ACI (arXiv 2405.15793v1): https://arxiv.org/pdf/2405.15793v1
- Goose by Block (review): https://www.openaitoolshub.org/en/blog/goose-ai-agent-block-review
- Cline Plan & Act: https://docs.cline.bot/core-workflows/plan-and-act
- CrewAI Features: https://vadim.blog/crewai-unique-features
- AutoGen Termination: https://microsoft.github.io/autogen/stable//user-guide/agentchat-user-guide/tutorial/termination.html
- smolagents: https://huggingface.co/blog/smolagents

---

### 1.5 Hotfix-debt theory — *why a deterministic hotfix ossifies into shadow authority*

**Summary.** The theory names the disease precisely: **a deterministic hotfix smuggles a policy decision into a mechanism site and ossifies into shadow authority.** A real fix targets the *class* at the root cause; a hotfix pins one *symptom-instance*. The references are the classic software-engineering literature — Brinch Hansen/Hydra policy-mechanism separation, Fowler's shotgun surgery, broken-windows tech-debt contagion, Vaughan's normalization of deviance, 5-Whys, testing anti-patterns, and DORA's change-failure-rate. This reference is the *theoretical backbone* under every other one; it explains why the audit's offenders were inevitable given the incentives, and why structural enforcement (not exhortation) is the only fix.

**Top transferable lessons.**

| # | Lesson | How it applies to Spark | Maps to |
|---|--------|-------------------------|---------|
| D-1 | Policy/mechanism separation (Brinch Hansen, Hydra): a hotfix fuses them by letting a regex decide authority, so each case forces editing the mechanism. | The `118 regex / 138 canned / 962 fallback` sites that *decide* are violations of Governor-only intent — demote them to evidence adapters. | `R-02`, `R-03` |
| D-2 | Shotgun surgery (Fowler): scattered special-cases mean one change needs many edits; each branch raises the next change's cost. | 28+ hotfix rounds and the route-regex thicket (`conversationIntent.ts:76 sites`) show fragmented authority. The test: a new route can be added **without** editing a detector. | `R-22`, `R-21` |
| D-3 | Broken-windows tech-debt contagion is causal: high-debt code raises the rate of *new* debt; debt teaches that hotfixes are house style. | A self-evolving harness reads its repo as the norm; `962` fallbacks train the next pass to make more. The `ChangeManifest` gate must forbid new fallback/regex authority. | `R-13`, `R-20` |
| D-4 | Normalization of deviance (Vaughan): a deviation that succeeds resets the baseline; the rule stays on paper but unenforced. | The audit's central finding (`mandate-vs-reality`): the charter forbids route-regex authority, yet `readiness_score()` trusts caller-supplied booleans (`kernel.py:677-744`). Counter with a Stop-Ship Gate that blocks promotion when a legacy detector can still execute. | `RL-15`, `RL-16` |
| D-5 | Fix the **class** not the instance; 5-Whys asks why the *system* allowed it. | A real fix asks why ANY input reaches execution without an envelope. Gate that the root-cause hypothesis names a CLASS, not a symptom-pin. | `R-05` |
| D-6 | A regression test must pin the **root cause**, not lock a symptom; asserting a canned string freezes the workaround. | The `fix-qa-discipline` slice found tests pinning `877 assertIn` literals, not invariants. Assert INVARIANTS (no execute without `AuthorizationDecisionV1`) over a family of inputs. | `R-11`, `R-05` |
| D-7 | DORA change-failure-rate is a stability metric a hotfix culture degrades; hotfix velocity is mistaken for throughput and buys a rising CFR. | Instrument CFR per self-evolving component; a rising-hotfix component is not release-candidate ready. | `R-20` |

**Red lines (hotfix-debt theory).**

- A route-specific regex owning execution authority (`RL-01`).
- A legacy patch/fallback router that bypasses or fights the Governor (`RL-03`).
- Relabeling a blocked/denied action as executed (`RL-08`).
- A chat-only move carrying or executing a proposed action.
- Self-evolution altering its own verifier, benchmark, or authority policy without approval (`RL-17`).
- Memory or pending state overriding fresh user intent.
- A failure-masking fallback that fabricates success instead of surfacing the error (`RL-08`).

**Citations (full URLs).**

- Separation of mechanism and policy (Wikipedia): https://en.wikipedia.org/wiki/Separation_of_mechanism_and_policy
- Policy/Mechanism Separation in Hydra (SOSP 1975): https://swift.sites.cs.wisc.edu/classes/cs736-fa06/papers/hydra-policy-mechanism.pdf
- Shotgun surgery (Wikipedia): https://en.wikipedia.org/wiki/Shotgun_surgery
- Broken Windows Applies to Technical Debt (arXiv 2209.01549): https://arxiv.org/html/2209.01549v3
- Normalization of deviance (Wikipedia): https://en.wikipedia.org/wiki/Normalization_of_deviance
- The power of 5 Whys (Atlassian): https://www.atlassian.com/incident-management/postmortem/5-whys
- Software Testing Anti-patterns (Codepipes): https://blog.codepipes.com/testing/software-testing-antipatterns.html
- Prompt injection defenses (Evidently AI): https://www.evidentlyai.com/llm-guide/prompt-injection-llm
- Securing LLM Agents Against Prompt Injections (2025): https://arxiv.org/pdf/2604.03870
- Four Keys / Change Failure Rate (Google Cloud DORA): https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance

---

### 1.6 CUA orchestration — *bound the worker, force escalation, enforce by observability*

**Summary.** SOTA for computer-use-agent ↔ higher-intelligence orchestration converges on a **supervisor / orchestrator-worker** shape (Anthropic Research, OpenAI Agents SDK, Google ADK): a higher-intelligence **planner** decomposes a goal, hands a CUA worker a scoped sub-task with explicit objective + output format + tool/source guidance + task boundaries, and the CUA acts ONLY inside those boundaries and **escalates** on defined signals rather than improvising a local fix. The central engineering philosophy: the low-level GUI agent is the **least reliable link** (OSWorld ~38% Operator / ~73% Claude on first attempt — ~3 of 4 desktop tasks fail), so reliability comes not from making the CUA smarter but from **bounding its authority and forcing escalation**. Both OpenAI Operator and Anthropic ship confirmation-before-consequential-action, watch mode, take-over for credentials, and a separate **monitor model** that can pause the run. Reflexion-style Actor/Evaluator/Self-Reflection turns a low-confidence step into a *help request* instead of a confident wrong action. Handoffs are first-class and bidirectional (`escalate_to_human()` is an explicit tool). Observability is the enforcement mechanism: full production tracing, OpenTelemetry GenAI spans, a small (~20-task) golden set, scheduled replay of golden traces against prod with deterministic fixtures, and a 3-layer eval stack.

The recurring lesson against Spark's pain #2: Spark's `RUNTIME_CHARTER` already encodes the right spine, but the actual CUA path (`browser/service.py`) is a thin payload-builder over an external `browser-use` CLI — **no in-process planner loop, no escalation, no retry ceiling, no confidence signal** — so the charter's rules are unenforced exactly where pain #2 lives. This reference is the direct source for the entirety of `03_CUA_ESCALATION_PROTOCOL.md`.

**Top transferable lessons.**

| # | Lesson | How it applies to Spark | Maps to |
|---|--------|-------------------------|---------|
| C-1 | Scope every CUA sub-task with explicit objective, output format, tool/source guidance, and HARD task boundaries; the boundary is what makes "out of scope → escalate" a well-defined event. | The Telegram-desktop CUA must receive a `ChangeManifest`-style task envelope (objective + end-state + allowed surfaces + "do NOT" list). When it hits anything outside the envelope it has a crisp boundary-violation signal to escalate on, instead of improvising a click sequence (a local hotfix). | `R-23` |
| C-2 | Route the CUA to **ask for confirmation** before any consequential/irreversible action; watch mode on sensitive surfaces; take-over for credentials; a separate monitor model that can pause. The CUA never self-authorizes high-stakes moves. | Maps 1:1 onto the charter's Risk Tiers: any CUA step that is medium+ MUST emit an `interrupt` verdict to the Governor/human, never an `allow` the CUA grants itself. A deterministic fallback that "just submits anyway" is exactly the self-authorized high-stakes action both OpenAI and Anthropic forbid. | `R-26`, `RL-04`, `R-28` |
| C-3 | Treat a low-confidence step as a **help request** that triggers re-verification/reflection/escalation. Reflexion puts an explicit Evaluator between acting and committing. | The CUA loop needs an Evaluator after each tool result (screenshot diff vs expected end-state). Below a confidence floor or after N stalled steps, STOP and escalate. `browser/service.py` has no confidence/retry-ceiling/stall detector — that absence is precisely why CUAs "drift into local hotfixes." | `R-24` |
| C-4 | Make handoffs first-class and bidirectional: `escalate_to_planner()` / `escalate_to_human()` are explicit tools; the **supervisor** (not the worker) decides escalate/retry/move-on. | Spark's CUA should expose `escalate_to_planner(reason, evidence, partial_state)` that returns control with the trace. This realizes "surfaces submit evidence, they do not own authority" — escalation is the CUA emitting evidence upward; the planner owns the next move. | `R-25`, `R-27` |
| C-5 | Scale effort from the **orchestrator**; the planner owns the long-horizon plan (persisted to external memory), workers own bounded execution. | The long-term-fix-vs-hotfix tension is resolved by *altitude*: the CUA is deliberately denied long-horizon authority, so it structurally cannot choose a quick local patch that compounds. | `R-25`, `R-23` |
| C-6 | Model graceful degradation explicitly: tell the agent a tool is failing and let it adapt; checkpoint/resume so a failure doesn't restart the run. Failure and rollback are first-class. | The principled alternative to the `962` fallbacks: a legitimate degradation surfaces the failure and adapts; a failure-masking fallback swallows it and returns a canned "success." A degraded/failed CUA step is recorded as failure+escalation, never a synthesized OK. | `RL-08`, `R-27` |
| C-7 | Reliability is enforced by **observability**: full tracing, OpenTelemetry GenAI spans, a ~20-task golden set, scheduled replay of golden traces with deterministic fixtures, a 3-layer eval stack. | Deterministic checks belong in the eval/verifier lane, NOT as runtime execution-authority regexes. A golden-trace replay would have caught each of the 28 `cli.py` hotfix rounds as a regression instead of accreting `r1..r28`. | `R-19`, `R-17` |
| C-8 | Assume the GUI layer is the unreliable link (~3 of 4 desktop tasks fail first-attempt); benchmark success ≠ production reliability. | Set the CUA's default authority to read/low and require interrupt for medium+; budget for a high baseline failure rate so escalation is the **common path**. The goal is not a CUA that rarely needs the planner, but one that escalates cleanly and often. | `R-26`, `R-24` |

**Red lines (CUA orchestration).**

- The CUA must **never** self-authorize a consequential/irreversible action — those require confirmation/human approval or an `interrupt` verdict, never a self-granted `allow` (`RL-04`, `R-26`).
- A being-stuck / low-confidence / out-of-scope CUA must **never** resolve itself with a local deterministic hotfix (`RL-01`, `RL-13`).
- A degraded or failed CUA step must **never** be recorded as success (`RL-08`, `R-27`).
- The CUA worker must **never** own long-horizon strategy or the escalate/retry/abort decision — that belongs to the planner/Governor (`R-25`).
- Deterministic checks must **never** live in the runtime execution-authority path as shadow routers; they belong in the verifier/eval/replay lane (`RL-11`, `R-19`).
- Self-evolution must **never** mutate the verifier, golden tasks, model config, or authority policy without explicit human approval (`RL-17`).

**Citations (full URLs).**

- How we built our multi-agent research system — Anthropic: https://www.anthropic.com/engineering/multi-agent-research-system
- Orchestrating Agents: Routines and Handoffs — OpenAI Cookbook: https://developers.openai.com/cookbook/examples/orchestrating_agents
- Operator — OpenAI Help Center (watch mode, take-over, confirmations): https://help.openai.com/en/articles/10421097
- Computer-Using Agent — OpenAI: https://openai.com/index/computer-using-agent/
- Computer-Use Agents, Explained (OSWorld reliability limits): https://www.siliconsnark.com/computer-use-agents-explained-why-openai-anthropic-and-perplexity-want-to-operate-your-laptop/
- Best Computer Use Agent Comparison 2025 (OSWorld 38% vs 73%): https://coasty.ai/blog/computer-use-agent-comparison-best-ai-2025
- Reflective Confidence (arXiv 2512.18605): https://arxiv.org/html/2512.18605
- CRITIC: LLMs Can Self-Correct with Tool-Interactive Critiquing (arXiv 2305.11738): https://arxiv.org/pdf/2305.11738
- Swarm vs. Supervisor: Multi-Agent Architecture Guide — Augment Code: https://www.augmentcode.com/guides/swarm-vs-supervisor
- Agent Observability 2026: Evals, Traces, Cost Guide — Digital Applied: https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide
- AI Agent Observability and Tracing — Arize: https://arize.com/ai-agents/agent-observability/
- Multi-Agent Orchestration Patterns — Prateek Sharma: https://www.prateek-sharma.com/blog/multi-agent-orchestration-patterns/

---

## 2. Comparison matrix

How each reference treats the nine axes that matter most for Spark's two pains, with **Spark-today** filled honestly from the audit and **Spark-target** stating the discipline-layer destination. Cell IDs in the Spark columns cite the offender or rule that grounds the claim.

| Axis | Hermes | OpenClaw | Anthropic doctrine | **Spark-today** | **Spark-target** |
|------|--------|----------|--------------------|-----------------|------------------|
| **Single authority spine / Governor-as-origin** | One `check_all_command_guards` funnel; backends can't bypass | "Access control before intelligence"; ordered layers before model runs | Workflow/agent split; capability behind one MCP authorization surface | **Absent at the edge.** CLI owns a *local* policy copy; "Governor" is just an HMAC key (`cli.py:69-72`). Telegram regex decides first, Governor bolted on as validator (`telegramActionAuthority.ts:79-102`). Bridge *reconstructs* a Governor decision from its own verdict (`bridge_authority.py:121-222`). | Governor is the **origin** of authority (`RL-02`, `R-03`); surfaces hold no local policy copy |
| **Policy-as-data + separate enforcement** | `DANGEROUS_PATTERNS` data vs approval-callback mechanism; #5528 → config-driven | `openclaw.json` data; enforcement is separate code ("policy does not enforce at runtime") | Declarative schemas the model reads; deterministic Stop-hooks enforce | **Inverted.** Enforcement masquerades as scattered policy — a `~460`-line if/elif ladder is the decision (`approval.py:137-597`); the memory rescue plane *is* the answer layer (`providers.py:1828-1830`) | New policy = a declarative manifest row evaluated by ONE engine (`R-16`); enforcement in one `kernel.py` chokepoint |
| **Fail-closed defaults** | `check_fn` exception ⇒ unavailable; timeout ⇒ decline; never approve | Unresolved secrets fail closed; auth required; SSRF blocked by default | Tools return actionable errors, never silent nulls | **Mixed.** Good: non-interactive ⇒ `blocked` (`approval.py:121`); `kernel.py:352-359` denies on bad decision. Bad: `voice_judge.py:63-72` returns midpoint `5`; `system_map.py:1186-1193` synthesizes `unknown`; `browser/service.py` returns `None`/`''`/`{}` | A failure is never success-shaped (`RL-08`); fallback legitimate only if it fails closed + emits a traceable reason (`R-06`) |
| **Security-disabling flags frozen & greppable** | `_YOLO_MODE_FROZEN` read once at import; hardline floor unbypassable | `dangerously`-prefixed flags; greppable; rate-limited config writes | (n/a — emphasis on hooks/verification) | **Hot & silent.** `SPARK_APPROVAL_ENFORCE=0` disables the only gate, re-readable at runtime (`cli.py:10976-10977`); `962/138/28/104` smell markers are silent and uncounted | Toggle frozen at process start (`RL-06`); greppable `unsafe_`/`maskingFallback_` naming gated by a counting lint |
| **LLM-is-input-not-authority** | "Only boundary is the OS"; heuristics catch cooperative mistakes only | "The model is never a security boundary" | "Hardcoding brittle logic" is the named anti-pattern | **Violated at scale.** ~647 regex-authority sites across `routeFirewall.ts`/`telegramIntentGate.ts`/`buildIntent.ts` hold route selection AND veto/grant; `~250+` literal answer-key branches in `domain-chip-memory` | A regex may NARROW (veto), never GRANT (`R-02`); a route detector is an evidence adapter only (`RL-01`) |
| **Typed escalation / handoff** | `_smart_approve` returns approve/deny/**escalate**; aux-LLM treats input as untrusted | (escalation via human approval gates) | Adversarial fresh-context reviewer; orchestrator-worker handoff | **None.** Zero automatic failure→escalation; the only path is user-typed `/swarm evaluate` gated by keyword+word-count, default `escalate=False` (`sync.py:1217-1360`). The escalation knob only degrades DOWN to a weaker fallback planner (`local.py:89-116`) | Escalation is a typed, first-class, frequent handoff to the planner (`R-25`); reviewer has a first-class escalate verdict (`RL-12`) |
| **Eval integrity / no benchmark overfit** | (not the focus) | (not the focus) | Held-out gating; "show evidence not assert success"; root-cause not symptom | **The epicenter.** `domain-chip-memory` is a benchmark answer-key plane: `'alice'/'bob'` personas (`memory_queries.py:75-78`), `'a sunset with a palm tree'`/`'Liberal'` (`provider_rescue_identity.py:6-173`), `{'stamford':'Connecticut'}` (`memory_factoid_answers.py:10-90`), run AHEAD of real extraction | No literals for names/facts/dates (`R-10`); eval gains gated on a HELD-OUT set (`R-11`); deterministic answer-keys never in the live path (`RL-10`, `RL-11`) |
| **God-file discipline** | (modular; backends are leaf files) | (modular gateway) | "Default to simplicity; a few lines of code"; prune ruthlessly | **Unenforced redline.** `cli.py` = 17,936 lines (`cli.py:1-17936`), `index.ts` = 10,152 (`index.ts:1-10152`), both past a written 3,000-line cap that named them; 5 planned extractions never made | No file >3000 lines without owner+refactor plan, CI-enforced (`R-21`); collapse competing detectors into one (`R-22`) |
| **Observability / replay** | (tracing via logs) | (advisory record as feedback) | Full production tracing as a release gate; outcome-based eval | **Self-attesting, not derived.** `readiness_score()` trusts caller-supplied gate booleans (`kernel.py:677-744`); `legacy_authority_demoted=True` hardcoded per decision (`kernel.py:316-322`); inventory is a hand list omitting the two biggest planes (`legacy_authority_inventory.py:81-200`) | Every step inspectable or the run is not ready (`R-17`); golden-trace replay in the eval lane (`R-19`); gates derived from artifacts, never trusted booleans (`RL-15`, `RL-16`) |

---

## 3. Top 12 borrowed moves, ranked by leverage for Spark

Ranked by how much of the audit each move neutralizes per unit of work. Each names the external source, the Spark wave/offender it fixes, and the rule it operationalizes.

1. **Derive readiness gates from artifacts, never trust caller booleans** (OpenClaw OC-7 + Anthropic A-9 + Vaughan D-4). The single highest-leverage move: `readiness_score()` trusting `zero_high_agency_legacy_local_gates` / `governance_rulesets_proven` as supplied booleans (`kernel.py:677-744`) is the enforcement hole that lets *every other offender pass promotion*. Make these derived from a `LegacyAuthorityInventory` reconciliation + a governance run. → `RL-15`, `RL-16`, `R-17`.

2. **Demote every route regex to an evidence adapter that can only NARROW** (Hermes H-1 + hotfix-debt D-1 + Anthropic A-1). Kills the headline Stop-Ship violation across `routeFirewall.ts:403-521`, `telegramActionAuthority.ts:79-102`, `approval.py:137-597`, and `qa-evidence-lane/routing.py:5-38`. The regex submits evidence; the Governor owns the verdict. → `RL-01`, `RL-02`, `R-02`.

3. **Make the Governor the origin, not a wrapper; delete the circular self-verification** (Hermes H-2 + OpenClaw OC-1). `bridge_authority.py:121-222` reconstructs a Governor decision from its own verdict; `telegramActionAuthority.ts:111-118` verifies a decision it authored. The surface must consume a decision it did *not* author. → `RL-02`, `RL-03`, `R-03`.

4. **Retire the `domain-chip-memory` answer-key plane and gate eval gains on a held-out set** (Anthropic A-6 + hotfix-debt D-6). The `~250+` literal branches (`provider_rescue_identity.py:6-173`, `memory_queries.py:75-78`, `memory_factoid_answers.py:10-90`, `provider_temporal_rescue.py:132-238`) running ahead of extraction (`providers.py:1828-1830`) are pain #1 at maximum scale. Delete the rescue plane; let the model extract; detect overfit with held-out questions. → `RL-10`, `RL-11`, `R-10`, `R-11`.

5. **Wire automatic failure→escalation into the CUA loop with an Evaluator and a typed handoff** (CUA C-3/C-4 + OSS O-2/O-4). The architectural root of pain #2: `evaluate_swarm_escalation` (`sync.py:1217-1360`) has no failure/ambiguity trigger and only the user can invoke it. Add an Evaluator after each tool result; below a confidence floor, STOP and `escalate_to_planner()`. → `R-24`, `R-25`, `R-27`.

6. **Freeze the security-disabling toggle at import and define a hardline floor** (Hermes H-4 + OpenClaw OC-3). `SPARK_APPROVAL_ENFORCE=0` (`cli.py:10976-10977`) is a runtime-re-readable kill switch over the only gate. Freeze it; forbid self-evolution from crossing the floor (can't disable the manifest gate, self-grant a tier, or delete audit). → `RL-06`, `RL-17`, `R-14`.

7. **Bind authority to the parsed/typed action, not re-tokenized argv** (OpenClaw OC-1 + Anthropic A-1). `main()` re-derives intent from `sys.argv` with its own tokenizer beside the real argparse dispatch (`cli.py:17925-17932`) — two routers that can disagree. Bind the Governor to the typed action. → `R-01`, `RL-02`.

8. **Add a CI god-file gate and execute the five named extractions** (Anthropic A-2 + Fowler D-2). `cli.py:1-17936` and `index.ts:1-10152` blow past a 3,000-line cap that already named them. A line-count gate that fails the build (no owner+refactor-plan token) stops the gravity well that absorbs every route-by-route hotfix. → `R-21`, `R-22`.

9. **Replace the hand-maintained legacy inventory with a source scanner reconciled in CI** (OpenClaw OC-7 + Vaughan D-4). The inventory that *proves* retirement is a self-attested array omitting `routeFirewall.ts` and `naturalRouteDecision.ts` (`legacy_authority_inventory.py:81-200`; also `legacyAuthorityInventory.ts:1-289`). Compute it from an AST/regex scan; fail when a verdict-returning plane is undeclared. → `RL-16`, `R-16`.

10. **Make every fallback fail closed and traceable; ban the success-shaped failure** (Hermes H-7 + Anthropic A-5 + CUA C-6). One audit rule converts a class of offenders: `voice_judge.py:63-72` (midpoint `5`), `system_map.py:1186-1193` (synthesized `unknown`), `routeArbiter.ts:188-205` (hardcoded `arbiter_failed` swallowed), `errorExplain.ts:66-309` ("ask me again"). A failure must surface as deny/degrade with a reason code. → `RL-08`, `R-06`, `R-18`.

11. **Map structured error CODES to remediation in one registry; never pattern-match a rendered message** (Hermes H-9 + OpenClaw OC-6). `is_dirty_update_failure()` (`cli.py:886-892`) and `user_safe_startup_detail()` (`cli.py:14933-14939`) key control flow / canned replies on English error substrings. Emit typed codes upstream; branch on the type. → `R-09`, `RL-09`, `R-07`.

12. **Hard-refuse self-evolution writes to the authority/policy/security layer via an explicit field allowlist** (OpenClaw OC-3/OC-8 + Anthropic red line). `PROTECTED_EVOLUTION_COMPONENTS` (`kernel.py:81`) is the right shape but the protected set is not proven to include the telegram route tables — a self-evolution run could edit the regex routing tables as "ordinary code" and alter authority without tripping approval. Add the authority-bearing files to the protected set; refuse capability/guard *removal* unless explicitly flagged. → `RL-14`, `RL-17`, `RL-15`, `R-13`, `R-14`.

---

## 4. Consolidated citation list

Every external URL referenced above, deduped. These are the only sources the discipline layer treats as authoritative external evidence; no other URLs may be cited as "research" without being added here first.

**Hermes Agent (NousResearch)**
- https://github.com/NousResearch/hermes-agent
- https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md
- https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py
- https://github.com/NousResearch/hermes-agent/blob/main/tools/environments/base.py
- https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval
- https://hermes-agent.nousresearch.com/docs/developer-guide/architecture
- https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime
- https://github.com/NousResearch/hermes-agent/issues/16475
- https://github.com/NousResearch/hermes-agent/issues/5528
- https://hermes-agent.nousresearch.com/docs/user-guide/security

**OpenClaw**
- https://docs.openclaw.ai/gateway/security
- https://github.com/openclaw/openclaw/blob/main/docs/gateway/security/index.md
- https://docs.openclaw.ai/tools/exec-approvals
- https://docs.openclaw.ai/cli/policy
- https://docs.openclaw.ai/cli/approvals
- https://docs.openclaw.ai/gateway/security/secure-file-operations
- https://github.com/openclaw/openclaw/security/advisories/GHSA-cv7m-c9jx-vg7q
- https://github.com/openclaw/openclaw/security/advisories/GHSA-m3mh-3mpg-37hw
- https://www.vulncheck.com/advisories/openclaw-gateway-config-mutation-guard-bypass-via-agent-tool-access
- https://github.com/openclaw/openclaw/security/advisories

**Anthropic / Claude SOTA**
- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/multi-agent-research-system
- https://code.claude.com/docs/en/best-practices
- https://modelcontextprotocol.io/docs/concepts/architecture

**OSS harness comparison**
- https://docs.langchain.com/oss/python/langgraph/durable-execution
- https://openai.github.io/openai-agents-python/handoffs/
- https://openai.github.io/openai-agents-python/guardrails/
- https://aider.chat/docs/usage/lint-test.html
- https://arxiv.org/pdf/2405.15793v1
- https://www.openaitoolshub.org/en/blog/goose-ai-agent-block-review
- https://docs.cline.bot/core-workflows/plan-and-act
- https://vadim.blog/crewai-unique-features
- https://microsoft.github.io/autogen/stable//user-guide/agentchat-user-guide/tutorial/termination.html
- https://huggingface.co/blog/smolagents

**Hotfix-debt theory**
- https://en.wikipedia.org/wiki/Separation_of_mechanism_and_policy
- https://swift.sites.cs.wisc.edu/classes/cs736-fa06/papers/hydra-policy-mechanism.pdf
- https://en.wikipedia.org/wiki/Shotgun_surgery
- https://arxiv.org/html/2209.01549v3
- https://en.wikipedia.org/wiki/Normalization_of_deviance
- https://www.atlassian.com/incident-management/postmortem/5-whys
- https://blog.codepipes.com/testing/software-testing-antipatterns.html
- https://www.evidentlyai.com/llm-guide/prompt-injection-llm
- https://arxiv.org/pdf/2604.03870
- https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance

**CUA orchestration**
- https://www.anthropic.com/engineering/multi-agent-research-system *(shared with Anthropic SOTA)*
- https://developers.openai.com/cookbook/examples/orchestrating_agents
- https://help.openai.com/en/articles/10421097
- https://openai.com/index/computer-using-agent/
- https://www.siliconsnark.com/computer-use-agents-explained-why-openai-anthropic-and-perplexity-want-to-operate-your-laptop/
- https://coasty.ai/blog/computer-use-agent-comparison-best-ai-2025
- https://arxiv.org/html/2512.18605
- https://arxiv.org/pdf/2305.11738
- https://www.augmentcode.com/guides/swarm-vs-supervisor
- https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide
- https://arize.com/ai-agents/agent-observability/
- https://www.prateek-sharma.com/blog/multi-agent-orchestration-patterns/

---

## 5. How to use this document

- When you write a fix, cite the **external move** it borrows and the **rule** it satisfies — this document is the bridge between the two. `02_REAL_FIX_PLAYBOOK.md` requires it.
- When a reviewer challenges a rule as arbitrary, the answer is here: every Red Line and Rule in `01_RULESET.md` traces to a system that shipped it or a CVE that proved its absence.
- When a new harness or paper enters the conversation, add its URL to Section 4 **before** citing it elsewhere, so the corpus stays closed and auditable.
- The matrix in Section 2 is the scorecard. Spark-target is reached when every Spark-today cell can be honestly rewritten to match the external columns — verified by the checkers catalogued in `01_RULESET.md §5`, not by assertion.

See also: `00_README.md` (the map of this doc set), `01_RULESET.md` (the canonical IDs), `02_REAL_FIX_PLAYBOOK.md` (fix shape), `03_CUA_ESCALATION_PROTOCOL.md` (escalation, sourced almost entirely from §1.6), and `04_AUDIT_FINDINGS_AND_BACKLOG.md` (the offender backlog these moves are aimed at).
