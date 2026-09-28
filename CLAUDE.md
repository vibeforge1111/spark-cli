# Spark CLI Agent Ruleset

## Repo Role

`spark-cli` owns Spark's local installer, registry, provenance, secrets, health checks, module lifecycle, sandbox/operator commands, and Spark OS read-model compilation.

Canonical truth owned here:

- starter-module registry, bundle membership, pins, and attestation metadata
- installer scripts, installer manifest, hosted-installer verification contracts, and onboarding checks
- local module lifecycle commands: setup, update, status, start/stop, fix, verify, doctor
- safe secret storage and generated module environment wiring
- Spark OS compiled read models: system map, repo board, authority view, trace index, memory projections, capability catalog, voice surface view, and operating cockpit inputs

This repo does not own:

- Telegram conversation behavior, composition, or channel tokens
- Builder AOC, route confidence, identity, or memory orchestration
- Spawner mission execution and provider result bodies
- domain-chip memory algorithms or durable memory doctrine
- Cockpit UI layout or user-facing dashboards

## Start-of-Work Protocol

1. Run `git status --short --branch`.
2. Read this file plus `README.md` and the relevant command/installer docs.
3. Identify whether the change is CLI-owned or belongs in Builder, Telegram, Spawner, memory, Cockpit, Labs, Swarm, voice, or Skill Graphs.
4. Define the smallest verifiable behavior and the stop-ship gate.
5. Prefer focused tests for the changed command or compiler slice before broader suites.
6. Update docs when commands, installer behavior, registry metadata, or compiled artifact shapes change.
7. Commit one logical checkpoint with verification notes.

## One Truth Rules

- Registry pins and installer manifests must describe owner repo truth; do not paper over dirty runtime state with local-only assumptions.
- Compiled Spark OS artifacts are projections. They must not become runtime authority, durable memory authority, or source state.
- If an artifact joins evidence from multiple repos, preserve source owner, freshness, blocker, and redacted reference fields.
- Do not create a new state root when an owner repo can expose metadata safely.
- Do not treat generated JSON, logs, proof folders, or local workspaces as source truth unless explicitly promoted and documented.
- If `spark os compile` reports `canonical_runtime_dirty`, stop installer work and clean or quarantine the residue without reading private payloads. Then rerun `spark os compile --json` and require `critical_duplicate_truth_count=0` before any hosted publication claim.
- Runtime residue belongs under `<spark-home>/state`, not inside module source roots. If residue must be preserved, move it to a dated quarantine path and document the verification command.

## Privacy Red Lines

Do not export, commit, or compile:

- secrets, tokens, env values, credentials, private keys
- raw chat ids, user ids, or non-redacted account identifiers
- raw prompts when metadata is enough
- provider output bodies
- memory bodies or transcript bodies
- raw audio payloads
- private `spark-intelligence-systems` strategy

Use allowlisted serializers for read models. If a source payload contains unknown fields, drop or redact them before projection.

## Authority and Route Rules

- CLI may own operator diagnostics and local repair guidance, but Builder owns RouteConfidenceGateV1 and AOC route judgment.
- `spark fix` and `spark doctor` outputs should expose metadata-only route context and verification commands, not mutate high-risk surfaces without explicit gates.
- High-agency actions must fail closed unless authority, capability, freshness, consequence risk, confirmation, and privacy boundary are known.
- External publication, destructive changes, credential changes, and installer/site publication require explicit release gates.

## Release and Installer Rules

- Source owner commit first.
- Installed runtime update second.
- Registry pin update third.
- Installer/site metadata publication last and only as a named batch.
- `spark verify --registry-pins`, installer verification, hosted metadata/checksum verification, onboarding verification, and relevant tests must pass before claiming install readiness.
- If installer scripts did not change, prefer registry/source cleanup over hosted byte publication.
- A clean compile with `0` critical duplicate truths is a release-readiness signal, not proof that all backlog is gone.

## Anti-Spaghetti Rules

- Do not duplicate Builder route logic, Telegram composition logic, Spawner mission logic, or memory algorithms inside CLI.
- Do not add hidden network calls to read-model compilation.
- Do not let a status command mutate source files, installed runtimes, or release metadata.
- Do not broaden registry/installer changes while fixing a compiler bug unless the release batch explicitly calls for it.
- Keep command output honest: if proof is missing, report the missing evidence instead of filling from memory or assumptions.

## Verification Menu

- Focused command/compiler tests for the changed behavior.
- `python -m pytest tests/test_system_map.py -q` for Spark OS read-model changes.
- `python -m pytest tests/test_cli.py -q` for command or installer behavior changes.
- `python -m compileall src tests`.
- `spark verify --registry-pins --json` for registry edits.
- `spark verify --installers --json` and hosted verification only for installer batches.
- `spark os compile --json` for read-model or duplicate-truth changes.
- Privacy scan for changed serializers, generated artifacts, docs, or release metadata.
- `git diff --check`.

<!-- SPARK FLEET STANDARD BLOCK v1 — canonical source: spark-compete/fleet/AGENT_GUIDE.md.
     This same block is mirrored into every repo's AGENTS.md and CLAUDE.md. Keep in sync. -->
## How agents work in this repo (Claude, Codex, Gemini — every LLM)

Many agents and sessions work these repos at the same time. There is a tiny **automatic**
workflow that keeps you from colliding. **There are no human-review steps — CI is the only
gate, and it is automatic.** This is coordination, not bureaucracy: claim, work, PR.

### Start of work — one command, then just work normally
```
python3 ~/spark-compete/scripts/fleet.py claim <this-repo-path> <area> <task>
```
You get your **own private worktree + branch + a lease** on `<area>`, so no other agent
edits the same files. It prints the folder to `cd` into. Work there and commit as usual —
a pre-commit hook **auto-checks and renews your lease**; you never manage it by hand.

- `fleet board` — see who's working on what, right now
- `fleet handoff <agent> --note "..."` — pass your work to another agent (with context)
- `fleet release --here` — done (frees the area + removes the worktree)

### Landing work — fully automatic, no human approval
1. Open a PR to the default branch.
2. **CI is the gate.** When it's green, the PR merges. No human reviews anything.
3. Never push directly to the protected branch; never commit from the shared checkout —
   always from your worktree.

### The rules (enforced by CI, not by people)
Full ruleset: **`spark-cli/docs/harness-discipline/`** — `01_RULESET.md` (7 Prime
Directives · Red Lines RL-01..21 · Rules R-01..28) and `07_FLEET_DISCIPLINE.md` (this
workflow). The day-to-day essentials:
- A real fix targets the **root cause**, not a symptom (R-05).
- No regex / keyword / canned answer **owns authority** — it is evidence only (RL-01).
- A failure **surfaces** with a clear reason; it never becomes a fake success (RL-08).
- One worktree per task; PRs only; nothing bypasses the CI gate (F-01 / F-09).

That's the whole contract. The system handles coordination and the gate for you —
automatically, with no human in the loop.
<!-- END SPARK FLEET STANDARD BLOCK v1 -->
