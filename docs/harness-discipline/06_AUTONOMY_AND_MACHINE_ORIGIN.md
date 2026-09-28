# Autonomy & the Machine-Origin Approval Decision

> Source of truth: `docs/harness-discipline/`. This document **resolves** the open question flagged in [`01_RULESET.md`](01_RULESET.md) §3 and [`04_AUDIT_FINDINGS_AND_BACKLOG.md`](04_AUDIT_FINDINGS_AND_BACKLOG.md) §6.5: does an unattended, self-evolving Spark ever self-approve a high-agency action, and if so, how? **Status: DECIDED — the lane is OFF, and stays off until a hard precondition set is CI-green.** This doc was adversarially red-teamed on 2026-06-24 (15 exploit paths found); the findings are folded in below.

---

## 0. Enforcement status — read this first

**The machine-origin lane does not exist in code. There is no door yet — which is the only thing currently making it safe.** No runtime component reads `AutonomyPolicyV1`; "frozen at load" (RL-06), the protected-component coverage of the policy file (RL-17), the `machine_origin` provenance field, reversibility, and the post-hoc audit queue are **all unbuilt** (status: missing). 

This matters because an earlier draft of *this very document* asserted those protections as if they were active — which is the **mandate-by-prose** pattern the whole ruleset exists to eliminate, reproduced inside the doc meant to close the hole. So, plainly:

- Everything below in §3–§4 is a **specification of what must be BUILT and CI-green before the lane can EVER be enabled** — not a description of current guarantees.
- Today the *only* safety property is: **allowlist is empty AND nothing reads the policy.** That is sufficient for "off," and nothing else is claimed.

## 1. The question

`RUNTIME_CHARTER.md:96` says high/critical actions require explicit approval *"unless a future policy grants a narrowly scoped machine-origin exception."* Spark runs **unattended** (cron, self-evolution, CUA sessions). So: when no human is present and a high-agency action is needed, does Spark halt forever, or does *something* let it proceed? Leaving this undefined invites an ad-hoc hotfix that fabricates an approval — exactly today's `legacy_turn_intent.py:627-638` offender behind RL-04.

## 2. The decision

**Machine-origin approval is DEFINED, but OFF, and gated behind a precondition set. Today, anything needing high-agency approval with no human present HALTS AND QUEUES (R-08). Nothing self-approves. RL-04 and RL-13 are absolute in effect.**

1. **High, critical, and irreversible actions are NEVER machine-origin eligible** — publish, deploy, PR, credential/secret ops, new-host network egress, destructive ops, and any change to the authority/policy/eval/inventory layer always require an out-of-band human approval. Non-negotiable (`Hermes` unbypassable hardline blocklist; `OpenClaw` "the model is never a boundary"; `cua-orchestration` "never self-authorize a consequential action").
2. **Machine-origin is a distinct, honestly-labeled provenance — never a synthesized human approval** (RL-04 holds).
3. **The eligible surface is an allowlist that starts empty and may only be populated after the §5 precondition set is CI-green.** Until then it is structurally impossible to enable, not merely defaulted-off.
4. **Capabilities graduate one at a time**, each a human-ratified, replay-backed, auto-revocable, post-audited addition — and only after the detection infrastructure that would catch a bad one exists. The doc's own rule — *never add an allowlist entry before the thing that would detect its failure exists* — is extended by the red team to: **never claim an enforcement guarantee before its enforcement code exists.**

This unblocks the CUA rules (they stay absolute now, so `03_CUA_ESCALATION_PROTOCOL.md` ships), closes the hole (the exception is defined, so no hotfix invents one), and gives a precise, *honest* path to real autonomy later.

## 3. What the red team found (why the preconditions exist)

15 exploit paths across three axes. None breaks the **empty/off** door today, but every one is a latent defect in the criteria the *first* allowlist entry would be judged against:

- **Composition & timing.** Per-action "low/reversible/local" does **not compose.** No schema has any cumulative/budget/rate concept (grep-confirmed), so N allowlisted-low actions sum to a high-blast-radius DoS no per-action check sees. Individually-innocent writes can **assemble** a never-listed effect (a deploy manifest / CI workflow file / git hook) that an out-of-band watcher then executes — the never-list is keyed on capability *names*, not realized *effects* (the RL-18 gap, still unenforced). "Reversible" is a per-action local-state property that ignores **external observation before audit** and does not compose (rolling back A leaves B's derivative). The post-hoc audit has **no latency bound** — an unbounded damage-before-review window. Idempotency is a **disjunctive escape hatch** with no specified durable key store.
- **Self-grant & freeze (criticals).** The protected-component gate keys on an **author-declared `component_type`** with no path→type registry — so a run **self-classifies** the policy as non-protected to skip the human-approval gate. `risk_tier` is **caller-supplied free data** with no classifier — "mark high as low" is a data choice, not a code change. `approval.source = "machine_origin"` is **not expressible** in `authorization-decision-v1` (`additionalProperties:false`, no field) — the honesty claim has no data contract. "Frozen at load" is unimplemented; a self-evolution run can widen its own allowlist while staying schema-valid and readiness-green.
- **Drift & deviance.** Allowlist entries are bare strings with **no owner/replay/expiry/auto-revoke** — "replay-backed, post-audited" decays into a **one-way ratchet** that has mechanisms to OPEN but none to force CLOSED. An operator under pressure can **mislabel** a policy edit to skip approval, or widen "just for now" by analogy ("we already allow X; Y is similar") — the exact r28 hotfix culture this effort fights.

## 4. Preconditions to enablement (ALL must be CI-green before the FIRST allowlist entry)

Each is a build item with a named rule and a checker. **Status of every item below: NOT BUILT.** This is the gate; "the lane is off" until it is fully green.

| ID | Precondition | Rule | Closes |
| --- | --- | --- | --- |
| **P-1** | **Path-identity protection.** A signed/hashed canonical registry maps file path → `component_type`; the autonomy-policy file *and* the risk-tier classifier are protected **by path**, not by author-declared type. Any edit to a protected path requires a valid, **authenticity-verified** `human_approval_ref` (real out-of-band operator/CLI/Telegram token, not mere presence). | RL-16, RL-17, R-14 | self-classify-to-skip-approval; mislabel-the-edit |
| **P-2** | **Derived risk tier.** `risk_tier` is computed by a protected classifier from the capability's declared effects, never trusted as a caller-supplied string. | RL-15, PD-1 | "mark high as low" |
| **P-3** | **Provenance in the contract.** Add `approval.source` (enum `human` \| `machine_origin`) to `authorization-decision-v1` (a protected schema change); `machine_origin` is *only* valid under a ratified policy and *never* for ≥ medium. | RL-04 | impersonating a human approval |
| **P-4** | **Freeze at load (for real).** Policy is loaded once at process start from a source whose sha256 is recorded; no hot-reload from mutable disk; no hot-path `os.environ`/disk read can flip it. | RL-06 | runtime mutation of the policy |
| **P-5** | **Effect-based mediation.** A capability/effect broker gates the **realized effect** (fs write to a watched/synced path, branch push, network egress), so the never-list/denylist hold even for an action whose *name* is innocent but whose *output* triggers a forbidden effect. | RL-18 | compositional escalation via watchers |
| **P-6** | **Cumulative blast-radius budget.** A run-scoped budget object (keyed on `harness-run-v1.run_id`) that the authorization path **must** consult: caps the count/rate/summed effect of machine-origin actions across a run/session, not just per action. | RL-18, R-08 | repeated-low → DoS / resource exhaustion |
| **P-7** | **Run-level reversibility.** A checkpoint/restore primitive + a recorded dependency graph (not only per-ledger `rollback_ref`); an effect that is externally observable before audit is treated as **irreversible** and is therefore ineligible. | R-27 | rollback-doesn't-compose; external observation |
| **P-8** | **Audit latency ceiling + backpressure.** A max time-to-audit; once the un-audited machine-origin backlog in a scope exceeds the ceiling, **all further machine-origin actions in that scope halt.** | R-08, R-17 | unbounded damage-before-review window |
| **P-9** | **Structured, self-revoking allowlist.** Allowlist items become objects `{ capability_id, risk_tier, replay_case_id (required), owner, expires_at, auto_revoke_on_replay_break: true }`; an entry whose replay case breaks or whose expiry passes is auto-revoked; each addition carries its own gate-clearance artifact; **justification-by-analogy is forbidden** (each entry cleared independently). | RL-10/RL-11, R-15, R-20 | the one-way ratchet; precedent creep |
| **P-10** | **Anti-widening invariant.** Across an accepted `ChangeManifestV1`, `allowlist` may only **shrink**, `autonomy_level` may only **decrease**, `denylist`/never-list may only **grow** — enforced as a checker on policy edits; a self-evolution run proposing to add *itself* is auto-denied (PD-7). | R-14, PD-7 | self-grant; "just for now" widening |
| **P-11** | **Required-hook proof.** A machine-origin execution must carry, in its ledger/proof capsule, evidence that the `pre_tool` blast-radius and `post_tool` audit-queue hooks actually ran; a missing hook proof fails the action closed. | RL-07, R-17 | declared-but-unrun hooks |

## 5. Reconciliation with the ruleset (the conservative RL-04 amendment)

This decision **amends RL-04** (folded into [`01_RULESET.md`](01_RULESET.md)) to a *gated* rule, not an open exception:

> **RL-04 (amended).** Approval evidence for a high/critical action must come from an out-of-band human signal and must never be synthesized from an in-process heuristic. A **machine-origin** authorization is permitted *only* when (a) the full §4 precondition set in `06` is CI-green, (b) the capability is on a structured, human-ratified `AutonomyPolicyV1` allowlist, and (c) it is recorded with `approval.source = "machine_origin"`. It is **never** valid for `high`/`critical`/irreversible actions. Until the preconditions are green, this rule is **absolute** (human-only). The shipped default allowlist is empty.

- **RL-13** unchanged: a non-allowlisted action still hard-halts/queues; machine-origin is a pre-authorized narrow lane, never a route-around-deny.
- **R-08** unchanged as the default; machine-origin is the explicit, audited, gated exception to it.
- **R-26** unchanged: a CUA may use a machine-origin lane only for the same ≤ low, allowlisted, reversible actions; everything consequential still escalates.

## 6. What the founder ratifies

1. **Adopt the decision: lane OFF, RL-04 absolute, default allowlist empty — indefinitely, until §4 is green.** (Safe to adopt as-is; this is the recommended call.)
2. **Do not build machine-origin enablement until the Wave-3 observability + the §4 preconditions exist.** The preconditions go in the backlog as a gated **"Wave 4 — machine-origin enablement"** block; none ships before Wave 3.
3. **The one genuine future choice — the first allowlist entry — does not arise until §4 is green.** Realistic first candidates then: *"refresh a registry pin in a scratch branch,"* *"run a read-only doctor and queue the report"* — each reversible, local, replay-covered, post-audited, cumulatively-bounded.

Until the founder authors and human-approves a non-empty `AutonomyPolicyV1` **with §4 green**, Spark self-approves nothing — the lane is documented, gated, and shut.

---

### Sibling documents
- [`00_README.md`](00_README.md) · [`01_RULESET.md`](01_RULESET.md) (RL-04 amended here) · [`03_CUA_ESCALATION_PROTOCOL.md`](03_CUA_ESCALATION_PROTOCOL.md) · [`04_AUDIT_FINDINGS_AND_BACKLOG.md`](04_AUDIT_FINDINGS_AND_BACKLOG.md) §6.5 + the Wave-4 gated block.
