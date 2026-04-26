# Spark Maintainability Governance - 2026-04-26

This is the cross-repo operating plan for keeping Spark maintainable as the ecosystem expands. It turns the April 26 review findings into rules, checks, and documentation ownership.

## Production Repo Map

| Repo | Production role | Highest-risk boundary | Required owner doc |
| --- | --- | --- | --- |
| `spark-cli` | Installer, registry, secrets, process supervision, verification | Executes module install/runtime commands and writes local config | `README.md`, `SECURITY.md`, this governance doc |
| `spark-agent-site` | Hosted install surface at `agent.sparkswarm.ai` | Serves install scripts and checksums | `README.md`, `SECURITY.md`, installer attestation docs |
| `spark-telegram-bot` | Telegram ingress and local mission relay | Receives user messages and forwards missions/memory calls | `README.md`, `SECURITY.md`, relay contract |
| `spark-intelligence-builder` | Runtime core for identity, routing, memory, and adapters | Holds most cross-system policy and prompt boundaries | rewritten `ARCHITECTURE.md`, `RUNTIME_RUNBOOK.md`, `MEMORY_CONTRACT.md` |
| `domain-chip-memory` | Default memory chip and benchmark substrate | Injects recalled memory into model prompts | `ARCHITECTURE.md`, benchmark/data policy |
| `spark-researcher` | Research/advisory/chip authoring runtime | Runs local adapter commands and writes ledgers | `ARCHITECTURE.md`, adapter command policy |
| `spark-character` | Persona, voice, and character scoring runtime | Feeds persona artifacts into prompts | `SECURITY.md`, artifact contract |
| `vibeship-spawner-ui` | Local execution/dashboard plane used by starter bundle | Receives mission relay events and runs local tasks | relay and runtime contract |

## Immediate Fix Plan

| Review finding | Fix now | Guardrail |
| --- | --- | --- |
| Registry pins lag pushed fixes | Update every blessed module pin to current remote HEAD | `spark verify --registry-pins` before calling the registry current |
| Builder depends on `spark-character@master` | Pin the git dependency to a full commit and update `uv.lock` | No floating git refs in production dependencies |
| `spark_cli/cli.py` is a control-plane god file | Extract new code by domain; start with runtime command policy | No new domain added to `cli.py` if it can live behind a module API |
| `run_shell` name lied after hardening | Rename to runtime command policy and delete `run_shell` | No `shell=True` for module/user-derived commands |

## Redlines

These are hard rules. Do not cross them without a written exception in this doc and a focused review.

1. No floating git refs in production dependencies, registry entries, installer sources, or blessed modules.
2. No production push to a blessed module without checking whether `spark-cli/registry.json` must be repinned.
3. No `shell=True` or shell command chains for user-derived, manifest-derived, or module-derived commands.
4. No new endpoint without an audit entry that names method, auth, content type, rate limit, and exposed secret surface.
5. No prompt injection of raw memory, research notes, web snippets, plugin metadata, or user-generated content without a fenced envelope and length cap.
6. No raw secrets in prompts, `.env` commits, logs, screenshots, docs, generated config, or model-visible context.
7. No new long-lived worker that caches secrets at startup unless the restart/rotation behavior is documented.
8. No module over 1,500 lines without an extraction ticket. No file over 3,000 lines without a named owner and refactor plan.
9. No live repo without `README.md`, `SECURITY.md`, `.gitignore`, tests, and a documented smoke command.
10. No history rewrite, force-push, destructive temp cleanup, or credential deletion without an explicit approval step.

## Session Protocol

Every Spark engineering session should follow this shape.

Start:

1. `git status --short --branch` in every touched repo.
2. Confirm whether touched repos are blessed modules in `spark-cli/registry.json`.
3. State the test plan before edits.
4. If changing dependencies, identify lockfiles and update them in the same slice.

During:

1. Commit each logical slice: code, dependency pin, docs, CI, or registry update.
2. Keep unrelated untracked files untouched.
3. Prefer extraction over adding more responsibilities to existing large files.
4. Add a regression test for every security or behavior fix.

End:

1. Run focused tests and any affected verify commands.
2. Run `spark verify --provenance` after registry/provenance edits.
3. Run `spark verify --registry-pins` after any blessed module push.
4. Update docs or explicitly list deferred docs.
5. Push touched repos only after the registry and lockfiles are coherent.

## Required Local Checks

| Repo | Minimum check before push |
| --- | --- |
| `spark-cli` | `python -m pytest tests/test_cli.py -q`; `python -m spark_cli.cli verify --provenance --json`; `python -m spark_cli.cli verify --registry-pins --json` |
| `spark-telegram-bot` | `npm run build`; `npm test`; `npm audit --omit=dev --audit-level=moderate` |
| `spark-intelligence-builder` | affected `python -m pytest ...`; `uv lock --check`; secret scan for `.env`, JWTs, and provider keys |
| `domain-chip-memory` | affected `python -m pytest ...`; prompt-boundary tests for memory injection changes |
| `spark-researcher` | affected `python -m pytest ...`; adapter command-policy tests for command changes |
| `spark-character` | affected `python -m pytest ...`; artifact/package data check when persona files move |
| `spark-agent-site` | installer hardening workflow equivalent: shell syntax, PowerShell parse, checksum validation, Docker build |

## Documentation Rewrite Map

| Area | Action |
| --- | --- |
| Cross-repo system map | Create one canonical `SPARK_SYSTEM_MAP.md` that describes repo roles, install flow, runtime flow, secret flow, and trust boundaries. |
| Builder docs | Collapse dated handoffs into `ARCHITECTURE.md`, `RUNTIME_RUNBOOK.md`, `TELEGRAM_BRIDGE.md`, `MEMORY_CONTRACT.md`, and `SECURITY.md`. Archive session logs separately. |
| Agent site docs | Add `README.md` and `SECURITY.md` for hosted installer deployment, checksums, attestation, CSP, HSTS, and rollback. |
| Character docs | Add `SECURITY.md` and artifact contract for persona files, provider base URLs, overlays, and scoring exports. |
| Repo contribution docs | Add `CONTRIBUTING.md` to each live repo with setup, tests, lockfile policy, secret policy, and release checklist. |
| Security tracker | Keep `docs/SECURITY_GAP_TRACKER_2026-04-26.md` updated until all P0/P1 security gaps are either closed or intentionally deferred. |

## Refactor Rules

When a file crosses 1,500 lines, new work should prefer a local extraction. When a file crosses 3,000 lines, create a refactor plan before adding new domains to it.

Suggested first extractions:

| Repo | File | Extraction |
| --- | --- | --- |
| `spark-cli` | `src/spark_cli/cli.py` | `registry_policy.py`, `secret_store.py`, `autostart.py`, `doctor.py`, `approval.py` |
| `spark-telegram-bot` | `src/index.ts` | message routing, command handlers, startup/config validation |
| `spark-telegram-bot` | `src/missionRelay.ts` | relay auth, event formatting, rate limiting, local endpoint server |
| `spark-intelligence-builder` | `adapters/telegram/runtime.py` | transport, command router, memory bridge, auth/correlation |
| `spark-intelligence-builder` | `researcher_bridge/advisory.py` | provider resolution, prompt construction, execution adapter, output parsing |
| `domain-chip-memory` | `cli.py` | benchmark commands, memory commands, chip packaging, provider diagnostics |
| `domain-chip-memory` | `sample_data.py` | move large fixtures to JSONL/data assets loaded through typed loaders |

## Registry Rules

The registry schema lives at `schemas/registry.schema.json`. The CLI still performs runtime validation, but the schema is the documentation and CI contract for external tooling.

Required for blessed modules:

- `source`: canonical HTTPS git source
- `commit`: full 40-character SHA
- `require_signed_commit`: present, even while false/report-only
- `blessed`: true
- `summary`: human-readable role

After any blessed module push:

```bash
python -m spark_cli.cli verify --registry-pins --json
python -m spark_cli.cli verify --provenance --json
```

## CI Baseline

Each live repo should get a small required CI workflow with:

1. Install dependencies from lockfile.
2. Run focused unit tests.
3. Run type/build check where applicable.
4. Run dependency audit.
5. Run gitleaks or equivalent secret scan.
6. Run repo-specific smoke checks.

CI should be boring and strict. If a check is too flaky to require, make it a separate manual workflow and document why.
