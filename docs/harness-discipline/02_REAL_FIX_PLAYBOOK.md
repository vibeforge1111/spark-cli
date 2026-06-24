# Spark Harness Discipline: What a Real Fix Looks Like

> Source of truth: `docs/harness-discipline/`. Grounded in the 2026-06-24 Spark harness audit (51 offenders) + Hermes/OpenClaw/Anthropic/OSS research (51 lessons).

This is the founder's #1 ask: a concrete, repeatable definition of a *real fix* versus a *hotfix*, with a procedure the team (and the self-evolution loop) is held to. It is the operational companion to `01_RULESET.md` — where that doc defines the Red Lines (`RL-01`..`RL-18`) and Rules (`R-01`..`R-28`), this doc shows how to satisfy them when you sit down to fix something. The anti-pattern catalogue here is the human-readable index into `04_AUDIT_FINDINGS_AND_BACKLOG.md`; the external theory is sourced from `05_EXTERNAL_HARNESS_LESSONS.md`. CUA-specific escalation lives in `03_CUA_ESCALATION_PROTOCOL.md`.

The thesis, in one sentence: **a hotfix smuggles a policy decision into a mechanism site and lets it ossify into shadow authority; a real fix names the class at its root cause, moves policy into auditable data, and lets one mechanism enforce it — then retires every patch the fix obsoletes.**

---

## 1. Hotfix vs Real Fix

### 1.1 The sharp definition

A **hotfix** answers *this specific failing instance*. It edits a mechanism site (a router, a reply path, an error handler) to encode a policy decision inline, so the next instance of the same class forces another edit at another site. It works, it ships, and it quietly becomes the authority for every input that resembles the one it was written for.

A **real fix** answers *the whole class*. It performs the [5-Whys](https://www.atlassian.com/incident-management/postmortem/5-whys) descent until it reaches the system property that *allowed* the failure ("why did any input reach execution without an envelope?"), separates the policy from the mechanism at that seam, expresses the policy as data, lets one generic engine enforce it, and pins the invariant — not the symptom string — with a test. It leaves the codebase *smaller* (one mechanism, N data rows) rather than larger (N branches).

This is not a stylistic preference. Spark evolves itself, so [tech debt is contagious by mechanism](https://arxiv.org/html/2209.01549v3): high-debt code raises the rate of *new* debt because the next self-evolution pass reads the repo as house style. The audit's `domain-chip-memory` slice is this contagion at maximum scale — ~250+ literal `in question_lower` branches that taught the chip its whole answering plane should be a lookup table (`providers.py:1828-1830`). Every hotfix that ships trains the system to make more.

### 1.2 The criteria table

Apply this to any proposed change. If any row lands in the **Hotfix** column, the change is a hotfix until proven otherwise — and a hotfix may ship only under §5.

| Dimension | Hotfix (reject as a fix) | Real fix (accept) | Theory |
|---|---|---|---|
| **Target** | Pins the symptom-*instance* — this message, this benchmark question, this OS error string. | Names the *class* at its root cause; prevents the whole family. | [5 Whys / fix-the-class](https://www.atlassian.com/incident-management/postmortem/5-whys) |
| **Policy/mechanism** | *Edits the mechanism to encode the policy* — a regex/branch inside the router decides authority, so each new case re-edits the router. | *Separates them* — policy is declarative data; one mechanism reads it. | [Policy/mechanism separation (Brinch Hansen, Hydra)](https://swift.sites.cs.wisc.edu/classes/cs736-fa06/papers/hydra-policy-mechanism.pdf) |
| **Branch count** | *Adds* a regex / canned / fallback branch — the surface grows by accretion. | *Removes the need* for one — the new case is a data row in an existing engine, or it disappears into a canonicalization pass upstream. | [Shotgun surgery](https://en.wikipedia.org/wiki/Shotgun_surgery) |
| **Test** | Pins a *literal string* (`assertIn("…", reply)`) — freezes the workaround. | Pins the *invariant* over a family of inputs (no execute without `AuthorizationDecisionV1`). | [Testing anti-patterns](https://blog.codepipes.com/testing/software-testing-antipatterns.html) |
| **Failure handling** | Returns a *success-shaped* value on failure (None / `''` / `{}` / canned OK / midpoint score) — masks the root cause. | *Fails closed* and emits a traceable, actionable reason code that an operator or the planner can act on. | [Hermes fail-closed](https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime); [Anthropic actionable errors](https://www.anthropic.com/engineering/writing-tools-for-agents) |
| **Retirement** | Becomes *permanent* — no owner, no ticket, "for now" forever. | Leaves a named *retirement owner* and updates the legacy inventory; the legacy plane only ever shrinks. | [Normalization of deviance](https://en.wikipedia.org/wiki/Normalization_of_deviance); `RL-15`, `R-15` |
| **Trend signal** | Hotfix velocity mistaken for throughput; the component's change-failure-rate rises unmeasured. | Change-failure-rate is instrumented per component; a rising-hotfix component is *not* release-candidate ready. | [DORA CFR](https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance); `R-20` |

The two pains the founder reported are the first two rows compounding. The `r28-longpath-guard` treadmill (`/Users/alchemistab/.spark/tools/spark-cli/.git`) is the "adds a branch / becomes permanent" rows: twenty-eight rounds of point-fixes bolted onto the pin path (`cli.py:823-855`) because the dominant move is *add one more guard*, and nothing says stop.

---

## 2. The Anti-Pattern Taxonomy

Eight categories surfaced in the audit. Each is defined, given a real Spark specimen with `file:line`, and paired with its real-fix shape and the governing IDs. Every specimen below is a committed offender from the findings; none is hypothetical.

### 2.1 `route-regex-authority` — a regex owns execution authority

**Definition.** A route-specific regex / keyword / canned classifier produces an `allow`/`deny` verdict that is a precondition for execution. The pattern *is* the authority, not evidence feeding the authority. This is the headline Stop-Ship Gate (`RUNTIME_CHARTER.md:170`).

**Spark specimen.** `evaluateDeterministicRoute()` in `routeFirewall.ts:403-521` is a ~40-route, ~30-predicate regex classifier whose `{allow, reason, confidence}` verdict is a hard gate on execution — it returns `allow:true` for `concrete_project_build`, `explicit_memory_write`, `explicit_schedule_delete` directly from regex matches on user text. It even hardcodes a single QA prompt's temp path, `appdata\local\temp\spark-telegram-level5-smoke.txt`, as a recognizer (`routeFirewall.ts:235`). The qa-evidence-lane chip does the same at chip-activation granularity: `should_activate()` decides authority from `POSITIVE_PATTERNS`/`NEGATIVE_GENERIC_PATTERNS` over raw text (`routing.py:5-38`).

**Real-fix shape.** Demote the detector to an *evidence adapter* that emits `route_candidate` evidence_refs only; a regex may **narrow** (veto) but never **grant** (`R-02`). The `allow`/`deny` must originate from a single Governor that the surface did not author. Delete per-prompt recognizers like the level5 smoke path — QA prompts are recognized by the planner, not by a production regex. Governs `RL-01`, `RL-02`, `R-01`, `R-02`, `R-03`.

### 2.2 `shadow-router` — a second router re-derives intent and can disagree

**Definition.** A second classifier sits beside the real one and re-derives intent from raw input (argv, text), so the two can diverge — one path becomes a bypass or a false-block of the other. Often the "Governor" is then reconstructed from the shadow router's own verdict, making the verification circular.

**Spark specimen.** `main()` enforces authority by re-deriving intent from `sys.argv` via its own tokenizer (`approval_required_for_command(...)`) and *then separately* dispatches the already-parsed argparse `Namespace` — two routers from one command (`cli.py:17925-17932`). In the Telegram stack the circularity is explicit: `build_governor_decision_from_bridge_authority()` fabricates a `governor-decision-v1` from the bridge's *own* verdict and then "checks" the decision against itself (`bridge_authority.py:121-222`); `preliminaryAllow` ANDs the regex `routeVerdict.allow` in front of a Governor decision minted from the same inputs (`telegramActionAuthority.ts:98-127`).

**Real-fix shape.** Bind authority to the *parsed/typed action*, not a re-tokenized string (`R-01`). The surface submits envelope + evidence to a real Governor and consumes a decision it did **not** author (`RL-02`). Delete the regex conjunct from the execution precondition. Governs `RL-02`, `R-01`, `R-03`.

### 2.3 `canned-response` — a hardcoded reply keyed on a magic substring

**Definition.** A specific failure or question is answered by a fixed string selected by substring-matching the underlying error or the user's text. The reply is plausible; the root cause is hidden behind it.

**Spark specimen.** `user_safe_startup_detail()` substring-matches the raw startup error (`'TELEGRAM_RELAY_SECRET'`) and swaps in a fixed remediation string (`cli.py:14933-14939`). At benchmark scale, `identity_and_community_rescue()` is a wall of literal-phrase→literal-answer branches — it returns hardcoded `'a sunset with a palm tree'`, `'Liberal'`, `'Single'` keyed to eval tokens (`provider_rescue_identity.py:6-173`); `mission-size-classifier.ts:104-116` checks equality against the literal phrase `'did you understand what i said'` and returns a fixed classification.

**Real-fix shape.** Have the producing layer emit a structured error **code**; map codes→remediation in one registry, never pattern-match the rendered message (`R-09`). Answers come from data + model extraction; names/facts/dates/personas are never literals in code (`R-10`). Delete the rescue plane; gate eval gains on a held-out set so memorization is detectable (`R-11`). Governs `RL-09`, `RL-10`, `R-09`, `R-10`, `R-11`.

### 2.4 `failure-masking-fallback` — a failure returned as a success-shaped value

**Definition.** The *masking* variant of a fallback: on error it returns None / `''` / `{}` / a synthesized OK / a midpoint score, so a failure flows downstream as if it succeeded. This is the dangerous twin of a legitimate defensive fallback (see §3.4).

**Spark specimen.** `_parse_score()` returns `5` (the ambiguous midpoint) when the judge response is empty or unparseable, laundering a judge outage into a real-looking 0.5 that corrupts the gate (`voice_judge.py:63-72`). `try_spark_character_fallback` returns a canned in-character reply whenever the bridge is in `bridge_error`/`disabled`/`stub`, so a backend failure reads as a normal successful turn (`runtime.py:808-856`). `errorExplain.ts:66-309` converts any failure into a canned `{userLine,check,repair}` bucket and tells the user to "ask me the same thing again" instead of diagnosing.

**Real-fix shape.** A judge/scorer failure surfaces as an explicit error/None, never a numeric midpoint (`R-12`). A degraded model reply is recorded as a *degrade with a reason code*, never silently swapped for templated text (`R-18`). The single line that separates a legitimate fallback from a masking one: does it surface the failure (decline/escalate/unavailable) or fabricate success? Governs `RL-08`, `R-06`, `R-12`, `R-18`.

### 2.5 `legacy-detector-authority` — a retained detector still finalizes authority

**Definition.** A historical detector that the charter says must be evidence-only still constructs envelopes, sets `authority_state`, finalizes tool ledgers, or synthesizes approval — it has not been demoted, only kept.

**Spark specimen.** `authorize_legacy_tool_call()` sets `authority_state='executable'` itself, calls `kernel.authorize()`, and returns a fully-minted allow + tool ledger; worse, it *fabricates* a `human_confirmation` approval_ref from `selected_intent.confidence=='explicit'`, masking the very approval gate it claims to honor (`legacy_turn_intent.py:595-665`). `is_dirty_update_failure()` keys control flow on the human-readable git error string (`cli.py:886-892`).

**Real-fix shape.** Strip the detector of any ability to emit `AuthorizationDecision`/`ToolCallLedger`; reduce it to `parse → evidence_ref list` (`RL-03`). Never synthesize human-confirmation evidence from a confidence heuristic — approval must be an out-of-band human signal (`RL-04`). Return typed failure reasons and branch on the type, never on the rendered message (`RL-09`, `R-09`). Governs `RL-03`, `RL-04`, `RL-09`.

### 2.6 `temporary-became-permanent` — a "for now" patch with no exit

**Definition.** A point-fix for one environment/edge bolted onto a path, with no retirement owner, that accretes into the architecture. The r-round cadence and the god-files are the signature.

**Spark specimen.** The module-pin path stacks git-recovery special cases — merge-base, then is-shallow, then `fetch --deepen=50` (a magic guess), then proceed anyway with `'(ancestry undecidable, shallow history)'` (`cli.py:823-855`); the literal `hotfix/r28-longpath-guard` tip is this lineage (`/Users/alchemistab/.spark/tools/spark-cli/.git`). `cli.py` reached **17,936 lines** (`cli.py:1-17936`) and `index.ts` **10,152 lines** (`index.ts:1-10152`) past a 3,000-line cap that already named them.

**Real-fix shape.** Replace the stacked guards with one full-fidelity fetch/verify primitive that **fails closed** on true ambiguity rather than proceeding (`R-06`); factor OS/path/clone-shape into one tested adapter. A quick-win is *labeled a stopgap and paired with the named long-term mechanism* (`R-15`). Enforce the line-count redline in CI (`R-21`). Governs `RL-08`, `R-06`, `R-15`, `R-21`.

### 2.7 `cua-local-reaction` — a stuck CUA hotfixes instead of escalating

**Definition.** When the computer-use agent hits failure, ambiguity, or out-of-scope state, it has no first-class way to hand the problem *up*, so it improvises a local fix. This is pain #2, and it is the engine that mints pain #1.

**Spark specimen.** `evaluate_swarm_escalation` — the **only** escalation-to-higher-intelligence path — decides by keyword substring (`'swarm'`,`'delegate'`,…) plus `len(task.split()) >= 40`; failure, retries, ambiguity, and stuck-state are **not** triggers, and the default is `escalate=False, mode='hold_local'` (`sync.py:1217-1360`). The one programmatic planner knob only degrades *down* to a weaker fallback planner, gated on the user typing `allow-fallback` (`local.py:89-116`).

**Real-fix shape.** Make escalation capability-driven, not keyword-driven: feed run-state signals (consecutive failures, low confidence, repeated identical retries, Governor blocks, novel error class) into an Evaluator that fires *inside* the action loop, and escalate as a typed, first-class handoff (`R-24`, `R-25`). The full protocol is `03_CUA_ESCALATION_PROTOCOL.md`. Governs `RL-12`, `RL-13`, `R-23`, `R-24`, `R-25`, `R-27`.

### 2.8 `benchmark-overfit` — an answer-key baked into the live path

**Definition.** A deterministic answer-key (eval personas, dated question strings, world-fact lookups) is committed into the live answering path so a benchmark passes via memorized strings rather than reasoning.

**Spark specimen.** `_question_aware_rescue` runs *ahead* of real extraction and returns immediately if it matches, so the canned plane wins over reasoning for any benchmarked question (`providers.py:1828-1830`). The personas are hardcoded (`if "alice" in question_lower: return "alice"`, `memory_queries.py:75-78`); world facts are 2-entry dicts (`_PLACE_TO_STATE={'stamford':'Connecticut'}`, `memory_factoid_answers.py:10-90`); temporal answers are keyed to verbatim eval phrases like `'pride festival'` (`provider_temporal_rescue.py:132-238`).

**Real-fix shape.** A deterministic answer-key must never be baked into the live answering path to pass a benchmark (`RL-10`); a rescue/canned plane must never run ahead of real model/retrieval reasoning (`RL-11`). Gate eval improvements on a **held-out** set — a benchmark pass via memorized strings is a stop-ship (`R-11`). Keep general capability (anchor-date arithmetic) and strip every scenario-specific phrase priority. Governs `RL-10`, `RL-11`, `R-10`, `R-11`.

---

## 3. The Real-Fix Protocol

A numbered, repeatable procedure. Run it top to bottom for any non-trivial change. Steps map to the Rules they satisfy.

### Step 1 — Reproduce, with a failing artifact

Reproduce the failure into a concrete artifact: a failing test, a captured trace, a command transcript with output. No reproduction, no fix — you cannot prove a class is closed if you cannot show the instance open. This is the [Aider verify-loop](https://aider.chat/docs/usage/lint-test.html) precondition: there must be a check that runs and fails *now*.

### Step 2 — 5-Whys to the class

Run [5 Whys](https://www.atlassian.com/incident-management/postmortem/5-whys), but aim each "why" at the *system*, not the input. The terminal "why" must name a **class** and a root cause — "any input of shape X reaches execution without an `AuthorizationDecisionV1`" — never "this message was misrouted." If the honest answer to "why did this happen" is "we never wrote a branch for it," you are about to write a hotfix; keep descending. Symptom-pins are rejected (`R-05`).

> Worked example. *Symptom:* `spark verify --deep` ran without a prompt. *Why?* The enforced-class set omits its class. *Why?* `high_cost_execution` is in `requires_approval=True` but excluded from `APPROVAL_ENFORCED_ACTION_CLASSES` (`cli.py:10963-11003`). *Why?* A second filter set was layered on to suppress a class the team didn't want to prompt on, instead of modeling it. *Root class:* two sources of truth for "enforced" can silently disagree. The real fix is one source of truth (`RL-05`), not adding the one class back.

### Step 3 — Find the policy/mechanism seam

Locate where the *decision* (policy) is currently fused into the *executor* (mechanism). This is almost always a regex/branch/string-match doing double duty. The [Brinch Hansen/Hydra separation principle](https://en.wikipedia.org/wiki/Separation_of_mechanism_and_policy) is the lens: every case that forces you to edit the mechanism is a case where policy is living in the wrong layer. The 118-regex/962-fallback/138-canned sites that *decide* are all seam violations.

### Step 4 — Fix at the seam: policy becomes data, mechanism enforces, fail closed

Three moves, together:

1. **Policy becomes data.** Express the rule as a declarative manifest row (pattern / risk tier / escalation target) evaluated by one generic engine — a new policy is *not* a new core branch (`R-16`). This is the [Hermes `DANGEROUS_PATTERNS` discipline](https://github.com/NousResearch/hermes-agent/issues/5528): twenty-eight hotfix rounds collapse into twenty-eight data rows reviewed by one code path.
2. **Mechanism enforces.** One central authority owned by the harness core; surfaces hold no local policy copy (`R-03`). Re-derive authority from a stored canonical object at execution time, [the way OpenClaw re-validates the approved plan rather than the approval-time string](https://docs.openclaw.ai/tools/exec-approvals). Normalize untrusted input to **one canonical form upstream of all rules** so you stop fighting evasions per-round (`R-07`) — [Hermes `_normalize_command_for_detection`](https://deepwiki.com/NousResearch/hermes-agent/5.4-security-and-command-approval).
3. **Fail closed.** When coverage is incomplete, refuse or escalate — never proceed best-effort. [OpenClaw refuses approval rather than guess when it cannot bind a concrete operand](https://github.com/openclaw/openclaw/security/advisories); a fallback is legitimate only if it fails closed and emits a traceable reason (`R-06`). Pair the guard with *every sibling path* to the same effect, or it is "unpaired theater" and breeds the next round ([Hermes](https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py); `RL-18`).

### Step 5 — Write a checker/test that pins the root cause, not the symptom string

Write the regression as an **invariant over a family of inputs**, not an assertion on one literal reply (`R-19`; see §4). The test should fail for the *entire class* before the fix and pass for the entire class after. Where the class is structural ("no legacy detector may finalize a ledger"), prefer a *checker* (an AST/scan) over a unit test, so the invariant holds as the repo grows — this is how the [SWE-agent lint-before-apply boundary](https://arxiv.org/pdf/2405.15793v1) catches violations at the mutation boundary instead of downstream.

### Step 6 — Verify LIVE

Run the verifier against real execution until it is green — not a fake or memorized pass. "Not success until the verifier runs green live" is the [Aider reflection-loop](https://aider.chat/docs/usage/lint-test.html) and [Anthropic's "show evidence rather than asserting success"](https://code.claude.com/docs/en/best-practices) rule. A literal-pinned or canned pass is forbidden; the audit found a *fake* gate (a `cpm` literal) precisely because nothing required live proof. Address root causes, not symptoms — *do not suppress the error to make the check go green.*

### Step 7 — Retire every legacy patch the fix obsoletes

A real fix that leaves the patches it replaces in place has not closed the class — the old branch still owns the decision for the inputs it matches. Delete them, and update the **auto-generated** legacy inventory (`RL-16`). The inventory must be **computed from a source scan**, never a self-attested hand list — the audit found `legacy_authority_inventory.py:81-200` is a hand-curated array that omits the two largest live planes (`routeFirewall.ts`, `naturalRouteDecision.ts`), so "plane retired" was unfalsifiable. This is [normalization-of-deviance](https://en.wikipedia.org/wiki/Normalization_of_deviance) made enforceable: the legacy plane only ever shrinks, and a Stop-Ship Gate blocks promotion while a legacy detector can still execute.

### Step 8 — Record a `ChangeManifestV1`

Every improvement flows through a `ChangeManifestV1`; missing evidence yields `not_ready`, never a mutation (`R-13`, charter `RUNTIME_CHARTER.md:142-164`). The manifest must declare:

- **failure evidence** (the Step 1 artifact)
- **root-cause hypothesis** (the Step 2 class — a hypothesis that names an *instance* is rejected)
- **target component** + **predicted fixes**
- **predicted regression risks**
- **required tests** (the Step 5 invariant)
- **live proof requirement** (the Step 6 result)
- **rollback plan**
- **observed delta** + **verdict**

If the change touches the authority/policy/security layer, it hits the hard-refuse: self-evolution may not mutate its verifier/benchmark/model-config/authority-policy without human approval, and the protected set **must include the authority-bearing files** (`RL-17`, `R-14`). [This is OpenClaw CVE-2026-45001 stated as a rule](https://www.vulncheck.com/advisories/openclaw-gateway-config-mutation-guard-bypass-via-agent-tool-access): a tool that can mutate the policy governing it inverts the hierarchy.

---

## 4. Regression-Test Discipline

### 4.1 What makes a test pin a root cause vs lock a symptom

A symptom-locking test asserts that *this input* produces *this output string*. It freezes the workaround: the moment the canned reply changes wording, the test breaks for the wrong reason, and — worse — it actively *protects* the hotfix, because deleting the hotfix breaks the test. An invariant-pinning test asserts a *property* over a *family* of inputs: a structural truth that must hold regardless of phrasing. [A regression test must pin the root cause, not lock a symptom](https://blog.codepipes.com/testing/software-testing-antipatterns.html) (`R-19`).

The audit quantified the failure: the `fix-qa-discipline` slice found **877 `assertIn`-literal tests** that pin phrases rather than invariants (a symptom-lock testing culture, `enforcement_gaps`). A repo whose tests assert literals will, when self-evolution runs, be taught that the way to "pass" is to emit the literal — which is exactly the `benchmark-overfit` plane in `domain-chip-memory`.

### 4.2 Before/after examples

**Example A — canned reply (the `canned-response` class).**

```python
# BEFORE (symptom-lock): protects the hotfix at provider_rescue_identity.py:6-173
def test_identity_question():
    assert answer("what does she support?") == "Liberal"   # freezes the answer-key
```
```python
# AFTER (invariant): the answer must be DERIVED, not a literal
def test_identity_answers_are_not_hardcoded_literals():
    # over a family of paraphrases, the answer must come from stored observations,
    # and a held-out paraphrase must still resolve (or honestly abstain)
    for q in paraphrases_of("what does she support?"):
        resp = answer(q, memory=store_with_supporting_evidence)
        assert resp.provenance == "retrieval+extraction"      # not "rescue"
        assert resp.source_span is not None                   # grounded in data
    # the held-out phrasing the rescue table never saw:
    assert answer(HELD_OUT_PARAPHRASE).provenance != "rescue"  # R-11
```

**Example B — authority (the `route-regex-authority` / `shadow-router` classes).**

```python
# BEFORE (symptom-lock): asserts one route's allow string
def test_build_route_allows():
    assert evaluateDeterministicRoute("concrete_project_build", text).allow is True
```
```python
# AFTER (invariant + checker): no regex plane may GRANT execution
def test_no_regex_plane_grants_execution():
    # structural invariant scanned from source (R-02, R-22, RL-01):
    for plane in scan_route_detectors(SRC_ROOTS):
        assert plane.may_veto in (True, False)
        assert plane.may_grant is False            # regex narrows, never grants
    # and at runtime, execution requires a Governor decision the surface did not author:
    decision = authorize(envelope, evidence=[regex_route_candidate])
    assert decision.origin == "governor"           # RL-02
    assert decision.allow == governor_only_verdict # not gated on routeVerdict.allow
```

**Example C — failure handling (the `failure-masking-fallback` class).**

```python
# BEFORE (symptom-lock): asserts the midpoint that masks the outage
def test_judge_empty_returns_five():
    assert _parse_score("") == 5      # locks the mask at voice_judge.py:63-72
```
```python
# AFTER (invariant): an unparseable judge output must surface, never coerce
def test_judge_failure_is_not_a_score():
    with pytest.raises(JudgeUnparseable):     # or returns None, never a number
        _parse_score("")                       # R-12, RL-08
    # and the gate built on it records a degrade reason, not a silent 0.5:
    assert run_gate(empty_judge).status == "degraded"
    assert run_gate(empty_judge).reason_code == "judge_unparseable"
```

The shape is consistent: delete the assertion that protects the workaround; add the assertion (or scan) that would fail for the *whole class* the workaround belonged to.

---

## 5. When a Hotfix Is Acceptable

A real incident — a live outage, an active break — sometimes needs a stopgap before the root cause is fully understood. That is legitimate *only* under strict conditions, and the stopgap may never harden into authority.

### 5.1 Strict conditions

A hotfix is acceptable during a live incident when **all** of these hold:

1. **There is a real, active incident** — not a failing benchmark, not a code-review nit. ([Hermes treats unattended/autonomous contexts as deny-by-default precisely because no human is watching](https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py); an autonomous run gets the conservative resolution `R-08`, never a hotfix.)
2. **It fails closed.** The stopgap narrows behavior or surfaces the failure; it must not *fabricate success* (`RL-08`, `R-06`). A masking fallback is never an acceptable hotfix — it is the thing this whole document exists to stop.
3. **It is labeled, loudly and greppably, as a stopgap.** Adopt a [greppable naming convention so a CI lint can count and gate it](https://docs.openclaw.ai/gateway/security) — the way OpenClaw prefixes every security-weakening flag with `dangerously`. A silent "for now" is how 23 `for now` markers and 104 `HACK` markers accumulated unseen.
4. **It is paired, same-day, with a debt ticket and a named retirement owner** (`R-15`). The ticket names the long-term general mechanism the stopgap is a placeholder for — [Hermes issue #16475's quick-win-paired-with-long-term-mechanism discipline](https://github.com/NousResearch/hermes-agent/issues/16475). No owner, no merge.

### 5.2 The hard line: a hotfix may never become an authority or eval surface

This is non-negotiable, and it is the direct lesson of pain #1:

- **A hotfix may never own execution authority.** A heuristic may flag or escalate; the decision belongs to the Governor (`RL-01`, [Hermes: a heuristic that produces a terminal deterministic response is masquerading as the boundary](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)).
- **A hotfix may never become an eval/answer surface.** A deterministic answer-key in the live answering path to pass a benchmark is a stop-ship, not a stopgap (`RL-10`, `RL-11`).
- **A denial or unmet gate is a hard halt.** When a Stop-Ship deny or an unmet `ChangeManifest` gate fires, the workstream halts; the agent does **not** retry, rephrase, or substitute a fallback to route around it (`RL-13`, [Hermes "silence is not consent"](https://github.com/NousResearch/hermes-agent/blob/main/tools/approval.py)). "Find an alternative that satisfies the surface check" is precisely the behavior that produced the fallback debt.
- **The change-failure-rate of the hotfixed component is tracked.** A rising-hotfix component is not release-candidate ready (`R-20`, [DORA](https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance)). Hotfix velocity is not throughput.

If a "hotfix" cannot meet §5.1 *and* stay on the right side of §5.2, it is not a hotfix — it is a deferred real fix, and the work is to do the real fix.

---

## 6. The Real-Fix PR Checklist

Copy-paste this into the PR description. Every box must be checked or explicitly N/A'd with a reason. Unchecked boxes block merge.

```markdown
## Real-Fix Checklist (docs/harness-discipline/02_REAL_FIX_PLAYBOOK.md)

### Reproduce & root-cause
- [ ] Reproduction artifact attached (failing test / trace / transcript)        [Step 1]
- [ ] 5-Whys descended to a CLASS + root cause, not a symptom-instance          [Step 2, R-05]
- [ ] Root-cause hypothesis names a class ("any input of shape X reaches…")     [PD-4, R-05]

### Policy / mechanism
- [ ] Policy/mechanism seam identified; the decision was NOT left fused in code  [Step 3]
- [ ] New/changed policy is a DECLARATIVE DATA ROW, not a new core branch        [R-16]
- [ ] Authority binds to the parsed/typed action, never re-tokenized argv/text   [R-01]
- [ ] No route-specific regex GRANTS execution; regex may only narrow/veto       [RL-01, R-02]
- [ ] Untrusted input normalized to ONE canonical form upstream of all rules     [R-07]

### Fail closed / fallbacks
- [ ] Every fallback fails closed AND emits a traceable, actionable reason code  [R-06, RL-08]
- [ ] No success-shaped failure value (None/''/{}/synthesized OK/midpoint score) [RL-08, R-12]
- [ ] No control flow keyed on a rendered human-readable error string            [RL-09, R-09]
- [ ] Guard paired with ALL sibling paths to the same effect (no unpaired theater) [RL-18]

### Tests
- [ ] Regression PINS THE INVARIANT over a family of inputs, not a literal string [R-19]
- [ ] No new assertIn-literal that protects a workaround                          [§4.1]
- [ ] Eval gains gated on a HELD-OUT set (no benchmark pass via memorized strings) [RL-10, R-11]

### Verify live
- [ ] Verifier runs GREEN LIVE — not a fake/memorized/literal-pinned pass         [Step 6, R-19]
- [ ] Evidence shown (test/command output), not asserted "looks done"             [Step 6]

### Retire legacy
- [ ] Every patch this fix obsoletes is DELETED                                   [Step 7, R-15]
- [ ] Auto-generated legacy inventory updated from a SOURCE SCAN (not hand list)  [RL-16]
- [ ] Legacy plane is smaller after this change than before                       [R-15]

### Manifest & protected layer
- [ ] ChangeManifestV1 records failure-evidence/root-cause/regression-risk/rollback [R-13]
- [ ] If authority/policy/security layer touched: human approval ref present       [RL-17, R-14]
- [ ] Change-failure-rate impact considered for the touched component             [R-20]

### Stopgap (only if this is a live-incident hotfix — see §5)
- [ ] Real active incident (not a benchmark/nit)
- [ ] Fails closed, does NOT fabricate success                                    [RL-08]
- [ ] Labeled with a greppable stopgap marker
- [ ] Same-day debt ticket + named retirement owner + long-term mechanism named   [R-15]
- [ ] Does NOT become an authority or eval/answer surface                         [RL-01, RL-10]
```

---

### Cross-references

- Red Lines (`RL-01`..`RL-18`) and Rules (`R-01`..`R-28`): `01_RULESET.md`.
- The CUA escalation loop that prevents §2.7 (`cua-local-reaction`): `03_CUA_ESCALATION_PROTOCOL.md`.
- The full offender inventory each specimen is drawn from, and the remediation backlog: `04_AUDIT_FINDINGS_AND_BACKLOG.md`.
- The external theory and sources (Hermes, OpenClaw, Anthropic, OSS harnesses, hotfix-debt theory): `05_EXTERNAL_HARNESS_LESSONS.md`.
- The governing charter this doc extends (never contradicts): `RUNTIME_CHARTER.md`.
