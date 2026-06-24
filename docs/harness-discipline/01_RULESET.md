# Spark Harness Discipline: The Ruleset

> Source of truth: `docs/harness-discipline/`. Grounded in the 2026-06-24 Spark harness audit (51 offenders) + Hermes/OpenClaw/Anthropic/OSS research (51 lessons).

This is the **anchor document**. Every sibling doc cites the IDs minted here. The Red Lines are `RL-01`..`RL-21`; the Rules are `R-01`..`R-28`. When `02_REAL_FIX_PLAYBOOK.md`, `03_CUA_ESCALATION_PROTOCOL.md`, `04_AUDIT_FINDINGS_AND_BACKLOG.md`, or `05_EXTERNAL_HARNESS_LESSONS.md` reference an `RL-` or `R-`, they mean the definition here. If a definition changes, it changes here first.

---

## 1. Preamble — why this document exists

### 1.1 The founder's two pains

Spark exists to evolve itself. That makes two specific failure modes catastrophic rather than annoying, because the system reads its own repository as the norm and reproduces it:

1. **Deterministic answers committed as hotfixes that became shadow authority.** A specific failing case (a misrouted Telegram message, a benchmark question, an OS-specific git error) gets "fixed" by a route-specific regex, a hard-coded fallback, or a canned reply. The shortcut works for that one case, ships, and then *owns the decision* for every future case that resembles it. As the repos grow, these shortcuts compound into a parallel, unaccountable authority plane that fights the real one.

2. **Telegram-desktop CUAs that failed to cooperate with a higher-intelligence planner and drifted into local hotfixes.** When the computer-use agent got stuck, hit ambiguity, or fell out of scope, it had no mechanism to hand the problem *up*. So it improvised locally — exactly the behavior that mints pain #1.

These are not hypotheticals. The audit found **51 offenders** that are these two pains realized in committed code.

### 1.2 The visible r28 hotfix treadmill

The clearest fingerprint of pain #1 is in `spark-cli` itself. Its branch tip is literally `hotfix/r28-longpath-guard` with four same-day installer re-tags (`/Users/alchemistab/.spark/tools/spark-cli/.git`). Each round patched one more environment-specific edge of a guard that was never a semantic model: shallow-clone ancestry, Windows long paths, read-only files (`cli.py:823-855`). Twenty-eight rounds, no exit from the treadmill — because the dominant remediation move is *add one more branch*, and nothing in CI says "stop, find the root cause."

The same gravity well shows in the god-files: `cli.py` is **17,936 lines** (`cli.py:1-17936`) and `index.ts` is **10,486 lines** (`index.ts:1-10486`), both blowing past a written 3,000-line hard cap that *already named them*, because the maintainability redline has no CI gate.

### 1.3 The central finding: mandate-by-prose

The Spark governance corpus is unusually mature **on paper**. The `RUNTIME_CHARTER.md` already forbids every anti-pattern the founder fears:

- "a route-specific regex owns execution authority" — Stop-Ship Gate (`RUNTIME_CHARTER.md:170`).
- "The Governor is the only runtime component that may promote evidence" (`RUNTIME_CHARTER.md:21`).
- "a legacy patch, fallback router, or adapter-local detector can bypass or fight the Governor" — Stop-Ship Gate (`RUNTIME_CHARTER.md:171`).
- Legacy Plane Retirement: detectors "can only emit evidence … cannot … finalize tool ledgers by itself" (`RUNTIME_CHARTER.md:25-42`).
- Self-evolution "cannot mutate verifier logic, benchmark cases, model config, or authority policy without explicit human approval" (`RUNTIME_CHARTER.md:150`).

**The vocabulary is correct. The enforcement is honesty.** The audit's single most important finding (the `mandate-vs-reality` slice) is that these rules are checked by *hand-curated lists and caller-supplied booleans*, not by code:

- `kernel.readiness_score()` accepts `zero_high_agency_legacy_local_gates`, `governance_rulesets_proven`, and `performance_budget_proven` as **caller-supplied booleans it trusts** (`kernel.py:677-744`). The function never scans code; it records whatever the caller asserts.
- The `legacy_authority_inventory` that is supposed to *prove* retirement is a **hand-maintained array that omits the two largest live planes** (`routeFirewall.ts`, `naturalRouteDecision.ts`) (`legacy_authority_inventory.py:81-200`). A plane omitted from the list is invisible to the readiness gate.

This is exactly **normalization of deviance** (Vaughan): a rule that lives on paper but is never mechanically enforced gets quietly worked around until the workaround is the baseline (`hotfix-debt-theory`, https://en.wikipedia.org/wiki/Normalization_of_deviance). And **broken-windows tech-debt contagion** makes it self-propagating in a self-evolving harness: high-debt code raises the rate of *new* debt because the repo teaches the next pass that hotfixes are house style (`hotfix-debt-theory`, https://arxiv.org/html/2209.01549v3).

### 1.4 Thesis

> **The charter names the rules. This ruleset makes them enforceable.**

We do not restate principles that are already well written. We **EXTEND** the charter by binding every rule to a **mechanism**: a greppable lint, a CI gate, a unit invariant, a schema validation, a human-approval gate, or an observability assertion. The standard, borrowed from Hermes, is blunt:

> A heuristic that produces a terminal deterministic response is, by definition, masquerading as the boundary. Name the real authority boundary and refuse to let a heuristic impersonate it (`Hermes`, https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md).

Every rule below carries a checker. If a rule cannot be checked by a machine, it is not done — it is a comment. Section 5 maps every Red Line and Rule to a checker type and its current status (`exists` / `partial` / `missing`), so the gap from "rules on paper" to "rules enforced" is itself auditable.

This ruleset does not contradict the charter at any point. It adds the **fix-discipline layer** the charter assumes but never specifies: how a fix must be shaped, what a fallback must do to be legitimate, and how the CUA must escalate instead of hotfixing (detailed in `03_CUA_ESCALATION_PROTOCOL.md`).

---

## 2. Prime Directives

Seven axioms. Everything below is a corollary of one of these. They are derived from the evidence, not invented.

**PD-1 — The model, the regex, the keyword is INPUT, never authority.**
A pattern match may *submit evidence*; it may never *own the verdict*. The only real boundary against an adversarial or drifting model is a structural one — the OS, a sandbox, the Governor's typed gate — not a string scan (`Hermes`, https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md; `OpenClaw`, https://docs.openclaw.ai/gateway/security).

**PD-2 — One authority spine. The Governor is the ORIGIN, not a downstream wrapper.**
There is exactly one place that promotes evidence into an executable envelope. Authority flows *out* of it. A regex that decides first, with the Governor bolted on to validate what the regex already permitted, is a shadow plane wearing the Governor's name (`telegramActionAuthority.ts:79-102`; `RUNTIME_CHARTER.md:21`).

**PD-3 — Policy is DATA; it is enforced by a SEPARATE mechanism that FAILS CLOSED.**
Declarative, auditable policy (risk tiers, allowlists, manifests) is distinct from the code chokepoint that re-checks every action. A "policy" that only reports drift is not enforcement; enforcement that masquerades as scattered policy (138 canned replies as the decision layer) is the inverse failure (`OpenClaw`, https://docs.openclaw.ai/cli/policy; Brinch Hansen/Hydra policy-mechanism separation, https://en.wikipedia.org/wiki/Separation_of_mechanism_and_policy).

**PD-4 — A real fix targets the CLASS at the root cause; it never pins a symptom.**
The root-cause question is "why did the *system* allow any input to reach this state?" not "how do I silence this one instance?" A regression test pins the invariant over a family of inputs, never a canned string (`hotfix-debt-theory`, https://www.atlassian.com/incident-management/postmortem/5-whys, https://blog.codepipes.com/testing/software-testing-antipatterns.html).

**PD-5 — Failure SURFACES; it never becomes fake success.**
A legitimate fallback fails closed and emits a traceable, actionable reason. A fallback that returns empty-but-success-shaped data, a synthesized "unknown" verdict, or a canned reassurance is a stop-ship defect (`Anthropic`, https://www.anthropic.com/engineering/writing-tools-for-agents; `Hermes`, https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime).

**PD-6 — The higher intelligence must be able to WIN. No permanently-shadowed planner.**
A higher-intelligence check (LLM arbiter, planner) that is structurally barred from ever becoming authority is the determinism trap as architecture. Escalation to it is a first-class, typed, *frequent* event — not a last resort, and never a verdict the executor can self-author (`cua-orchestration`, https://developers.openai.com/cookbook/examples/orchestrating_agents; `oss-harness-comparison`, https://openai.github.io/openai-agents-python/handoffs/).

**PD-7 — Eval integrity: never hardcode answers to pass your own benchmark, and the grader is never writable by the graded.**
Benchmark-string answer keys baked into the live answering path are shadow authority at maximum scale. Self-evolution that can edit its verifier, golden set, or authority policy to make a failing run pass is the deepest failure-mask (`provider_rescue_identity.py:6-173`; `RUNTIME_CHARTER.md:150`; `OpenClaw` CVE-2026-45001, https://www.vulncheck.com/advisories/openclaw-gateway-config-mutation-guard-bypass-via-agent-tool-access).

---

## 3. RED LINES (never cross)

A Red Line is a **stop-ship condition**. If any of these is true, the surface does not promote — period. Each synthesizes the charter's Stop-Ship Gates, the six research `red_lines` sets, and the audit. Each names the Spark offender(s) that currently violate it (exact `file:line`) and the **detection method** that must catch it in CI.

> Charter Stop-Ship Gates (`RUNTIME_CHARTER.md:167-178`) are the substrate. Where a Red Line below extends a charter gate, that is intentional: the charter says *what*; the Red Line adds *how it is detected*.

> **Charter reconciliation — the machine-origin approval exception (FOUNDER DECISION REQUIRED).** `RUNTIME_CHARTER.md:96` anticipates that a *future* policy may grant "a narrowly scoped machine-origin exception" to the human-approval requirement. RL-04, RL-13, and R-26 are written as absolutes because **no such policy exists yet** — and for a self-evolving harness that runs unattended (cron, self-evolution, CUA loops) an undefined exception is an open authority hole. Until a narrowly-scoped autonomous-approval policy is *designed, gated, and added to this document*, the autonomous resolution of an uncertain high/critical action is **halt-and-queue for human review (R-08)** — never a self-granted allow. This **defers** the charter's exception; it does not delete it. Decide explicitly: either retire the exception (amend the charter) or specify the narrow autonomous-approval branch here — what may self-approve, under what proof, with what rollback and mandatory post-hoc human audit.

### RL-01 — A route-specific regex / keyword / canned classifier must never own execution authority.
**Why:** This is the charter's headline Stop-Ship Gate (`RUNTIME_CHARTER.md:170`) and the empirically proven bypass farm of every adjacent system (`OpenClaw` advisory record, https://github.com/openclaw/openclaw/security/advisories). A pattern table cannot see semantics; it drifts; each new case is another branch.
**Spark violates it at:** `approval.py:137-597` (a ~460-line if/elif ladder that is the *entire* CLI execution-authority decision); `routeFirewall.ts:403-521` (`evaluateDeterministicRoute` returns `allow:boolean` consumed as authority); `conversationIntent.ts` (76 regex sites); `routing.py:5-38` (qa-evidence-lane `should_activate` flips activation from raw-text regex).
**Detection:** AST/grep authority-site detector — flag any function returning `allow`/`deny`/`route`/a terminal answer derived from regex/keyword input that is consumed as a precondition of execution. *Status: missing.*

### RL-02 — The Governor must be the origin of authority, never a wrapper around a prior regex verdict.
**Why:** PD-2. If a regex `allow` is a *necessary conjunct* of the final decision, the Governor can only narrow what the regex already permitted and can never originate authority — the charter-forbidden "legacy patch can fight/bypass the Governor" (`RUNTIME_CHARTER.md:171`), laundered to look governed.
**Spark violates it at:** `telegramActionAuthority.ts:79-102` (`preliminaryAllow = routeVerdict.allow && …`; reason codes even surface `route_firewall:<reason>`); `bridge_authority.py:121-222` (`build_governor_decision_from_bridge_authority` fabricates a `governor-decision-v1` from the bridge's own verdict, then verifies against itself — bypass by impersonation).
**Detection:** Unit invariant test — assert the final allow equals `governorVerification.allowed` with no upstream regex `allow` in the conjunction; AST check that no `governor-decision-v1` is constructed in the same module that authored the authorization it certifies. *Status: missing.*

### RL-03 — A legacy detector must never finalize a tool ledger or authorization by itself.
**Why:** Legacy Plane Retirement (`RUNTIME_CHARTER.md:38`): a retained detector "cannot … finalize tool ledgers by itself." A detector that mints `allow` + ledger is a parallel authority.
**Spark violates it at:** `legacy_turn_intent.py:595-665` (`authorize_legacy_tool_call` sets `authority_state='executable'` itself, calls `kernel.authorize()`, returns a finalized `allow` + ledger).
**Detection:** AST detector — any module dispositioned `evidence_adapter` that calls `record_tool_call` / returns an `AuthorizationDecision` fails the build. Reconcile against `_validate_legacy_plane_disposition` (`kernel.py:1615`). *Status: partial (schema rule exists, not wired to a scan).*

### RL-04 — Approval evidence for high/critical actions must come from an out-of-band human signal, never be synthesized.
**Why:** "High and critical actions require explicit approval" (`RUNTIME_CHARTER.md:96`). Fabricating the human-confirmation reference from a confidence heuristic masks the very gate it claims to honor.
**Spark violates it at:** `legacy_turn_intent.py:627-638` (fabricates a `human_confirmation` `approval_ref` from `selected_intent.confidence=='explicit'`).
**Detection:** Schema validation — `human_confirmation` evidence_refs must carry an out-of-band provenance token (operator/CLI/Telegram approval id); reject refs whose source is an in-process confidence value. *Status: missing.*

### RL-05 — `requires_approval` must mean *enforced*. No second filter set may silently drop an enforced class.
**Why:** Two sources of truth that disagree is a silent authority gap — the "deterministic answer masks the real decision" smell.
**Spark violates it at:** `cli.py:10963-11003` (`APPROVAL_ENFORCED_ACTION_CLASSES` omits `high_cost_execution`, so `spark verify --deep` computes `requires_approval=True` at `approval.py:586-595` yet is never prompted or blocked).
**Detection:** Unit invariant test — for every `ApprovalClass` with `requires_approval=True`, assert it is either enforced or explicitly marked `enforcement_mode='advisory'` in the *same* decision object. *Status: missing.*

### RL-06 — A security-disabling toggle must never be re-readable from mutable runtime by in-process code.
**Why:** A self-evolving harness runs agent-authored code in-process; if a kill switch is read from a mutable env var on every call, a skill/hotfix can flip it and disable governance — the deepest form of "hotfix becomes shadow authority" (`Hermes` YOLO-freeze, https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval).
**Spark violates it at:** `cli.py:10976-10977` (`SPARK_APPROVAL_ENFORCE` env var can disable the entire local approval gate at runtime; with no Governor fallback, setting it to `0` removes the only authority check).
**Detection:** Grep/AST — security gates must read their enabling state once at process start / from signed config; flag any `os.environ`/`getenv` read of an enforcement toggle inside a hot path. *Status: missing.*

### RL-07 — A missing authority verdict is a hard anomaly that quarantines; never synthesize a placeholder.
**Why:** Absence of a Governor verdict is the strongest possible signal that something escaped the authority spine. Manufacturing a stand-in so downstream renders cleanly masks the root condition.
**Spark violates it at:** `system_map.py:1186-1193` (synthesizes `{verdict:'unknown', reason_code:'authority_verdict_missing'}` and continues processing the candidate; also normalizes `fallback_analysis_written` as a routine artifact signal at `1165-1168`).
**Detection:** Observability assertion — a missing verdict emits a distinct `authority_trace_missing` category that blocks promotion and is counted separately, never flows through the same path as real verdicts. *Status: missing.*

### RL-08 — A failure must never be returned as a success-shaped value (None/''/{}/synthesized OK/midpoint score).
**Why:** PD-5. This is the exact mechanism by which a local hotfix is born: the agent proceeds on empty state. The single line that separates a legitimate fallback from a masking one — unknown/error ⇒ decline/unavailable, never ⇒ approve (`Hermes`, https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime; `Anthropic`, https://www.anthropic.com/engineering/writing-tools-for-agents).
**Spark violates it at:** `voice_judge.py:63-72` (`_parse_score` returns the ambiguous midpoint `5` on empty/garbled judge output — a judge outage laundered into a real-looking `0.5`); `runtime.py:808-856` (`try_spark_character_fallback` returns a canned in-character reply on `bridge_error`/`disabled`/`stub`, so a failed bridge reads as a normal turn); `runtime.py:4033-4042` (broad `except Exception` swallows voice errors into a soft text message with no escalation).
**Detection:** AST detector for "silent-success fallback" — `except` blocks or `if failed:` paths that return a success-shaped value without a `reason_code` + degrade/deny verdict. Cross-checked by the legitimate-vs-masking taxonomy in `02_REAL_FIX_PLAYBOOK.md`. *Status: missing.*

### RL-09 — Control flow must never be keyed on a rendered human-readable error string.
**Why:** A branch keyed on English error text silently stops firing the moment wording, locale, or an upstream message changes — and it re-infers a condition the code already knew structurally.
**Spark violates it at:** `cli.py:886-892` (`is_dirty_update_failure` substring-matches `'working tree has local changes'` to choose recovery flow); `cli.py:14933-14939` (`user_safe_startup_detail` matches `'TELEGRAM_RELAY_SECRET'` to swap in a canned remediation); `errorExplain.ts:66-309` (substring-matches the error text into ~12 canned `{userLine,check,repair}` buckets).
**Detection:** Grep/AST — flag `if <substring> in <error_text/detail>` driving control flow; require typed failure reasons (enum/dataclass), with the human string *generated from* the type, never matched against it. *Status: missing.*

### RL-10 — A deterministic answer-key must never be baked into the live answering path to pass a benchmark.
**Why:** PD-7. Benchmark-string ⇒ literal-answer branches are not retrieval or inference; they mask that the underlying extraction cannot derive the answer, and they silently break on phrasing drift. Eval improvements must be gated on a held-out set so overfitting is detectable.
**Spark violates it at:** `provider_rescue_identity.py:6-173` (returns hard-coded `'a sunset with a palm tree'`, `'Liberal'`, etc. keyed to benchmark tokens); `provider_temporal_rescue.py:132-238` (literal scenario phrases as priorities); `memory_queries.py:75-78` (hard-codes `'alice'`/`'bob'`); `memory_factoid_answers.py:10-90` (`{'stamford':'Connecticut'}` + literal dated question strings); `mission-size-classifier.ts:104-116` (equality check against the literal phrase `'did you understand what i said'`).
**Detection:** CI eval-integrity gate — held-out-set check on chip/classifier changes; an AST detector flags literal proper-noun / dated-question / persona-answer constants on a code path that returns user-facing answers. *Status: missing.*

### RL-11 — A deterministic rescue/canned plane must never run *ahead of* real model/retrieval reasoning.
**Why:** Precedence inversion is the structural mechanism that turns a pile of hotfixes into authority: the answer-key family wins over real reasoning for any input it matches.
**Spark violates it at:** `providers.py:1828-1830` (`_question_aware_rescue` runs and short-circuits return *before* normal extraction).
**Detection:** Unit invariant test — any retained rescue plane must be invoked only *after* model/retrieval yields nothing, and its output must be tagged low-confidence with provenance. *Status: missing.*

### RL-12 — A higher-intelligence reviewer/planner must treat the action it reviews as UNTRUSTED INPUT and must have a first-class `escalate` verdict.
**Why:** The planner reviewing a CUA's proposal must frame it as data, not instructions, and route uncertainty *up* — not collapse into a binary that pressures a local approve/hotfix (`Hermes` smart-approve, https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval; `Anthropic` fresh-context reviewer, https://www.anthropic.com/engineering/multi-agent-research-system).
**Spark violates it at:** the routeArbiter LLM is type-locked `'off'|'shadow'` with **no `enforce` value** (`routeArbiter.ts:12,56-61`), so the higher intelligence is structurally barred from ever being authority; on arbiter failure the catch hard-codes `allow:false` and is invisible to routing (`routeArbiter.ts:188-205`).
**Detection:** Unit invariant test — the arbiter/planner verdict type must include `escalate`; a typed promotion path (`shadow → enforce`) must exist; reviewer input must be quarantined (wrapped, directives ignored). *Status: missing.* See `03_CUA_ESCALATION_PROTOCOL.md`.

### RL-13 — A denial, timeout, or unmet gate is a hard halt. The agent must never retry/rephrase/substitute to route around it.
**Why:** "Silence is not consent; an explicit deny is a hard halt" (`Hermes`, https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py). Routing around a deny by inventing a fallback that satisfies the surface check *is* the hotfix culture.
**Spark violates it at:** `local.py:89-116` (`allow_fallback_planner` degrades *down* to a weaker planner instead of halting/escalating up); `errorExplain.ts:289-294` (tells the user to "ask me the same thing again" — inviting a blind retry that masks the failed dependency); `cli.py:823-855` (shallow-ancestry-undecidable proceeds anyway with a note instead of failing closed).
**Detection:** Unit invariant test — a `deny`/unmet-gate outcome must terminate the workstream with a recorded reason; assert no automatic alternative-command/rephrase path follows a deny. *Status: missing.*

### RL-14 — A self-attesting compliance flag must never be hardcoded; it must be derived from live evidence.
**Why:** A record that *asserts* charter compliance the system has not verified makes the explanation fictional — and Observability requires that "if Spark cannot explain why it acted, the run is not ready" (`RUNTIME_CHARTER.md:133`).
**Spark violates it at:** `kernel.py:316-322` (`governor_decision()` hardcodes `execution_boundary.legacy_authority_demoted = True` for every decision, with no check that any legacy plane was actually demoted). **Root cause is in the CONTRACT, not just the code:** `governor-decision-v1.schema.json:57,65` makes `execution_boundary.legacy_authority_demoted` a *required* field with `{ "const": true }` — so the honest value (a derived boolean) **cannot validate**. The code hardcodes `True` because the schema forces it. (Surfaced by the 2026-06-24 conflict check — this is deeper than the original audit caught.)
**Detection:** Unit invariant test — `legacy_authority_demoted` must be derived from a live `LegacyAuthorityInventoryV1.release_gate.zero_high_agency_legacy_local_gates` for the surface, or removed from the per-decision record. **The fix REQUIRES a schema amendment** (`const: true` → `type: boolean`, or drop it from `required`), which is itself a protected-component change governed by RL-17 (human approval). *Status: missing (and currently un-satisfiable without the schema change).*

### RL-15 — Readiness/promotion gates must be DERIVED from artifacts, never trusted as caller-supplied booleans.
**Why:** This is *the* enforcement hole that lets every other offender persist. A surface can pass the legacy-plane Stop-Ship gate while a regex still vetoes execution, because nothing cross-checks the claim against source.
**Spark violates it at:** `kernel.py:677-744` (`readiness_score()` reads `zero_high_agency_legacy_local_gates`, `governance_rulesets_proven`, `performance_budget_proven` as a trusted `dict[str,bool]` and never verifies them).
**Detection:** Schema validation + CI — `readiness_score` must reject these gates as raw booleans without backing artifacts (a fresh legacy-plane scan reconciliation + a governance-ruleset run result). *Status: missing.*

### RL-16 — The legacy-authority inventory must be COMPUTED from a source scan, never a self-attested hand-maintained list.
**Why:** An inventory that is supposed to *prove* retirement but is a manual allowlist drifts; new route regexes keep the gate green while the inventory silently omits the biggest live planes — making "plane retired" unfalsifiable.
**Spark violates it at:** `legacyAuthorityInventory.ts:1-289` (hand-maintained array that never scans source); `legacy_authority_inventory.py:81-200` (omits `routeFirewall.ts` and `naturalRouteDecision.ts` entirely).
**Detection:** CI reconciliation — an AST/regex scanner walks all surfaces, finds every function returning allow/deny/route verdicts from regex/keyword input, and FAILS if any such plane is not declared with `disposition != active_authority`. *Status: missing.*

### RL-17 — Self-evolution must never mutate its verifier, benchmark/golden set, model config, or authority policy without explicit human approval — and the protected set must actually include the authority-bearing files.
**Why:** "the grader must not be writable by the graded" (PD-7; `RUNTIME_CHARTER.md:150`). A self-evolution run that can edit the regex routing tables as ordinary code alters authority without tripping protected-component approval — the `config.apply`-mutates-its-own-governor CVE class (`OpenClaw` CVE-2026-45001, https://www.vulncheck.com/advisories/openclaw-gateway-config-mutation-guard-bypass-via-agent-tool-access).
**Spark violates it at:** the protected-component gate is genuinely enforced in `kernel.py:81/1545` (`PROTECTED_EVOLUTION_COMPONENTS`), **but** there is no guard ensuring the protected set *includes* `routeFirewall`/route tables or the `legacy_authority_inventory` list — they are treated as ordinary code (`enforcement_gaps`, `mandate-vs-reality` slice).
**Detection:** Schema validation — the protected set must enumerate every authority-bearing file/table; a ChangeManifest touching any of them requires a `human_approval_ref`. *Status: partial (gate exists; protected set incomplete).*

### RL-18 — A deny/guard enforced on one path but not its siblings is "unpaired theater" and is a defect, not a partial fix.
**Why:** Single-path fixes are why symptoms recur: the one observed route is patched and sibling routes stay open, spawning the next hotfix round. "Enumerate all paths to this effect" is a requirement of any guard (`Hermes`, https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py).
**Spark violates it at:** the r1..r28 cadence itself (`cli.py:823-855` env-specific guards bolted onto the pin path one OS at a time); `approval.py:137-597` (the regex gate covers the *observed* binaries but misses `bash script.sh`, `xargs rm`, aliases/shims, base64-to-`python -c` — the effect is governed on one path only — `enforcement_gaps`, spark-cli slice).
**Detection:** Capability/effect-based mediation (broker that intercepts the real effect: fs delete, network egress, credential read, process persistence) so all sibling paths to one effect are gated once; the string table is advisory pre-screen only. *Status: missing.*

### RL-19 — Memory, pending state, route history, provider names, or stale mission state must never override fresh user intent.
**Why:** Charter Runtime Authority (`RUNTIME_CHARTER.md:17-23`; Stop-Ship Gate `:172`) and the Genesis Kernel non-negotiable (`SPARK_GENESIS_KERNEL_SCHEMA_DESIGN.md:41-49`): "fresh user intent is the only source that can authorize a new high-agency move"; everything else is *evidence only*, and "pending state expires as context, not authority" (`RUNTIME_CHARTER.md:112-116`). Memory that promotes itself to instruction is shadow authority with a long half-life — a founder-named pain class.
**Spark status:** No single committed offender among the 51 *grants* on memory alone, so this Red Line is **preventive** — but the nearest live instance is `providers.py:1828-1830`, where a memory chip's canned rescue plane wins *precedence* over fresh extraction (RL-11), demonstrating the exact precedence inversion this gate forbids at authority scope. The multi-module mesh has no invariant asserting memory contributes only evidence.
**Detection:** Unit invariant — memory/pending-state inputs may only produce `evidence_ref`s; assert they never set `selected_intent`, `authority_state`, or a proposed action; observability assertion that any turn whose authority traces to a memory/pending source is blocked. *Status: missing.*

### RL-20 — A conversational (chat-only) move must never carry or execute a proposed action or side effect.
**Why:** Charter Move Semantics (`RUNTIME_CHARTER.md:44-58`; Stop-Ship Gate `:173`): `chat_explain`/`chat_plan`/`chat_compare`/`chat_score`/`chat_draft_text` "must not contain proposed actions … must not write memory, launch missions, publish, deploy, schedule, edit files, or call external tools." A chat surface that smuggles a decision is an unaccountable execution path that bypasses the whole tool lifecycle.
**Spark status:** The audit found answer paths that *are* decisions — the domain-chip-memory rescue/canned plane returns a user-facing answer that holds authority over real reasoning (`providers.py:1828-1830`, `provider_rescue_identity.py:6-173`), and 129 deterministic `reply_text` strings (`runtime.py:13251-13256`) render as normal answers with no governed move. The Move-Semantics contract itself is operationalized nowhere in code.
**Detection:** Schema validation — a record whose `selected_move` is conversational must carry empty `proposed_actions` and zero tool/mutation calls; AST flag for a chat-move code path that reaches a mutating capability. *Status: missing.*

### RL-21 — A declared capability with no executable surface (a hollow chip/module) must never be presented as available or trusted.
**Why:** A module that claims a domain but ships no implementation is a missing capability masked by a manifest. If the planner/Governor routes to it or trusts it, it is hollow authority — the spec exists, the enforcement does not, and the failure is silent.
**Spark violates it at:** `domain-chip-spark-bug-recognition/source/AGENTS.md` — the entire source tree is a single `AGENTS.md`; no `src/` package, no detector, no tests, yet the chip declares the "bug recognition" domain.
**Detection:** Chip-registration CI gate — fail registration of any chip that declares a domain/contract but exposes no executable surface (no `src/` entrypoint satisfying its declared interface, no tests). *Status: missing.*

---

## 4. THE RULES

Rules are the **operating discipline** below the Red Lines. Each has DO / DON'T / Spark evidence / enforcement. Grouped by theme A–G. Crossing a Red Line blocks promotion; breaking a Rule blocks the PR.

### (A) Authority & Routing

#### R-01 — Bind authority to the parsed/typed action, not to a re-tokenized argv or raw text.
- **DO** declare each handler's `action_class`/`risk` as typed metadata and evaluate *that* typed intent in one envelope.
- **DON'T** re-derive intent by string-matching `sys.argv` with an ad-hoc tokenizer beside the real parser.
- **Spark evidence:** `cli.py:17925-17932` (a shadow gate re-parses argv via `approval_required_for_command` while `args.func(args)` dispatches the already-parsed `Namespace` — two routers that can disagree → bypass or false-block).
- **Enforcement:** AST authority-site detector (RL-01); unit test that authority is read from the parsed action.

#### R-02 — Demote every route detector to an evidence adapter. A regex may NARROW (veto, low-confidence), never GRANT.
- **DO** have the detector emit `route_candidate` evidence_refs with confidence + reason into the envelope; let the Governor (or a model-backed move-classifier) own the verdict.
- **DON'T** make `routeVerdict.confidence === 'explicit'` (a pure regex outcome) sufficient to authorize a route.
- **Spark evidence:** `telegramActionAuthority.ts:79-102`; `routeFirewall.ts:403-521`; `naturalRouteDecision.ts:217-520` (99-branch de-facto turn-selector); `telegramIntentGate.ts:47-110` (89 regex sites select route before the firewall runs).
- **Enforcement:** RL-01 + RL-02 detectors; inventory reconciliation (RL-16).

#### R-03 — One central authority owned by the harness core; surfaces never hold a local policy copy.
- **DO** call the shared Governor (the CLI already shares `GOVERNOR_HMAC_SECRET_ID`, `cli.py:69-72`) for a signed allow/deny verdict.
- **DON'T** re-implement policy per repo as a local if/elif ladder.
- **Spark evidence:** `approval.py:137-597` (entire CLI authority is a local string table; there is no Governor envelope in this path).
- **Enforcement:** CI cross-repo check that authority decisions resolve through one module; AST flag for duplicated policy tables.

#### R-04 — Re-authorize at every trust-boundary crossing; session/route IDs are routing handles, not authorization.
- **DO** re-check authority at each module hop (CLI → harness-core → telegram-bot → CUA); use context-local approval state so a decision in one session can't authorize another.
- **DON'T** trust a session/route identity, or replay an approval from another context, as authority.
- **Spark evidence:** `telegramActionAuthority.ts:79-102` treats `routeAuthorizedByTurn` — a *routing* fact — as a conjunct of the authorization decision, conflating route identity with authority; the per-hop re-authorization invariant is otherwise absent across the CLI→harness-core→telegram→CUA mesh (this rule is partly **preventive**) (`mandate-vs-reality` slice; `Hermes`, https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md).
- **Enforcement:** unit invariant per boundary; observability assertion that each hop carries its own `AuthorizationDecisionV1`.

### (B) Fixes & Fallbacks

#### R-05 — Every fix names a CLASS and a root cause; symptom-pins are rejected.
- **DO** write a root-cause hypothesis answering "why did the *system* allow any input to reach this state?" (5 Whys).
- **DON'T** add a branch that silences one instance.
- **Spark evidence:** `cli.py:823-855` (stacked per-environment git-recovery clauses); `mission-size-classifier.ts:29-128` (magic thresholds `>=9`, `>=3` with no principled basis).
- **Enforcement:** ChangeManifest gate requires the `root-cause hypothesis` + `target component` fields to name a class (see `02_REAL_FIX_PLAYBOOK.md`); reviewer checklist.

#### R-06 — A fallback is legitimate ONLY if it (a) fails closed and (b) emits a traceable, actionable reason. Otherwise it is failure-masking and is removed.
- **DO** convert failure into an explicit `deny`/`degrade` verdict with a `reason_code` (the good pattern: `kernel.py:352-359` returns `deny` with `reason_code: invalid_governor_decision`).
- **DON'T** return empty-but-success-shaped data, a synthesized verdict, or a midpoint score.
- **Spark evidence (masking):** `voice_judge.py:63-72`; `runtime.py:808-856`; `runtime.py:4033-4042`; `system_map.py:1186-1193`. **Legitimate (keep):** `gateway/guardrails.py` normalizations; `browser/service.py` honest `*_FAILED` statuses; `runtime.py:13253` honest operator-pause message.
- **Enforcement:** RL-08 detector; the legitimate-vs-masking taxonomy in `02_REAL_FIX_PLAYBOOK.md`.

#### R-07 — Normalize untrusted input to ONE canonical form upstream of all rules, instead of stacking a patch per evasion.
- **DO** canonicalize paths, identifiers, encodings, unicode, shell forms, aliases at the boundary so a small rule set matches; resolve filesystem ops through a trusted-root handle, not `path.resolve().startsWith()`.
- **DON'T** add guard round N+1 for one more un-normalized edge case.
- **Spark evidence:** the r28 long-path saga (`cli.py:533,980-984`, `.git` tip `hotfix/r28-longpath-guard`).
- **Enforcement:** lint for `.startsWith` path checks; a single canonicalization pass with a test matrix (`Hermes`, https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval; `OpenClaw`, https://docs.openclaw.ai/gateway/security/secure-file-operations).

#### R-08 — Unattended/autonomous runs get a SEPARATE, conservative resolution: deny-by-default, halt-and-queue.
- **DO** make self-evolution and CUA loops fail toward "halt and queue for human review" when uncertain; same detection, conservative resolution.
- **DON'T** let an unattended run auto-resolve an uncertain action via a fallback (the unwitnessed-drift case).
- **Spark evidence:** no failure→escalation anywhere in the Telegram runtime/swarm bridge (`sync.py:1217-1360` is user-typed and keyword-gated).
- **Enforcement:** unit invariant — autonomous-context flag forces `deny`/`interrupt` on uncertainty (`Hermes` cron-mode, https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py).

### (C) Canned Responses & Eval Integrity

#### R-09 — Map structured error CODES to remediation in one registry; never pattern-match a rendered message to choose a reply.
- **DO** have the producing layer emit `{code: 'telegram_relay_secret_missing'}`; preserve the original detail alongside the friendly hint.
- **DON'T** substring-match the rendered detail to select a canned response.
- **Spark evidence:** `cli.py:14933-14939`, `cli.py:7423`, `cli.py:14949`; `errorExplain.ts:66-309`; `runtime.py:13251-13256` (129 deterministic `reply_text` strings).
- **Enforcement:** RL-09 detector; registry-shape lint.

#### R-10 — Answers come from data + model extraction; names, facts, dates, personas must never be literals in code.
- **DO** resolve speakers/entities from stored conversation metadata; let the model handle factoid/geography/temporal inference; keep only general extraction features.
- **DON'T** commit benchmark proper nouns, dated question strings, or persona answers to a live path.
- **Spark evidence:** `provider_rescue_identity.py:6-173`; `provider_temporal_rescue.py:132-238`; `memory_queries.py:75-78`; `memory_factoid_answers.py:10-90`.
- **Enforcement:** RL-10 eval-integrity gate; held-out-set regression on chip changes.

#### R-11 — Gate eval improvements on a HELD-OUT set; a benchmark pass via memorized strings is a stop-ship, not a win.
- **DO** assert invariants over a *family* of inputs (e.g. "no execute without `AuthorizationDecisionV1`"), and judge agents on correct FINAL STATE.
- **DON'T** assert a canned string in a regression test (it freezes the workaround).
- **Spark evidence:** 877 `assertIn` literal assertions pin phrases not invariants (`fix-qa-discipline` slice); fake-literal `cpm` gate noted in prior progression work.
- **Enforcement:** CI generalization/coverage gate; lint that flags literal-reply assertions in authority/answer tests (`hotfix-debt-theory`, https://blog.codepipes.com/testing/software-testing-antipatterns.html; `oss-harness-comparison` Aider verify-loop, https://aider.chat/docs/usage/lint-test.html).

#### R-12 — A judge/scorer failure must surface as an explicit error/None, never coerce to a numeric midpoint.
- **DO** distinguish "judge said ambiguous (5)" from "judge produced no parseable score" — on unparseable/empty, raise or return `None` so the caller can retry or mark the run invalid.
- **DON'T** record a real-looking `0.5` that corrupts metrics and any gate built on them.
- **Spark evidence:** `voice_judge.py:63-72`.
- **Enforcement:** unit invariant on scorer parse paths (RL-08).

### (D) Self-Evolution & Governance

#### R-13 — Every improvement flows through a `ChangeManifestV1` carrying the full evidence set; missing evidence ⇒ `not_ready`, never a mutation.
- **DO** declare failure evidence, root-cause hypothesis, target component, predicted fixes, regression risks, required tests, live-proof requirement, rollback plan, observed delta, verdict (`RUNTIME_CHARTER.md:152-163`).
- **DON'T** mutate files outside an accepted manifest.
- **Spark evidence:** `change_manifest_runner` is a callable invoked only by CLI/TS helpers; no live self-evolution path is forced through it as a chokepoint (`enforcement_gaps`, harness-core slice).
- **Enforcement:** CI chokepoint — runtime mutations require an accepted manifest token; human-approval gate for protected components (RL-17).

#### R-14 — Hold an explicit allowlist of which fields self-evolution may touch; HARD-REFUSE in code any write to the authority/policy/security layer.
- **DO** enumerate tunable fields; refuse control-plane edits (authority policy, the enforcement toggles, the manifest gate, the legacy inventory).
- **DON'T** let a degraded model output silently widen its own scope or shrink a safety allowlist.
- **Spark evidence:** protected set exists (`kernel.py:81/1545`) but omits the route tables / inventory (RL-17); no anti-truncation guard on self-mod writes.
- **Enforcement:** schema validation + `replacePaths`-style anti-truncation guard (`OpenClaw`, https://docs.openclaw.ai/cli/approvals; CVE-2026-45001, https://www.vulncheck.com/advisories/openclaw-gateway-config-mutation-guard-bypass-via-agent-tool-access).

#### R-15 — A "quick win" hotfix must be labeled a stopgap and paired with the named long-term general mechanism (honor Legacy Plane Retirement).
- **DO** answer "is this a data row in an existing general mechanism, or a new special-case branch?"; if special-case, attach a retirement owner + ticket.
- **DON'T** keep a "for now" detector without a retirement owner.
- **Spark evidence:** `routeFirewall.ts:235` (`isBoundedOperatorProbe` hard-codes the exact level-5 smoke-test temp path — a canned recognizer for one QA prompt in production routing); the bug-recognition chip ships only `AGENTS.md`, zero implementation (`domain-chip-spark-bug-recognition/source/AGENTS.md`).
- **Enforcement:** ChangeManifest field `stopgap_retirement_owner`; registration gate fails a chip with no executable surface (`Hermes` #16475, https://github.com/NousResearch/hermes-agent/issues/16475).

#### R-16 — New policy is a declarative manifest row evaluated by ONE generic engine, not a new code branch in core.
- **DO** express a new determinism rule as `(pattern + risk tier + escalation target)` data; collapse N hotfix rounds into N reviewed data rows.
- **DON'T** smear policy into mechanism by branching core logic per symptom.
- **Spark evidence:** `prd-analyzer.ts:136-628`, `goal-analyzer.ts:23-348`, `skill-router.ts` — 3–4 competing keyword analyzers for one decision; `mission-size-classifier.ts:29-128` static RULES table as authority.
- **Enforcement:** policy-as-data schema (PD-3); dedupe lint for competing classifiers (`Hermes` #5528, https://github.com/NousResearch/hermes-agent/issues/5528; Brinch Hansen, https://en.wikipedia.org/wiki/Separation_of_mechanism_and_policy).

### (E) Observability & Honesty

#### R-17 — Every meaningful step is inspectable; if Spark cannot explain why it acted, the run is not ready.
- **DO** emit envelope, candidate evidence, selected move, proposed action, authorization decision, tool-lifecycle stage, sanitized output, run verdict, readiness score, change manifest (`RUNTIME_CHARTER.md:118-133`) as OpenTelemetry-style spans.
- **DON'T** ship a path you can't trace.
- **Spark evidence:** the CUA path (`browser/service.py`) is a thin payload-builder with no in-process planner loop, no trace of decision/verdict (`cua-orchestration` slice).
- **Enforcement:** observability assertion as a release gate (`cua-orchestration`, https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide).

#### R-18 — A low-information/degraded model reply must be recorded as a `degrade` with a reason code, never silently swapped for templated surface text.
- **DO** emit `degrade` with `provider_low_signal`/`route_blocked` and tell the user the request was degraded.
- **DON'T** substitute templated text that reads as a normal answer ("report missing proof, don't fill from memory", `AGENTS.md:80`).
- **Spark evidence:** `index.ts:3106-3109,3270-3281` (`isLowInformationLlmReply` swaps `applyPlainWordsSurfaceRequest`/canary text without recording why).
- **Enforcement:** RL-08 detector; honesty lint on reply-substitution paths.

#### R-19 — Maintain a golden-trace replay harness; deterministic checks live in the EVAL/verifier lane, never in the runtime authority path.
- **DO** keep a small (~20) golden set of real journeys and run scheduled replay with deterministic fixtures that bypass live calls — a replay would have caught each of the 28 hotfix rounds as a regression.
- **DON'T** bury deterministic verification as a runtime router.
- **Spark evidence:** the r1..r28 accretion (no replay caught it); 877 literal assertions instead of invariants.
- **Enforcement:** CI replay job; 3-layer eval stack (unit → LLM-judge → trace sampling) (`cua-orchestration`, https://arize.com/ai-agents/agent-observability/; `oss-harness-comparison`, https://docs.langchain.com/oss/python/langgraph/durable-execution).

#### R-20 — Instrument change-failure-rate per self-evolving component; a rising-hotfix component is not release-candidate ready.
- **DO** track CFR on self-evolution runs; treat hotfix velocity as a *cost*, not throughput.
- **DON'T** mistake round-count for progress.
- **Spark evidence:** the r28 cadence with no change-failure metric (`fix-qa-discipline` enforcement gaps).
- **Enforcement:** DORA CFR metric wired to readiness (`hotfix-debt-theory`, https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance).

### (F) Maintainability / God-files

#### R-21 — No module over 1,500 lines without an extraction ticket; no file over 3,000 lines without a named owner + refactor plan — enforced by CI.
- **DO** execute the already-planned extractions (`registry_policy`, `secret_store`, `autostart`, `doctor`, `approval`).
- **DON'T** add a new domain inline to a god-file.
- **Spark evidence:** `cli.py:1-17936` (~6× the hard cap, redline written 2026-04-26); `index.ts:1-10486` (>3× the cap, with inline `/regex/.test` route branches at `1706`, `6045-6046`).
- **Enforcement:** CI line-count gate that fails the build for files >3000 lines lacking a registered owner+refactor-plan token.

#### R-22 — Collapse competing detectors/analyzers into one model-driven authority; no two keyword routers for the same decision.
- **DO** unify `prd-analyzer`/`smart-prd-analyzer`/`goal-analyzer`/`skill-router` into one analyzer with explicit reasoning + honest confidence.
- **DON'T** ship a fabricated confidence (keyword-count → score) that signals "understood" when it isn't.
- **Spark evidence:** `goal-analyzer.ts:284` (`keywords.length>=5` adds `0.05`); `prd-analyzer.ts:563-565` (ad-hoc idf weighting); duplicate routing across the spawner-ui keyword routers.
- **Enforcement:** shotgun-surgery lint — "add a new route WITHOUT editing a detector" as the acceptance test (`hotfix-debt-theory`, https://en.wikipedia.org/wiki/Shotgun_surgery).

### (G) CUA & Escalation (brief — see `03_CUA_ESCALATION_PROTOCOL.md`)

#### R-23 — The CUA receives a bounded task envelope (objective + expected end-state + allowed surfaces/domains + explicit "do NOT" list) and acts only inside it.
- **DO** make boundary violations crisp escalation triggers.
- **DON'T** let vague delegation ("fix the page") invite the CUA to invent scope.
- **Spark evidence:** `service.py` `_normalize_allowed_domains` exists but there is no envelope, no objective/end-state contract (`cua-orchestration` slice).
- **Enforcement:** schema validation of the CUA mission envelope. Full protocol in `03`.

#### R-24 — An Evaluator step after every CUA tool result; below a confidence floor or after N stalled steps, STOP and escalate.
- **DO** diff observed state vs expected end-state; convert being-stuck into an escalation event.
- **DON'T** loop or confidently guess.
- **Spark evidence:** `service.py` has no confidence signal, no retry ceiling, no stall detector (`cua-orchestration` slice).
- **Enforcement:** unit invariant on the CUA loop; observability assertion. Details in `03`.

#### R-25 — Escalation is a typed, first-class, frequent handoff back to the planner — `escalate_to_planner(reason, evidence, partial_state)`; the executor self-authors no authority.
- **DO** return control up with the trace; the planner owns retry/replan/abort.
- **DON'T** let the worker decide long-horizon strategy or "just keep trying."
- **Spark evidence:** the only escalation (`sync.py:1217-1360`) is user-typed, keyword-gated, default `escalate=False`; `local.py:89-116` only degrades down.
- **Enforcement:** typed handoff tool; RL-12, RL-13. Details in `03` (`oss-harness-comparison`, https://openai.github.io/openai-agents-python/handoffs/).

#### R-26 — The CUA defaults to read/low authority; any medium+ action emits `interrupt` (confirmation/human), never an `allow` the CUA grants itself.
- **DO** map CUA steps onto the charter Risk Tiers; watch-mode/take-over for sensitive surfaces and credentials.
- **DON'T** self-confirm consequential/irreversible actions.
- **Spark evidence:** no risk-tier binding in the CUA path; ~3 of 4 desktop tasks fail on first attempt, so escalation must be the common path.
- **Enforcement:** unit invariant tying CUA action class → required verdict. Details in `03` (`cua-orchestration`, https://help.openai.com/en/articles/10421097).

#### R-27 — A degraded/failed/blocked CUA step is recorded as failure + escalation, never as a synthesized OK; a tool ledger is evidence, not a permission grant.
- **DO** honor authority-bound execution status: `success/failure/partial/rolled_back` require an `allow` authorization (`RUNTIME_CHARTER.md:70-79`).
- **DON'T** re-represent a blocked action as executed.
- **Spark evidence:** `_governor_outcome` conflates `degrade` with missing-ledger evidence (`kernel.py:1169-1183`).
- **Enforcement:** the genuinely-enforced ledger binding (`kernel.py:1356,1593`) extended to split `degrade` from `incomplete_evidence`.

#### R-28 — A monitor model may pause/abort a CUA run on anomalous or prompt-injected behavior; CUA screen/tool dumps are stored as artifacts and summarized, not sprayed into context.
- **DO** run a separate monitor; persist the plan to external memory to survive truncation.
- **DON'T** trust page/image-embedded instructions; don't bloat context with raw dumps.
- **Spark evidence:** no monitor model, no artifact-summarization discipline in the CUA path (`cua-orchestration` slice).
- **Enforcement:** observability + a monitor gate. Details in `03` (`Anthropic`, https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).

---

## 5. The Enforcement Model

This is the bridge from "rules on paper" to "rules enforced." Every Red Line and Rule maps to a **checker type** and a **status**. Checker types:

- **CI line-count gate** — a build step that fails on file/module size.
- **AST/grep authority-site detector** — static analysis that flags a forbidden code shape (regex-owns-authority, silent-success fallback, error-string control flow, literal answer keys).
- **Unit invariant test** — asserts a property over a family of inputs (no execute without `AuthorizationDecisionV1`; `requires_approval ⇒ enforced`).
- **Schema validation** — a record/manifest must satisfy a JSON-Schema constraint (out-of-band approval ref; field allowlist; CUA mission envelope).
- **Human-approval gate** — a protected change requires a `human_approval_ref`.
- **Observability assertion** — a release gate that the required spans/traces exist and a missing verdict trips an alarm category.

Status: `exists` (wired today), `partial` (a related mechanism exists but doesn't cover this), `missing` (no checker).

| ID | Theme | Primary checker type | Status |
|----|-------|----------------------|--------|
| RL-01 | route-regex authority | AST/grep authority-site detector | missing |
| RL-02 | Governor-as-origin | Unit invariant + AST (no self-authored governor decision) | missing |
| RL-03 | legacy detector finalizes ledger | AST detector vs `_validate_legacy_plane_disposition` | partial |
| RL-04 | synthesized human approval | Schema validation (out-of-band provenance) | missing |
| RL-05 | requires_approval ⇒ enforced | Unit invariant test | missing |
| RL-06 | mutable kill switch | Grep/AST (no hot-path env read of enforcement toggle) | missing |
| RL-07 | synthesized missing verdict | Observability assertion (`authority_trace_missing`) | missing |
| RL-08 | success-shaped failure | AST silent-success detector | missing |
| RL-09 | error-string control flow | Grep/AST (typed failure reasons) | missing |
| RL-10 | benchmark answer keys | CI eval-integrity gate + AST literal-constant detector | missing |
| RL-11 | rescue plane precedence | Unit invariant (rescue runs last, tagged) | missing |
| RL-12 | shadowed planner / escalate verdict | Unit invariant (enforce path + escalate verdict exists) | missing |
| RL-13 | route-around-deny | Unit invariant (deny ⇒ hard halt) | missing |
| RL-14 | self-attesting flag | Unit invariant (flag derived from inventory) | missing |
| RL-15 | trusted-boolean readiness | Schema validation + CI (gates derived from artifacts) | missing |
| RL-16 | hand-curated inventory | CI scan reconciliation | missing |
| RL-17 | self-evolution edits authority | Human-approval gate (protected set complete) | partial |
| RL-18 | unpaired theater | Capability/effect-based mediation broker | missing |
| RL-19 | memory overrides fresh intent | Unit invariant (memory = evidence only) | missing |
| RL-20 | chat-move carries action | Schema validation (conversational ⇒ no actions) | missing |
| RL-21 | hollow capability | Chip-registration CI gate | missing |
| R-01 | parsed-action authority | AST detector + unit test | missing |
| R-02 | demote route detectors | RL-01/RL-02 detectors + inventory scan | missing |
| R-03 | one central authority | CI cross-repo authority-resolution check | missing |
| R-04 | re-auth per boundary | Unit invariant + observability assertion | missing |
| R-05 | fix names a class | Human review gate (ChangeManifest fields) | partial |
| R-06 | legitimate fallback only | AST silent-success detector (RL-08) | missing |
| R-07 | canonicalize upstream | Grep lint (`.startsWith` paths) + test matrix | missing |
| R-08 | conservative unattended | Unit invariant (autonomous ⇒ deny/interrupt) | missing |
| R-09 | error CODE registry | RL-09 detector + registry-shape lint | missing |
| R-10 | answers from data | RL-10 eval-integrity gate | missing |
| R-11 | held-out eval gate | CI generalization/coverage gate | missing |
| R-12 | judge-failure surfaces | Unit invariant on scorer parse | missing |
| R-13 | ChangeManifest chokepoint | CI chokepoint (manifest token required) | partial |
| R-14 | self-evo field allowlist | Schema validation + anti-truncation guard | partial |
| R-15 | stopgap retirement owner | Schema field + chip-registration gate | missing |
| R-16 | policy-as-data engine | Policy schema + dedupe lint | missing |
| R-17 | full traceability | Observability assertion (release gate) | partial |
| R-18 | degrade recorded honestly | RL-08 detector + honesty lint | missing |
| R-19 | golden-trace replay | CI replay job | missing |
| R-20 | change-failure-rate | DORA CFR metric wired to readiness | missing |
| R-21 | god-file CI gate | CI line-count gate | missing |
| R-22 | collapse competing routers | Shotgun-surgery lint | missing |
| R-23 | CUA mission envelope | Schema validation | missing |
| R-24 | CUA evaluator/stall | Unit invariant + observability | missing |
| R-25 | typed escalation handoff | Unit invariant (typed handoff tool) | missing |
| R-26 | CUA read/low default | Unit invariant (action class → verdict) | missing |
| R-27 | failed step ≠ success | Ledger binding invariant (extend `kernel.py:1356,1593`) | partial |
| R-28 | monitor + artifact summary | Observability + monitor gate | missing |

**Reading of the table.** The genuinely-enforced foundations exist and must be *kept*: `kernel.py:1356,1593` (ledger binding), `kernel.py:81/1545` (`PROTECTED_EVOLUTION_COMPONENTS`), `kernel.py:1615` (`_validate_legacy_plane_disposition` schema rule), `url_policy.py` and `runtime_policy.py` (structural, parsed-input guards — the exemplars of how authority *should* be expressed). Everything marked `partial` has the right *shape* but is not wired to a scan or its scope is incomplete. Everything marked `missing` is the `mandate-by-prose` gap: the rule is real, the checker is not. The backlog in `04_AUDIT_FINDINGS_AND_BACKLOG.md` sequences building these checkers.

---

## 6. How to use this ruleset

**This ruleset binds at four points:**

1. **PR template.** Every PR answers: *Which `R-` and `RL-` does this touch? Does any change introduce a route-regex authority, a success-shaped fallback, an error-string branch, or a literal answer key? Is any "for now" labeled a stopgap with a retirement owner (R-15)?* A PR that adds a god-file domain inline (R-21) or a competing keyword router (R-22) is blocked on the answer alone.

2. **ChangeManifest.** Self-evolution runs carry the full evidence set (R-13) and the `stopgap_retirement_owner` field (R-15). Touching any authority-bearing file requires a `human_approval_ref` (RL-17). This is the promotion boundary the charter already mandates (`RUNTIME_CHARTER.md:144`); this ruleset makes its fields machine-checked.

3. **CI.** The checkers in Section 5 run on every change. The first three to land (they catch the most offenders for the least effort) are: the **god-file line-count gate** (R-21, catches `cli.py`/`index.ts` today), the **authority-site detector** (RL-01/RL-02, catches the regex-authority cluster), and the **legacy-plane scan reconciliation** (RL-16, makes "plane retired" falsifiable). Until a checker exists, its Red Line/Rule is enforced by review — and review is honesty, which is exactly the gap this document exists to close. Track checker build-out as the explicit exit from `mandate-by-prose`.

4. **Readiness / promotion.** `readiness_score` gates must be **derived from artifacts** (RL-15), not trusted booleans. A surface does not reach release-candidate while any Red Line is live, while `performance_budget_proven` / `governance_rulesets_proven` are unproven (`RUNTIME_CHARTER.md:135-138`), or while a checker marked `missing` for a Red Line it touches has not been built.

**The review gate, in one line:** *a deterministic shortcut is allowed only as a typed control-flow gate (in the Governor/policy) OR as model reasoning — never as an undeclared third thing that silently owns authority.* If a proposed change is a third thing, it does not merge.

---

## Appendix A — Exemplars to Preserve (do-not-touch / copy these)

A self-evolving harness reads its own repo as the norm, so an **allowlist of correct patterns is as important as the offender list.** A cleanup or self-evolution pass must not "re-fix" the code below — these are the right answers, drawn from the audit's `already_mandated` findings. When in doubt, *copy these shapes*; when adding a new control, it should look like one of these, not like an offender.

### A.1 Authority expressed correctly (the templates for how to do it)
- **`security/url_policy.py`** — a genuine SSRF/metadata-host/private-net allow/deny model driven by *parsed structure* (`ipaddress`, `urlparse`), not command strings. This is the canonical example of authority-as-structure (PD-1/PD-3). **Keep; copy this shape for new guards.**
- **`runtime_policy.py`** — argv-only execution (no shell-chain tokens) + an explicit interpreter allowlist (`python`/`node`/`npm`/`uv`). A structural guard, not a string-pattern hotfix. **Keep.**
- **`spark-researcher/adapters/exec.py`** — generic execution disabled by default + an explicit `ALLOWED_ADAPTER_EXECUTABLES` allowlist. The findings explicitly warn: **do NOT re-invent or "harden" this.**

### A.2 Genuinely-enforced governance (the spine that already works)
- **`kernel.py:1356` + `kernel.py:1593`** — tool-call-ledger binding + `_assert_execution_status_authorized`: executed statuses (`success/failure/partial/rolled_back`) require an `allow`, and the ledger's authorization must match turn/action/capability/decision ids. **This is the working core of the charter's Tool Lifecycle — extend it (R-27), never weaken it.**
- **`kernel.py:81` / `kernel.py:1545`** — `PROTECTED_EVOLUTION_COMPONENTS` + `_validate_self_evolution_policy`: verifier/benchmark/model-config/authority-policy cannot be marked editable-by-evolution and require a `human_approval_ref`. Fail-closed and correct (PD-7). *The only fix needed (RL-17) is to make the protected **set** include the route tables + legacy inventory — not to change this mechanism.*
- **`kernel.py:1615`** — `_validate_legacy_plane_disposition`: an `evidence_adapter` disposition cannot retain high-agency risk; a `canonical_consumer` requires `governor_required` + `consumer_of_governor` + `ledger_required`. The right schema rule — RL-03/RL-16 only ask that it be *wired to a runtime scan*.
- **`kernel.py:703-738`** — readiness gates encode the charter's promotion requirements (`performance_budget_proven`, `governance_rulesets_proven`, `zero_high_agency_legacy_local_gates`) **correctly as data**. RL-15 fixes only that the booleans must be *derived from artifacts*, not the gate definitions.

### A.3 Honest failure (legitimate fallbacks — NOT masking)
- **`browser/service.py`** — the browser-use/CUA adapter records honest failure status (`BROWSER_USE_DOCTOR_FAILED`, `SMOKE_REQUIRED_PROOF_FAILED`, `last_failure_reason`, smoke proofs) rather than faking readiness. Its fallbacks are legitimate defensive status reporting. **This is what RL-08 wants — keep it.**
- **`runtime.py:13253`** — the honest operator-pause message ("Spark Intelligence is temporarily paused for this Telegram channel") is a *true* status, not a masked failure (finding F-51). Legitimate.
- **`system_map.py`** — emits an authority-verdict index / OS-review candidates that are review-only, with `human_review_required` and network/memory promotion disabled by default (fail-closed promotion posture). Keep the posture; RL-07 only fixes the synthesized-`unknown`-verdict path.

### A.4 Legitimate deterministic substitutions (narrow, documented — do NOT flag as offenders)
- **`gateway/guardrails.py`** — `_strip_em_dashes` and `_normalize_score_decimals_to_percent` are narrow, documented, justified outbound persona/format normalizations. The findings explicitly say **do NOT flag or "re-fix" these.** They are the boundary case that proves the rule: a deterministic transform is fine when it is presentation-only and changes no decision.
- **`qa-evidence-lane/validator.py`** — redaction/format guards (`no_raw_ids`, `no_paths`, `no_secrets`, provider-field whitelist). Legitimate regex use for *output safety* (not authority). Keep as-is.

### A.5 Right shape, wrong source (keep the shape, fix the source)
- **`security/approval.py`** already classifies actions into a typed `ApprovalClass`/`ApprovalRisk` and emits a structured `ApprovalDecision` with `command_digest` + `confirmation_phrase`, and redacts secrets before hashing (`_digest_command`). The **shape is correct**; RL-01/R-03 only move the *source* of the classification from string-matching to a typed parsed action resolved through the one Governor. Non-interactive contexts already fail closed (`approval.py:121`, `cli.py:11013-11019`) — preserve that.

> The boundary test for this appendix: a pattern belongs here if it (a) derives its decision from *parsed structure or declared data*, not a rendered string, and (b) fails closed with an honest reason. If a "fix" would make one of these look more like an offender, the fix is wrong.

---

### Sibling documents

- `00_README.md` — orientation, the two pains, how the doc set fits together.
- `01_RULESET.md` — **this document.** The anchor: Prime Directives, `RL-01`..`RL-21`, `R-01`..`R-28`, the Enforcement Model, and Appendix A (Exemplars to Preserve).
- `02_REAL_FIX_PLAYBOOK.md` — how to shape a real fix; the legitimate-fallback vs failure-masking taxonomy (expands R-05, R-06, RL-08).
- `03_CUA_ESCALATION_PROTOCOL.md` — the planner↔CUA contract; the escalation protocol (expands R-23..R-28, RL-12, RL-13).
- `04_AUDIT_FINDINGS_AND_BACKLOG.md` — the 51 offenders, grouped by root cause, sequenced into a checker-build backlog.
- `05_EXTERNAL_HARNESS_LESSONS.md` — the 51 research lessons (Hermes, OpenClaw, Anthropic, OSS, hotfix-debt theory, CUA orchestration) with source URLs.
