# Fleet Discipline — working with many agents in many repos

> Source of truth: `docs/harness-discipline/`. This extends the runtime ruleset (00–06) to the **development layer**: how multiple AI agents work on these repos at the same time without stepping on each other. Grounded in the 2026-06-24 fleet audit + SOTA research, and red-teamed (21 weaknesses found and folded in). **Read Part 1 first — it's plain English.**

---

# Part 1 — How this works, in plain English

## The problem, in one picture

Right now, every agent that works on a repo shares **one set of files** (one "checked-out" copy). Imagine five people trying to edit the same physical document on the same desk at the same time. Someone saves over someone else's paragraph; a half-finished edit gets mixed into a finished one; and because they all sign with the same pen name ("Codex"), you can't even tell who did what. That's exactly what we measured: one identity authored **60 of the last 60** commits in the telegram-bot repo, and a file grew by ~500 lines mid-session with nobody watching.

The fix is to give **each agent its own private copy of the files to work in**, a **named line of work**, and a **single doorway** where finished work gets checked and merged. That's all "worktrees, branches, and a gate" really mean.

## The five words, explained once (no jargon)

| Word | What it actually is | Everyday analogy |
| --- | --- | --- |
| **Repo** | A project's code + its full history. | A workshop. |
| **Working tree** | The actual files you see and edit right now. | The workbench. Today, everyone shares ONE. |
| **Branch** | A named line of work ("Alice's cancel-bug fix"). | A labeled folder of changes. |
| **Worktree** | A *second, private* working tree fed from the same history. Each agent gets its own. | Giving each person their **own workbench** in the same workshop, drawing from the same shared storeroom. |
| **PR + the gate** | The one place finished work is reviewed and merged into the shared version. | The single **doorway** with a checker standing at it. |
| **Lease** | A short "I'm working on these files until 3pm" sign-out. | A **sign-out sheet** so two people don't grab the same tool. |

That's the whole vocabulary. Everything below is just *how we make sure agents actually follow it* (because a rule nobody enforces is the exact trap this whole project exists to avoid).

## The part that should un-confuse you: **you don't juggle worktrees by hand**

You said you don't usually work with many worktrees and branches — good news: **you mostly won't.** The machinery is run *by the agents, via one command*, not by you. Here's the honest division of labor:

**What the SYSTEM does automatically (you never touch this):**
- When an agent starts a task, it runs **one command** — `spark fleet claim <repo> <area>` — and the system: makes a private worktree, a properly-named branch, sets the agent's identity, and signs out the files (the lease). When the work merges, the worktree is **auto-cleaned**. A nightly sweep (`spark fleet gc`) removes leftovers.
- The "gate" (the checker at the doorway) runs automatically on every PR. Bad work (a god-file growing, a missing sign-out) gets **rejected by the build**, not by you remembering to check.

**What YOU do (small, human, high-value):**
1. **Kick off an agent on a task** ("fix the telegram cancel bug").
2. **Glance at the fleet board** when you want to see who's working on what ("Agent A: telegram routing; Agent B: harness schemas; no collisions").
3. **Approve the things that need a human** — changes to the *important* files (the authority spine, the schemas, the policy) are set to require your sign-off. Everything routine is handled by the automated jury.

That's it. You are the person who *starts work* and *approves the sensitive stuff*. The worktrees and branches are plumbing the agents run for themselves.

## A day in the life (concrete)

> You: *"Agent A, fix the cancel-relay bug in telegram-bot."*
>
> **Behind the scenes (Agent A, automatically):** runs `spark fleet claim spark-telegram-bot routing`. The system hands it a private worktree at `~/.spark/fleet/worktrees/spark-telegram-bot/agent-a/cancel-relay`, on a branch `agent/agent-a/cancel-relay`, with identity `agent-a`, and a lease on the "routing" files until it's done. Agent B, meanwhile, claimed `harness-core/schemas` — a *different* area, so no conflict; if B had tried to claim "routing" too, it would have been told *"held by agent-a until 3:10pm — wait or pick another area."*
>
> Agent A edits, commits (every commit stamped `Agent-Id: agent-a`), opens a PR. **The gate runs:** tests pass, the god-file ratchet is happy, the sign-out checks out → the jury approves → it merges. Agent A's worktree auto-cleans.
>
> **You:** glanced at the board once, saw two agents on two non-overlapping areas, approved nothing (nothing sensitive was touched). Done. **You never created or deleted a worktree.**

## Why we bother (the one-sentence reason)

Five agents going fast with no isolation isn't five times the work — it's five times the *entanglement*, and the cleanup eats the speed. Isolation + one gate is what lets you actually run many agents **and stay calm.**

---

# Part 2 — The Working Agreement (the formal rules)

These are the rules the system enforces. Each has a **Status** so this document never claims enforcement that isn't built yet (the #1 lesson of this whole effort: *a rule is only as real as its mechanism*). The red team's correction is baked in: **the load-bearing enforcement is server-side** (the gate at the doorway), because a check that runs only on an agent's own machine can be skipped. Local checks are a helpful early warning, not the real gate.

**Status legend:** ✅ LIVE (built and working) · 🟡 SCAFFOLD (script exists, advisory only, not yet a blocking gate) · ⛔ TO BUILD (designed, not yet built).

### Isolation
- **F-01 — One agent = one task = one private worktree = one branch off the canonical branch = one PR.** No agent ever commits from the shared/primary checkout, or onto a branch another agent occupies. *Enforcement:* `worktree_guard.py` (rejects commits from the primary checkout / a protected branch / a wrong-named branch / the shared identity). **Status: 🟡 SCAFFOLD** (runs as a local check today; becomes load-bearing only as a server-side / merge-queue check — see F-09).
- **F-02 — Branch names are a contract:** `agent/<agent-id>/<task-slug>`. *Enforcement:* `worktree_guard.py` + the `spark fleet claim` script is the only sanctioned way to start. **Status: 🟡 SCAFFOLD.**
- **F-03 — Each worktree sets its own git identity** (`agent-id`), retiring the shared `Codex` pen name, so commits are attributable. *Enforcement:* `commit_trailer_gate.py` requires an `Agent-Id:` trailer matching the branch. **Status: 🟡 SCAFFOLD.**
- **F-04 — Each task also gets isolated *execution* state** (its own port + data dir), so two agents don't fight over one SQLite file or port. *Enforcement:* the claim script provisions them; a dev-server wrapper reads them. **Status: ⛔ TO BUILD.**

### One gate
- **F-09 — Protected canonical branch + a single merge gate in every repo.** Agents open PRs only; the existing **agent-jury** stays the one approval (we do *not* add a second). No direct pushes by anyone. *Enforcement:* GitHub branch ruleset + merge queue with required checks (jury + the guards + the god-file ratchet) + a remote pre-receive hook so it can't be skipped. **Status: ⛔ TO BUILD — and per the red team this is the FIRST thing to build, because nothing else is load-bearing without it.**
- **F-11 — The important files require a human.** The authority spine (`harness-core` kernel + schemas), the autonomy policy, the verifier/eval set: an agent may *propose*, but a human (you) must approve. *Enforcement:* `CODEOWNERS` + required code-owner review (this is RL-17 from the runtime ruleset, applied to the dev layer). **Status: ⛔ TO BUILD.**

### Policy-as-data (coordination lives in files a machine reads, not prose)
- **F-05 — Lease before write:** hold an active lease over every (repo, area) you'll change before your first commit. **Status: ⛔ TO BUILD** (needs the ledger, F-13).
- **F-06 — Leases don't overlap:** the ledger grants a claim only if no active lease covers the same area; overlapping files run **sequential, never parallel**. God-files (`index.ts`, `cli.py`) are **file-level forced-serial** (a wait-your-turn queue), because that's the finest honest granularity. **Status: ⛔ TO BUILD.**
- **F-07 — Leases expire** (default 30 min, heartbeat extends, released on PR-open). A crashed agent's lease auto-frees. Grant *and* reclaim are a single atomic database transaction (not "trust the server is single-writer"). **Status: ⛔ TO BUILD.**
- **F-13 — The lease ledger** is `fleet/leases.json` validated by `fleet-lease-v1.schema.json`, served by atomic endpoints on the existing spark-compete server. **Status: 🟡 SCAFFOLD** (schema + example written; endpoints TO BUILD).
- **F-08 — No green from a dirty tree.** A baseline or gate may only be captured/evaluated from a clean working tree on the canonical branch. Dirty / detached / wrong-branch ⇒ rejected. *Enforcement:* a clean-tree precondition shared by all `harness_checks`. **Status: ⛔ TO BUILD** (the line-count gate's `--update` needs this added).

### Honest authorship & no-drift
- **F-10 — Every commit is Conventional-Commit-shaped and carries `Agent-Id` (+ `Task-Id`).** *Enforcement:* `commit_trailer_gate.py`. **Status: 🟡 SCAFFOLD.** (Real attribution requires per-agent push credentials, F-09, or the trailer is self-asserted.)
- **F-12 — The dev-layer checkers live canonically in `spark-compete/scripts/harness_checks/`**, vendored byte-identical into each repo, guarded by a `check-harness-checks-sync` job so copies can't drift. **Status: 🟡 SCAFFOLD** (checkers exist; the sync job is TO BUILD — *build it before fanning out*).
- **F-16 — Known god-files carry the R-21 ratchet** so the next mid-session accretion fails the build. **Status: ✅ LIVE** in spark-cli + telegram-bot (baselines captured; needs re-capture clean once F-08 lands).

### See it / clean it
- **F-14 — Nightly `spark fleet gc`** prunes finished worktrees + merged branches; a one-time sweep clears today's ~37 stale worktrees. **Status: ⛔ TO BUILD.**
- **F-15 — Use the lightest mode that works.** Default to isolated independent agents; only use coupled "agent teams" for genuinely shared work, behind a checked-in file-ownership split approved at claim time. **Status: ⛔ TO BUILD.**
- **F-13b — A fleet board** (extending the existing `admin.html`) shows live leases, orphan `agent/*` branches with no lease (the entanglement alarm), worktree counts, and god-file growth — reading the *same* data the gate reads (one source of truth, no split-brain). **Status: ⛔ TO BUILD.**

---

# Part 3 — How we build it (healthy order) + what's true today

The red team's biggest catch: the original plan led with **local pre-commit hooks**, but no hooks are installed anywhere and a local hook is trivially skipped — so leading with them would be *mandate-by-prose* (claiming a gate that isn't one). **So we build the server-side gate first.**

| Wave | What | Why this order |
| --- | --- | --- |
| **1. The real gate** | Pick the canonical branch per repo (today they're inconsistent — spark-compete is `master`, others `main`); turn on the protected-branch ruleset + merge queue with required checks on **one pilot repo** (telegram-bot). | Nothing below is load-bearing until the gate exists server-side. |
| **2. Identity + hygiene** | Retire the shared `Codex` identity; make `spark fleet claim` the only start-of-work path; one-time `git worktree` sweep; re-capture the god-file baselines clean. | Stops anonymous shared-checkout commits; cleans the 37-worktree mess. |
| **3. Human-owned files** | `CODEOWNERS` on the authority spine + the fleet files, paired with the ruleset (CODEOWNERS is inert without it). | Protects the things only you should approve. |
| **4. Leases** | Build the ledger (atomic transactions) + area manifests; turn on the lease check; build the drift-guard *before* fanning checkers out. | The concurrency guarantee, done race-safe. |
| **5. See + sweep** | The fleet board; nightly GC; fan the checkers to every repo. | Observability becomes a gate input, not just a dashboard. |
| **6. Write the rest of this doc from shipped reality** | Flip each Status above to ✅ as it actually ships. | We never claim a gate before it's real. |

### What is actually true *today* (no over-claiming)
- ✅ The **R-21 god-file ratchet** is live in spark-cli + telegram-bot (it would now block the index.ts growth we saw).
- 🟡 Two **advisory** local checkers exist (`worktree_guard.py`, `commit_trailer_gate.py`) — they warn, they are **not yet a blocking gate** (that's Wave 1).
- 🟡 The **lease schema + an example area manifest** are written as the contract; the **server endpoints, the gate, leases, CODEOWNERS, the board, and GC are all TO BUILD.**
- The honest one-liner: **today the discipline is *designed and partially scaffolded*; it becomes *enforced* only after Wave 1 (the server-side gate).** Don't treat the 🟡/⛔ rows as protections yet.

---

### Sibling documents
- [`00_README.md`](00_README.md) — start here · [`01_RULESET.md`](01_RULESET.md) (the runtime ruleset this extends) · [`04_AUDIT_FINDINGS_AND_BACKLOG.md`](04_AUDIT_FINDINGS_AND_BACKLOG.md) · [`06_AUTONOMY_AND_MACHINE_ORIGIN.md`](06_AUTONOMY_AND_MACHINE_ORIGIN.md).
- Mechanisms live in `spark-compete/`: `scripts/harness_checks/` (checkers), `fleet/` (lease schema + area manifests), `scripts/fleet-claim.sh` (start-of-work).
