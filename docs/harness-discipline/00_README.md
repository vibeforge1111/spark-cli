# Spark Harness Discipline

> Source of truth: `docs/harness-discipline/`. Grounded in the 2026-06-24 Spark harness audit (51 offenders, 6 code slices) + Hermes / OpenClaw / Anthropic / OSS-harness research (51 lessons, 58 citations). Every code claim in this set was spot-verified against live source (29 checks, 0 hallucinations).

This is the **orientation document**. Read it first. It explains *why this set exists*, *what it found*, *how the five documents fit together*, and *where to start*.

---

## Why this set exists — the two pains

Spark is a **self-evolving** agent harness. That makes two failure modes catastrophic rather than annoying, because the system reads its own repository as the norm and reproduces it:

1. **Deterministic answers committed as hotfixes that became shadow authority.** A single failing case — a misrouted Telegram message, a benchmark question, an OS-specific git error — gets "fixed" with a route-specific regex, a hardcoded fallback, or a canned reply. The shortcut works for that one case, ships, and then *owns the decision* for every future case that resembles it. As the repos grow, these shortcuts compound into a parallel, unaccountable authority plane that fights the real one.

2. **Telegram-desktop CUAs that failed to cooperate with a higher-intelligence planner and drifted into local hotfixes.** When the computer-use agent got stuck, hit ambiguity, or fell out of scope, it had no mechanism to hand the problem *up*. So it improvised locally — which is exactly the behavior that mints pain #1.

These are not hypotheticals. The audit found **51 offenders** that are these two pains realized in committed code, and the `spark-cli` branch tip is literally `hotfix/r28-longpath-guard` — 28 rounds of patch-one-more-edge with no exit from the treadmill.

## The central finding — *mandate by prose, enforcement by honesty*

The Spark governance corpus is unusually mature **on paper**. `RUNTIME_CHARTER.md` already forbids every anti-pattern above: "a route-specific regex owns execution authority" is a Stop-Ship Gate; "the Governor is the only component that may promote evidence"; Legacy Plane Retirement; self-evolution "cannot mutate verifier logic … without explicit human approval."

**The vocabulary is correct. The enforcement is honesty.** Those rules are checked by hand-curated lists and caller-supplied booleans, not by code:

- `kernel.readiness_score()` trusts `governance_rulesets_proven` / `zero_high_agency_legacy_local_gates` as **caller-supplied booleans** (`kernel.py:677-744`) — it never scans the code.
- The inventory that is supposed to *prove* legacy-plane retirement is a **hand-maintained array that omits the two largest live planes** (`legacy_authority_inventory.py:81-200`).
- The "higher intelligence" is structurally benched: the LLM route-arbiter is type-locked to `'off' | 'shadow'` and can **never** become authority (`routeArbiter.ts:12,56-61`), while the regex IntentGate runs in `'enforce_safe'` — the determinism trap as architecture, and pain #2 in code.

> **Thesis of this set: the charter names the rules; this set makes them mechanically enforceable.** Every rule carries a checker (a lint, a CI gate, a unit invariant, a schema, a human-approval gate, an observability assertion). A rule that can't be checked by a machine is a comment, not a rule.

## The one-line review gate

> A deterministic shortcut is allowed **only** as a typed control-flow gate (inside the Governor/policy) **or** as model reasoning — **never** as an undeclared third thing that silently owns authority. If a proposed change is a third thing, it does not merge.

---

## How the five documents fit together

```
                00_README.md  ← you are here (orientation)
                      │
                      ▼
   01_RULESET.md  ── the anchor: 7 Prime Directives, RL-01..RL-21 (red lines),
        │             R-01..R-28 (rules), the Enforcement Model, Appendix A
        │             (exemplars to preserve). Every other doc cites these IDs.
        ├──────────────► 02_REAL_FIX_PLAYBOOK.md   — how to shape a real fix vs a
        │                  hotfix; the legitimate-fallback-vs-masking taxonomy;
        │                  the Real-Fix Protocol + PR checklist. (expands R-05/R-06/RL-08)
        ├──────────────► 03_CUA_ESCALATION_PROTOCOL.md — the planner↔CUA contract;
        │                  escalation triggers; the typed handoff. (expands R-23..R-28, RL-12/13)
        ├──────────────► 04_AUDIT_FINDINGS_AND_BACKLOG.md — the 51 offenders with
        │                  file:line, grouped by root cause, sequenced into a
        │                  Wave-0..Wave-3 checker-build backlog.
        └──────────────► 05_EXTERNAL_HARNESS_LESSONS.md — the 51 research lessons
                           (Hermes, OpenClaw, Anthropic, OSS, hotfix-debt theory,
                           CUA orchestration), the comparison matrix, the closed citation list.
```

| Doc | What it answers | Primary audience moment |
| --- | --- | --- |
| **01_RULESET** | "What are the rules, red lines, and how is each enforced?" | Writing/reviewing any change; setting up CI gates. |
| **02_REAL_FIX_PLAYBOOK** | "What does a *real* fix look like, and when is a hotfix ever OK?" | Before fixing a bug; in code review. |
| **03_CUA_ESCALATION_PROTOCOL** | "When must the CUA escalate instead of improvising, and how?" | Building/operating the computer-use + Telegram loop. |
| **04_AUDIT_FINDINGS_AND_BACKLOG** | "What's broken today, how bad, and in what order do we fix it?" | Planning; sprint sequencing; tracking the exit from `mandate-by-prose`. |
| **05_EXTERNAL_HARNESS_LESSONS** | "What do the best harnesses do, and what do we borrow?" | Designing a fix; justifying a rule; onboarding. |

This set **relates to `RUNTIME_CHARTER.md`** the way an enforcement statute relates to a constitution: it does not contradict the charter at any point — it *extends* it with the fix-discipline layer and the mechanisms the charter assumes but never specifies. Where the charter says *what*, this set adds *how it is detected*.

---

## Reading order

- **New engineer / onboarding:** `00` → `01` (skim the Prime Directives + Red Lines) → `02` → `05`. Then keep `01` open while you work.
- **Fixing a bug right now:** `02` (the Real-Fix Protocol + PR checklist) → the relevant Red Lines in `01`.
- **Working on the Telegram/CUA loop:** `03` → `01` §(G) → `05` §6 (CUA orchestration).
- **Planning the remediation:** `04` (the backlog) → `01` §5 (the Enforcement Model table).
- **Designing a new control or justifying a rule:** `05` → `01` Appendix A (don't re-fix the exemplars).

---

## Where to start — the highest-leverage first moves

The backlog (`04` §4) sequences everything, but three checkers catch the most offenders for the least effort and should land first. Until a checker exists, its rule is enforced by review — and **review is honesty, which is exactly the gap this set exists to close**:

1. **God-file CI line-count gate** (`R-21`) — fails the build on any file >3,000 lines lacking a registered owner+refactor-plan. Catches `cli.py` (17,936 lines) and `index.ts` (10,486) today, and stops the next inline-hotfix accretion.
2. **Authority-site detector** (`RL-01` / `RL-02`) — an AST/grep check that flags any function deriving `allow`/`deny`/`route`/a terminal answer from regex/keyword input that is then consumed as a precondition of execution. Catches the entire regex-authority cluster (`approval.py`, `routeFirewall.ts`, the intent gates).
3. **Legacy-plane scan reconciliation** (`RL-16`) — makes "this plane is retired" *falsifiable* by computing the inventory from a source scan instead of trusting a hand-maintained list.

After those, the rest of Wave 0 ("stop the bleeding") makes the next self-evolution pass mechanically unable to add offender #52.

---

## Two decisions this set surfaces for the founder

1. **The machine-origin approval exception** (`RUNTIME_CHARTER.md:96`) — **DECIDED, ratifiable** (see [`06_AUTONOMY_AND_MACHINE_ORIGIN.md`](06_AUTONOMY_AND_MACHINE_ORIGIN.md)). The lane is **OFF**: nothing self-approves; RL-04/RL-13 stay absolute (halt-and-queue, R-08); high/critical/irreversible are never eligible; the default allowlist is empty and can only be populated after an 11-item precondition set (P-1..P-11) is CI-green. A 2026-06-24 red team found 15 exploit paths and established that the lane is currently *unbuilt paper* — the empty allowlist is the only present safety property. The founder's remaining action is to **ratify** (adopt off + gate enablement behind the preconditions).
2. **Sequencing the backlog against live work.** `04` proposes Wave 0→3; the founder owns whether to gate launch on Wave 0 (the CI checkers) or run them in parallel with feature work. The smell census (962 fallbacks, 138 canned, 118 route-regex) only ratchets down once Wave 0 is green.

---

### The set

- **`00_README.md`** — this document. Orientation.
- **`01_RULESET.md`** — the anchor: Prime Directives, `RL-01`..`RL-21`, `R-01`..`R-28`, the Enforcement Model, Appendix A (exemplars to preserve).
- **`02_REAL_FIX_PLAYBOOK.md`** — hotfix vs real fix; the anti-pattern taxonomy; the Real-Fix Protocol; the PR checklist.
- **`03_CUA_ESCALATION_PROTOCOL.md`** — the planner↔CUA orchestration contract and escalation protocol.
- **`04_AUDIT_FINDINGS_AND_BACKLOG.md`** — the 51 offenders + the Wave-0..Wave-3 remediation backlog.
- **`05_EXTERNAL_HARNESS_LESSONS.md`** — Hermes / OpenClaw / Anthropic / OSS lessons, the comparison matrix, and the closed citation list.
- **`06_AUTONOMY_AND_MACHINE_ORIGIN.md`** — the machine-origin approval decision (lane OFF, gated behind the P-1..P-11 precondition set); resolves the charter `:96` exception. Red-teamed 2026-06-24.
- **`07_FLEET_DISCIPLINE.md`** — **the dev-layer extension: how many agents work on these repos at once** without entanglement (worktrees, branches, one gate, leases). **Part 1 is plain-English** — read it first if worktrees/branches are unfamiliar. Red-teamed 2026-06-24.
