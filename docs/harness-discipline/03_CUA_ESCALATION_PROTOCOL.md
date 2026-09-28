# CUA ↔ Higher-Intelligence Orchestration

> Source of truth: `docs/harness-discipline/`. Grounded in the 2026-06-24 Spark harness audit (51 offenders) + Hermes/OpenClaw/Anthropic/OSS research (51 lessons).

This document is the protocol for the founder's **pain #2**: Telegram-desktop CUAs (computer-use agents) that failed to cooperate with a higher-intelligence planner and drifted into local hotfixes. It is the operational expansion of `R-23`..`R-28`, `RL-12`, and `RL-13` defined in `01_RULESET.md`. Where this doc cites an `RL-` or `R-`, the canonical definition lives there.

It does not restate the charter; it extends it. The `RUNTIME_CHARTER.md` already encodes the right spine — `surfaces observe → Governor decides → lifecycle executes → ledgers prove → evolution improves` — and the right authority model (`surfaces submit evidence … they do not own authority`, `RUNTIME_CHARTER.md:100`). The gap is that **the actual CUA path is unenforced exactly where pain #2 lives.** This protocol closes that gap.

---

## 1. The problem, restated — and the Spark evidence

### 1.1 What "CUA" means in Spark

The "CUA" in this stack is not (yet) a screenshot/click desktop loop. It is the **Telegram-driven agent**: a Telegram message is classified into a route and dispatched to a handler that may launch missions, write memory, switch models, run the spawner, and (via `spark-intelligence-builder`'s `browser/service.py`) drive an external `browser-use` CLI. The `browser/service.py` adapter is "a thin payload-builder over an external browser-use CLI with no in-process planner loop, no escalation, no retry ceiling, no confidence signal" (`cua-orchestration` slice). So the entire failure surface of a desktop CUA already exists in spirit, with none of the orchestration discipline a desktop CUA would force you to build.

### 1.2 The core finding: there is ZERO automatic failure → planner escalation

The single most important finding for this document, stated by the Telegram + CUA audit slice verbatim:

> When the CUA hits a failure or ambiguity it does NOT escalate to a planner or open a root-cause path. There is **ZERO automatic failure→escalation anywhere** … The only escalation, `evaluate_swarm_escalation`, is user-typed (`/swarm evaluate <task>`) and decides via keyword substring match + word-count ≥ 40 … failure/ambiguity is not even in its trigger set, and its default is `escalate=False`, `mode="hold_local"`.

That last clause is the whole disease in one line. When the agent is stuck, the system's default is **`hold_local`** — stay local, improvise — which is precisely the behavior that mints pain #1 (a local deterministic hotfix that becomes shadow authority). The four concrete offenders:

| What the code does | File:line | Why it produces pain #2 |
|---|---|---|
| `routeArbiter` (the higher-intelligence LLM classifier) is type-locked `'off' \| 'shadow'` — **no `enforce` value exists** — and `queueRouteArbiterShadow` only appends a JSONL record; it never feeds back into routing. | `routeArbiter.ts:12,56-61` | The higher intelligence is **structurally barred** from ever becoming authority. "Shadow" was meant to be a migration step toward enforce, but there is no `enforce` value in the type, so the migration can never complete — the shadow became permanent (`RL-12`). |
| `telegramIntentGateV2Mode` defaults to `'enforce_safe'` — the regex/keyword IntentGate V2 is the **LIVE enforcing selector** while the LLM arbiter and naturalRoute decision are shadow. | `telegramIntentGate.ts:766-788` (default at `:770`) | The deterministic gate enforces while the intelligent gates only observe — the inverse of the charter's intent. `enforce_safe` was the conservative migration default that became the permanent operating mode. |
| `evaluate_swarm_escalation` — the **only** escalation-to-higher-intelligence path — decides whether to hand a task up purely by keyword substring match (`'swarm'`,`'delegate'`,`'parallel'`,`'comprehensive'`,`'orchestrate'`) plus `len(task.split()) >= 40`. Default branch returns `escalate=False, mode='hold_local'`. | `sync.py:1217-1360` | "The CUA cannot decide to escalate because the escalation gate has no failure/uncertainty signal — it only fires on the user literally typing 'swarm'/'delegate' or writing a long message. So on a hard problem the agent stays local and hotfixes instead of recruiting the planner." This is the architectural root of pain #2. |
| `swarm_bridge_autoloop`'s only escalation knob, `allow_fallback_planner`, **degrades DOWN** to a weaker fallback planner instead of escalating up; it is gated on the user remembering to type `allow-fallback`. | `local.py:89-116` | "The escalation knob's only direction is DOWN to a weaker fallback planner." There is no path that escalates to a stronger planner on difficulty. |

When the CUA *does* fail, the failure is laundered, not surfaced. `explainSparkError` substring-matches the error text into ~12 canned `{category,userLine,check,repair}` buckets and, for `builder_or_memory` failures, replies *"Builder memory is shaky… Ask me the same thing again and I will answer from the current thread"* (`errorExplain.ts:66-309`, the `ask-again` branch at `:289-294`). Telling the user to blindly retry is the opposite of escalation — it masks the failed dependency (`RL-13`). On the voice path, a broad `except Exception` swallows the error into "I answered in text because the voice audio step is not ready yet" with no escalation of a recurring failure (`runtime.py:4033-4042`).

### 1.3 Why this is the same disease as pain #1

A CUA that cannot hand a hard problem *up* has exactly one move left: solve it *locally*. The hotfix-debt literature names this precisely — "a CUA reaching for a local hotfix is the generic try-again loop" (`oss-harness-comparison`, Goose, https://www.openaitoolshub.org/en/blog/goose-ai-agent-block-review). And the CUA-orchestration research states the red line directly:

> A being-stuck / low-confidence / out-of-scope CUA must NEVER resolve itself with a local deterministic hotfix (route-specific regex, canned response, hard-coded click path) — that is the charter Stop-Ship Gate "a route-specific regex owns execution authority" and the exact compounding failure the user reports (`cua-orchestration` red_lines).

So pain #2 is the *generator* of pain #1. Close the escalation path and you cut off the supply of new local hotfixes at the source.

---

## 2. Target architecture — supervisor / orchestrator-worker

The SOTA for CUA ↔ higher-intelligence orchestration converges on a single shape across Anthropic Research, the OpenAI Agents SDK, and Google ADK: a **supervisor / orchestrator-worker** topology (`cua-orchestration` summary). The principle that makes it work is not a smarter CUA — it is a **bounded** one.

> The low-level GUI agent is the least reliable link (OSWorld ~38% Operator / ~73% Claude on first attempt; 3 of 4 desktop tasks fail), so reliability comes not from making the CUA smarter but from **BOUNDING its authority and forcing escalation** (`cua-orchestration` summary; OSWorld figures at https://www.siliconsnark.com/computer-use-agents-explained-why-openai-anthropic-and-perplexity-want-to-operate-your-laptop/ and https://coasty.ai/blog/computer-use-agent-comparison-best-ai-2025).

### 2.1 Altitude: who owns what

There are two roles, and the boundary between them is **non-negotiable**.

- **The PLANNER (higher intelligence)** owns long-horizon strategy AND the escalate / retry / replan / abort authority. It holds the durable plan in external memory so it survives context truncation, decomposes the goal, synthesizes worker reports between legs, and decides the next move. It is also the *fresh-context adversarial reviewer* of each proposed action (§4.4). The retry/move-on/abort decision lives here — never in the worker (`cua-orchestration` lessons, https://www.anthropic.com/engineering/multi-agent-research-system).

- **The CUA WORKER (executor)** owns only **bounded, scoped execution of one leg**. It receives a task envelope (§4.1), acts only inside it, runs an Evaluator after every tool result (§3, §4.2), and escalates on any defined trigger. It is structurally denied long-horizon authority: "the CUA is deliberately denied long-horizon authority — it executes one bounded leg and reports … This prevents the CUA from making a local decision (a quick regex/canned reply) that compounds, because the CUA structurally cannot choose strategy" (`cua-orchestration` lessons, https://www.anthropic.com/engineering/multi-agent-research-system).

This altitude split *is* the charter's per-surface responsibility model (`Builder owns context orchestration and domain reasoning`; `Spawner owns mission execution once authorized` — `RUNTIME_CHARTER.md:104-105`). The protocol enforces it.

### 2.2 The loop (diagram-as-text)

```text
                        ┌─────────────────────────────────────────────────────┐
                        │                     PLANNER                          │
                        │        (higher intelligence / Governor-fronted)      │
                        │  • holds durable plan in external memory             │
                        │  • decomposes goal → bounded legs                    │
                        │  • fresh-context adversarial reviewer of proposals   │
                        │  • OWNS escalate / retry / replan / abort            │
                        └───────────────┬───────────────────────▲─────────────┘
                                        │                        │
                  (1) bounded task      │                        │ (5) escalate_to_planner(
                      envelope          │                        │       reason, evidence,
                  objective + end-state │                        │       partial_state, screenshot )
                  + allowed surfaces    │                        │     — typed, first-class, FREQUENT
                  + explicit "do NOT"   │                        │
                                        ▼                        │
        ┌───────────────────────────────────────────────────────┴─────────────┐
        │                            CUA WORKER                                 │
        │                       (bounded execution only)                       │
        │                                                                      │
        │   ┌────────────┐   (2) act    ┌──────────────┐   (3) observe         │
        │   │  PROPOSE   │ ───────────▶ │   TOOL CALL  │ ───────────────┐      │
        │   │ one step   │              │ (read/low by │                │      │
        │   └─────▲──────┘              │   default)   │                ▼      │
        │         │                     └──────────────┘        ┌──────────────┐
        │         │                                             │  EVALUATOR   │
        │         │   continue (in-scope, confident,            │ diff observed│
        │         │   progress observed)                        │ vs expected  │
        │         └──────────────────◀──────────────────────────┤ end-state +  │
        │                                                        │ confidence + │
        │                                                        │ stall count  │
        │                                                        └──────┬───────┘
        │                                                               │
        │        (4) ESCALATION TRIGGER (any of §3) ────────────────────┘
        │            low confidence · N retries · ambiguity ·
        │            out-of-scope · consequential/irreversible ·
        │            novel error  ──▶  STOP. emit (5). do NOT improvise.
        └──────────────────────────────────────────────────────────────────────┘

Authority binding (every leg, the charter spine — RUNTIME_CHARTER.md:60-79):
  propose → validate → authorize → approve/interrupt → execute → sanitize → store → summarize → continue
  • read/low  → CUA may act inside the envelope
  • medium+   → emit `interrupt`; route to Governor/human; NEVER an `allow` the CUA grants itself (R-26)
  • degraded/failed/blocked → record as failure + escalation; NEVER a synthesized OK (R-27)
```

The reframing the research insists on: escalation is the **common path, not the exception**. Because ~3 of 4 desktop tasks fail on first attempt, "the goal is not a CUA that rarely needs the planner, but a CUA that escalates cleanly and often, with the planner absorbing the unreliability via retries/alternative strategies/human handoff" (`cua-orchestration` lessons, https://www.siliconsnark.com/computer-use-agents-explained-why-openai-anthropic-and-perplexity-want-to-operate-your-laptop/).

---

## 3. Escalation triggers — the signals that MUST hand UP

These are the signals that, when present, **require** handing up instead of being hotfixed locally. This list replaces the keyword/word-count gate in `sync.py:1217-1360` with a **capability/state-driven** trigger set, wired to fire automatically inside the action loop (the Evaluator step of §2.2), not only on a user-typed `/swarm evaluate`. The governing rule from the research:

> A low-confidence step is a **HELP REQUEST**, not a path to discard or to confidently guess. Reflexion's Actor/Evaluator/Self-Reflection split puts an explicit Evaluator between acting and committing; "Reflective Confidence" turns a sub-threshold score into an immediate diagnose-and-continue/escalate (`cua-orchestration` lessons, https://arxiv.org/html/2512.18605).

| # | Trigger | Concrete threshold / definition | Why it must escalate (not hotfix) |
|---|---------|----------------------------------|-----------------------------------|
| **T1** | **Low confidence / uncertainty** | Evaluator confidence on the just-executed step `< confidence_floor` (default `0.6`, mirroring the `voice_judge` pass bar at `voice_judge.py:63-72` but used to *escalate*, not to coerce a midpoint). | A sub-floor step is a help request. Guessing confidently is the wrong-action failure mode (`cua-orchestration`, Reflexion). |
| **T2** | **Repeated failure / no progress** | `N` retries of the same step with no observable state change. Default `N = 2` (the 3rd attempt escalates). A "stall" = two consecutive Evaluator diffs with no change toward the expected end-state. | Bound the loop with a declarative ceiling, not an open patch/retry loop — the r28 anti-pattern is "unbounded patch/retry" (`oss-harness-comparison` donts; AutoGen termination, https://microsoft.github.io/autogen/stable//user-guide/agentchat-user-guide/tutorial/termination.html). |
| **T3** | **Ambiguity** | The leg admits more than one plausible interpretation of the objective, OR the observed UI/page does not map unambiguously to the expected end-state. | Vague delegation causes the agent to *invent scope*; a clean boundary makes "this is ambiguous → escalate" a well-defined event (`cua-orchestration`, https://www.anthropic.com/engineering/multi-agent-research-system). |
| **T4** | **Out-of-scope** | The next required surface/domain/path is **not** in the envelope's `allowed_surfaces` (e.g. a path not in `service.py`'s `_normalize_allowed_domains`), or the action is on the envelope's explicit `do_NOT` list. A login wall or unexpected dialog is the canonical case. | The envelope boundary is what converts "out of scope" from a judgment call into a crisp boundary-violation signal to escalate on, "instead of improvising a route-specific click sequence (a local hotfix)" (`cua-orchestration`, https://www.anthropic.com/engineering/multi-agent-research-system). |
| **T5** | **Any consequential / irreversible action** | Charter Risk Tier **medium+**: submit, send, pay, delete, publish, deploy, secret-write, broad workspace mutation, mission launch (`RUNTIME_CHARTER.md:88-96`). | The CUA must never self-authorize these. "A deterministic fallback that 'just submits anyway' is exactly the self-authorized high-stakes action both OpenAI and Anthropic forbid" (`cua-orchestration`, https://help.openai.com/en/articles/10421097). Emit `interrupt`, route to Governor/human (`R-26`, `RL-13`). |
| **T6** | **Novel / unclassified error** | An error that does not map to a known typed failure code (Goose's six-type classification is the reference; a generic `try-again` is poor recovery). | "Classify failures and route capability-gap/ambiguity to the planner as an interrupt"; a generic retry hides the error class (`oss-harness-comparison`, Goose, https://www.openaitoolshub.org/en/blog/goose-ai-agent-block-review). A novel error is by definition outside the CUA's competence — it is the planner's call. |

**The defaults are conservative because the runs are unattended.** Per `R-08`, an autonomous CUA loop gets deny-by-default: "when no human is in the loop, an uncertain action must HALT and queue for review, not auto-resolve via a fallback" (`Hermes` cron-mode, https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py). T1–T6 are the detection set; the *resolution* when unattended is always halt-and-escalate, never a local fix.

**One trigger is enough.** The CUA does not weigh triggers or decide whether escalation is "worth it." Any T-fire is an unconditional STOP + emit `escalate_to_planner(...)` (§4.3). The decision of what to do *next* belongs to the planner, never the worker (`RL-13`, `R-25`).

---

## 4. The handoff contract

Escalation is a **typed, first-class, bidirectional handoff** with full prior context — not a silent fallback, not a console log, not a JSONL append nobody reads (the current `routeArbiter.ts:56-61` failure mode). The contract has four parts.

### 4.1 The bounded task envelope (planner → CUA)

The planner hands each leg a **ChangeManifest-style task envelope** (`R-23`). Required fields:

```text
CuaTaskEnvelopeV1 {
  objective:          string        // the single bounded goal of THIS leg
  expected_end_state: string        // an observable target the Evaluator can diff against
  allowed_surfaces:   string[]      // domains/paths/apps the CUA may touch (reconciled with
                                    //   service.py _normalize_allowed_domains)
  output_format:      schema        // the distilled result shape the CUA returns to the planner
  do_NOT:             string[]      // explicit prohibitions (submit, pay, leave domain, etc.)
  risk_ceiling:       RiskTier      // the max tier the CUA may act on without `interrupt` (default: low)
  confidence_floor:   number        // T1 threshold (default 0.6)
  stall_ceiling:      int           // T2 threshold (default N=2)
}
```

The envelope is what makes every §3 trigger *crisp*. Without `expected_end_state` the Evaluator has nothing to diff; without `allowed_surfaces` and `do_NOT` there is no boundary to violate; without `risk_ceiling` there is no line for `interrupt`. "Vague delegation ('research the shortage' / 'fix the page') causes duplication, gaps, and the agent inventing scope" (`cua-orchestration`, https://www.anthropic.com/engineering/multi-agent-research-system). Enforcement: schema validation of the envelope (`R-23`).

### 4.2 The Evaluator step (inside the CUA, after every tool result)

After **every** CUA tool result, an Evaluator step runs (`R-24`): it diffs observed state (e.g. a screenshot/DOM snapshot) against `expected_end_state`, computes a confidence/progress signal, and increments a stall counter when there is no observable change. This is the Reflexion Actor/Evaluator/Self-Reflection split made mandatory. The absence of exactly this step is why CUAs drift: "`service.py` today has no confidence/retry-ceiling/stall detector — that absence is precisely why CUAs 'drift into local hotfixes'; there is no mechanism that converts being-stuck into an escalation" (`cua-orchestration`, https://arxiv.org/html/2512.18605). The Evaluator is the thing that fires T1/T2/T3.

### 4.3 The escalation handoff (CUA → planner)

Escalation is an **explicit, typed tool the CUA calls** — modeled on the OpenAI Agents SDK handoffs, which "expose handoffs as typed tools with filtered context and reason/priority/summary metadata, one per destination" (`oss-harness-comparison`, https://openai.github.io/openai-agents-python/handoffs/). The contract:

```text
escalate_to_planner({
  reason:        TriggerCode,    // one of T1..T6 (typed, never a free-text guess)
  priority:      Priority,       // derived from risk_ceiling crossing / irreversibility
  summary:       string,         // distilled state, NOT a raw screen dump
  evidence:      EvidenceRef[],  // the trace: envelope, steps taken, Evaluator diffs
  partial_state: object,         // what was accomplished, so the leg can resume not restart
  screenshot:    artifactRef     // stored as an artifact, summarized — never sprayed into context
})

escalate_to_human()             // a first-class tool for the medium+ / consequential path (T5)
```

Three properties are load-bearing:

1. **Bidirectional with full prior context.** "A worker hands the conversation back UP to the supervisor with full prior context" (`cua-orchestration`, https://developers.openai.com/cookbook/examples/orchestrating_agents). The planner receives the whole trace, not a lossy summary that forces it to re-derive what happened.
2. **`escalate_to_human()` is first-class, not a last resort.** For any T5 (consequential/irreversible) the path is watch-mode / take-over / human confirmation — the Operator model: "ASK FOR CONFIRMATION before any consequential or irreversible action (submit, send, pay, delete), require WATCH MODE on sensitive surfaces, TAKE-OVER for credentials" (`cua-orchestration`, https://help.openai.com/en/articles/10421097).
3. **Escalation realizes the charter, it does not bypass it.** "Escalation is the CUA emitting evidence upward; the Governor/planner owns the next move" — this *is* `surfaces submit evidence … they do not own authority` (`cua-orchestration`, https://developers.openai.com/cookbook/examples/orchestrating_agents; `RUNTIME_CHARTER.md:100`).

### 4.4 Graceful-degradation signaling + checkpoint/resume

A failed leg must not restart the whole run, and a failure must not be swallowed. Two LangGraph-grounded mechanisms (`oss-harness-comparison`, https://docs.langchain.com/oss/python/langgraph/durable-execution):

- **Model degradation explicitly.** When a tool is failing, tell the agent/planner so it can adapt — do not paper over it. "A legitimate degradation surfaces the failure to the agent/planner and adapts or resumes from a checkpoint; a failure-MASKING fallback swallows it and returns a canned 'success'" (`cua-orchestration`, https://www.anthropic.com/engineering/multi-agent-research-system). This is the principled alternative to `errorExplain.ts`'s canned `{userLine,check,repair}` buckets and the `runtime.py:4033-4042` silent voice fallback.
- **Checkpoint/resume.** LangGraph checkpoints per node and "persists on interrupt/failure, requires idempotent workflows; `interrupt_before` is a durable approval pause" (`oss-harness-comparison`, https://docs.langchain.com/oss/python/langgraph/durable-execution). The `interrupt` verdict (T5) becomes a **durable** pause, not the volatile pending state the charter warns expires as context, not authority (`RUNTIME_CHARTER.md:116`). `partial_state` in the handoff (§4.3) is what makes resume-not-restart real.

---

## 5. Hard rules for the CUA (mapped to Red Lines)

These are absolute. Each maps to a Red Line in `01_RULESET.md`; crossing one is a stop-ship condition.

### 5.1 The CUA must never self-authorize a consequential action. → `RL-13`, `R-26`

Any medium+ Risk-Tier step (submit/send/pay/delete/publish/deploy/secret-write/broad mutation/mission launch) emits an **`interrupt`** verdict and routes to the Governor/human. The CUA never grants itself an `allow`. The default authority tier is **read/low**; everything above it is escalated.

> The low-level CUA must NEVER self-authorize a consequential/irreversible action … those require explicit confirmation/human approval or an 'interrupt' verdict from the Governor, never an 'allow' the CUA grants itself (`cua-orchestration` red_lines; `RUNTIME_CHARTER.md:88-96`).

### 5.2 The CUA must never resolve being-stuck with a local deterministic hotfix. → `RL-01`, `R-25`

A regex, a canned response, a hard-coded click path, or a synthesized OK result is forbidden as a stuck-state resolution. The only legal move when stuck is **escalate** (§3). This is the charter Stop-Ship Gate "a route-specific regex owns execution authority" (`RUNTIME_CHARTER.md:170`) reaching the CUA path. It is also the rule that severs pain #2 from pain #1: with no local seam to hotfix into, the CUA cannot mint a new shadow-authority shortcut.

> A being-stuck / low-confidence / out-of-scope CUA must NEVER resolve itself with a local deterministic hotfix … that is the charter Stop-Ship Gate and the exact compounding failure the user reports (`cua-orchestration` red_lines).

### 5.3 The CUA must never record a degraded/failed/blocked step as success. → `RL-08`, `R-27`

`success` / `failure` / `partial` / `rolled_back` are authority-bound; a blocked action cannot be re-represented as executed by editing the ledger result later (`RUNTIME_CHARTER.md:70-79`). A failed leg is recorded as **failure + escalation**, with a `reason_code` — never `None`/`''`/`{}`/a synthesized OK/a midpoint score. Note the existing offender the protocol must fix: `_governor_outcome` conflates `degrade` with missing-ledger evidence (`kernel.py:1169-1183`); split `degrade` from `incomplete_evidence` so a missing tool ledger is a hard non-executable outcome, not a soft "proceed cautiously."

> A degraded or failed CUA step must NEVER be recorded/returned as success — masking a root cause behind a fallback that synthesizes an OK result is forbidden (`cua-orchestration` red_lines). A tool ledger is evidence, not a permission grant (`R-27`).

### 5.4 The CUA must never own the escalate / retry / abort decision. → `RL-12`, `R-25`

The worker self-authors **no** authority. It detects triggers and hands up; the planner decides retry/replan/abort. "A worker choosing to 'just keep trying' is the cooperation failure" (`cua-orchestration` red_lines). This is the direct antidote to `local.py:89-116`, whose only knob degrades *down* to a weaker planner, and to `sync.py`'s `hold_local` default.

### 5.5 The planner must treat the CUA's proposal as UNTRUSTED INPUT and have a first-class `escalate` verdict. → `RL-12`

When the planner reviews a proposed CUA action, it frames that action as **data, not instructions**, and routes uncertainty *up* — it must not be forced into a binary that pressures a local approve. This mirrors Hermes' smart-approve (strip comments, XML-wrap, ignore embedded directives, return approve/deny/**ESCALATE**) and Anthropic's fresh-context reviewer that "sees only the diff and the criteria," so "the agent doing the work isn't the one grading it" (`cua-orchestration`, https://www.anthropic.com/engineering/multi-agent-research-system; `Hermes`, https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval). A monitor model may additionally **pause or abort** the run on anomalous or prompt-injected behavior — page/image-embedded instructions are an attack surface (`R-28`, `cua-orchestration` dos).

---

## 6. Observability requirement

Reliability here is **enforced by observability, not hope.** The OSWorld data is the reason: ~3 of 4 desktop tasks fail on first attempt, so you cannot ship a CUA path you cannot trace and replay.

- **Full tracing.** Instrument the entire CUA loop with **OpenTelemetry GenAI spans** capturing the charter's observability list: envelope, candidate evidence, chosen action, authorization verdict, tool-lifecycle stage, sanitized output, and run verdict (`R-17`; `RUNTIME_CHARTER.md:118-133`; `cua-orchestration`, https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide and https://arize.com/ai-agents/agent-observability/). The release gate is blunt: "if you can't explain why it acted, it is not promotion-ready" (`RUNTIME_CHARTER.md:133`).

- **Golden-task replay.** Maintain a small (~20) golden set of real CUA journeys and run **scheduled replay with deterministic fixtures** (recorded tool/screen responses) that bypass live calls, against current prod (`R-19`). The point is causal, not decorative: "a golden-trace replay would have caught each of the 28 spark-cli hotfix rounds as a regression instead of accreting r1..r28" (`cua-orchestration`, https://www.digitalapplied.com/blog/agent-observability-2026-evals-traces-cost-guide). **Deterministic checks belong in this eval/replay/verifier lane — never in the runtime execution-authority path** (`RL-12` / Legacy Plane Retirement). That is the resolution of the determinism tension: determinism is a *verification* tool, not an *authority*.

- **Three-layer eval stack.** Deterministic unit checks first → LLM-as-judge for subjective quality → production trace sampling for drift (`cua-orchestration`, https://arize.com/ai-agents/agent-observability/). And per `R-20`, instrument **change-failure-rate per self-evolving component**: a rising-hotfix component is not release-candidate ready (`hotfix-debt-theory` DORA, https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance).

One self-evolution guard rail bounds all of the above (`RL-17`): self-evolution must never mutate the **verifier logic, the golden tasks, the model config, or the authority policy** to make a failing run pass — "the deepest form of failure-masking" (`cua-orchestration` red_lines; `RUNTIME_CHARTER.md:150`). The grader is never writable by the graded.

---

## 7. Migration plan

The end state: the LLM planner/arbiter is the **origin** of route authority (`RL-02`), the regex planes are demoted to **evidence that can only narrow, never grant** (`R-02`), and escalation is **confidence/failure-driven and automatic** (`R-24`, `R-25`). Two tracks get us there.

### 7.1 Promote the arbiter `shadow → enforce` behind a real promotion gate

The blocker is structural: `RouteArbiterMode` is type-locked `'off' | 'shadow'` with **no `enforce` value** (`routeArbiter.ts:12`), and `telegramIntentGateV2Mode` defaults to `'enforce_safe'` (`telegramIntentGate.ts:770`) — the regex enforces, the intelligence observes. The migration inverts this without a flag-day risk:

1. **Add the `enforce` value to the type** and a typed promotion path `off → shadow → enforce` (`RL-12` requires the path to exist). This is the precondition for the legacy plane ever being retired.
2. **Let the arbiter BLOCK on disagreement before full enforce.** Even in the migration window, "the LLM verdict should be able to BLOCK a regex route on disagreement even before full enforce" (`routeArbiter.ts` real_fix). The arbiter going from telemetry to a *veto* is the first real authority it holds.
3. **Gate promotion on ledger agreement.** "Once shadow agreement with regex exceeds a threshold on the ledger, flip arbiter to authority and regex to veto-only" (`routeArbiter.ts` real_fix). This is the `R-19` golden-trace/replay discipline doing double duty as the promotion gate — a derived, artifact-backed flip (`RL-15`), not a hand-set boolean.
4. **At `enforce`, invert the gate.** The LLM intent envelope becomes the SOLE source of route authority; `telegramIntentGateV2` regex becomes a deny-list/veto for clearly-unsafe routes only, and `routeFirewall`'s `evaluateDeterministicRoute` is demoted to emit `route_candidate` EvidenceRefs (confidence + reason), never `allow` (`R-02`, `routeFirewall.ts:403-521` real_fix). Remove `routeVerdict.allow` from the `preliminaryAllow` conjunction at `telegramActionAuthority.ts:79-102` (`RL-02`).
5. **Make retirement falsifiable.** Register the demoted planes in the legacy-authority inventory via a **computed source scan**, not a hand list — today `legacyAuthorityInventory.ts:1-289` is self-attested and omits the two largest live planes (`RL-16`). The scan reconciliation is what proves `can_route_turns = false`.

A degraded-arbiter condition must be **loud**, not absorbed: on sustained arbiter failure (currently swallowed into a JSONL record and a `console.warn` at `routeArbiter.ts:188-205`), raise operator visibility and, once `enforce` exists, fail *safe* by requiring confirmation rather than letting the regex auto-execute interruptive routes (`routeArbiter.ts:188-205` real_fix; `RL-08`).

### 7.2 Replace keyword escalation with a confidence/failure-driven trigger

Retire the keyword/word-count gate in `evaluate_swarm_escalation` (`sync.py:1217-1360`) and the down-only `allow_fallback_planner` knob (`local.py:89-116`):

1. **Wire the Evaluator (§4.2) into the action loop** so T1–T6 fire automatically after every tool result — not only on a user-typed `/swarm evaluate` (`R-24`; `sync.py:1217-1360` real_fix: "feed in run-state signals … and let a planner LLM decide escalate vs continue. Wire it to fire automatically inside the action loop").
2. **Invert the fallback posture.** "On low confidence or failure, escalate to the higher-capability planner automatically; make the fallback planner an explicit, logged degradation with a recorded reason, not a quietly-flagged command suffix" (`local.py:89-116` real_fix). `hold_local` is no longer the default — **escalate** is.
3. **Replace the canned failure path.** On failure, emit a structured failure event into the escalation evaluator so the planner decides retry/repair/escalate; reserve canned strings for the final user-facing summary *after* a root-cause attempt, and never instruct a blind "ask me again" (`errorExplain.ts:66-309` real_fix; `RL-13`).
4. **Bind the typed escalation tool.** Ship `escalate_to_planner(...)` and `escalate_to_human()` (§4.3) as first-class tools (`R-25`), and tie each CUA action class to its required verdict so medium+ → `interrupt` is a unit invariant, not a convention (`R-26`).

### 7.3 Sequencing and the exit criterion

Land the cheapest-highest-yield checkers first (consistent with `01_RULESET.md` §6): the **`enforce`-mode type + promotion gate** (unblocks `RL-12`), the **Evaluator-in-loop trigger set** (delivers `R-24`/`R-25` and kills `hold_local`), and the **computed legacy-plane scan** (makes `RL-16` falsifiable so retirement is provable). The exit criterion is a single derived gate (`RL-15`): the CUA surface reaches release-candidate only when its route authority originates in the Governor/arbiter (no regex `allow` in the conjunction), its escalation is confidence/failure-driven, and a fresh source scan confirms zero high-agency legacy local gates — all proven from artifacts, never asserted as a boolean.

---

### Sibling documents

- `00_README.md` — orientation, the two pains, how the doc set fits together.
- `01_RULESET.md` — the anchor: Prime Directives, `RL-01`..`RL-18`, `R-01`..`R-28`, the Enforcement Model. The canonical home of every ID cited here.
- `02_REAL_FIX_PLAYBOOK.md` — how to shape a real fix; the legitimate-fallback vs failure-masking taxonomy (the discipline behind `R-27` / `RL-08`).
- `03_CUA_ESCALATION_PROTOCOL.md` — **this document.** The planner↔CUA contract and the escalation protocol.
- `04_AUDIT_FINDINGS_AND_BACKLOG.md` — the 51 offenders, grouped by root cause, sequenced into a checker-build backlog (the CUA offenders cited here in context).
- `05_EXTERNAL_HARNESS_LESSONS.md` — the 51 research lessons (Hermes, OpenClaw, Anthropic, OSS, hotfix-debt theory, CUA orchestration) with source URLs.
