# Spark Security Gap Tracker - 2026-04-26

This tracker is the cross-repo source of truth for the April 26 hardening pass. Keep it updated before and after each security slice so state does not disappear across repos.

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Rotated Telegram token history check | Verified | Custom Git history scan and gitleaks 8.30.1 scan across `spark-cli`, `spark-intelligence-builder`, `spark-telegram-bot`, `domain-chip-memory`, `spark-researcher`, `spark-character`, and `spark-agent-site` found no rotated Telegram-token prefix hits. |
| Rotated MiniMax key history check | Verified | Custom Git history scan and gitleaks 8.30.1 found no rotated MiniMax-key prefix hits. |
| Live `.env` / temp working files | Contained locally | Current-tree scan still sees local `.env`, `.env.override`, `.env.dspy.local`, and many Builder `.tmp-*` homes, but follow-up `git ls-files` and `git check-ignore` showed those paths are ignored rather than tracked. Do not print or commit their contents. |
| History rewrite | Deferred | No `git filter-repo` rewrite is planned unless a real committed secret is found. Rewriting history and force-pushing remain destructive coordinated work requiring explicit approval. |
| Blessed module commit pins | Done | `registry.json` blessed Git modules are pinned to full commits and registry validation refuses missing pins. |
| Registry pin drift verification | Done | `spark verify --registry-pins` compares blessed registry pins against remote HEAD and fails on lag/divergence. Run it after every blessed module push. |
| Module provenance / attestations | Started | `spark verify --provenance` reports commit-pin, signed-commit, and attestation posture in report-only mode. Signature and attestation enforcement are intentionally not breaking installs yet. |
| Floating production git dependencies | Contained | Builder's `spark-character` dependency is pinned to a full commit and represented in `uv.lock`. No production dependency should use branch refs such as `@master`. |
| Private JSON linked-path protection | Done | Spark private JSON writes refuse symlink/reparse-point paths. |
| Generated env linked-path protection | Done | Generated module env writes and cleanup now use the same linked-path guard plus write-boundary checks. |
| Endpoint audit | Started | See `docs/ENDPOINT_AUDIT_2026-04-26.md`. Builder and Telegram local relay surfaces are documented with current auth posture. |
| Per-request secret resolution | Checked | Builder Discord/WhatsApp webhook secrets resolve through `ConfigManager.read_env_map()` during request handling. CLI runtime envs resolve secrets at process launch; rotation still needs restart for long-lived child processes. |
| Provider base URL overrides | Done | `domain-chip-memory` now validates OpenAI and MiniMax base URLs as HTTPS, credential-free, query/fragment-free URLs on known provider hosts before constructing clients. |
| Researcher adapter subprocess config | Done | `spark-researcher` adapter env/CLI command overrides now validate executables against per-adapter allowlists. The generic adapter is disabled by default and requires an explicit executable allowlist. |
| Module runtime shell execution | Done | `spark-cli` module hooks, healthchecks, ready checks, and process starts now parse runtime commands to argv and run without `shell=True`; supported runtime tools are allowlisted. |
| Runtime command policy ownership | Done | Runtime argv parsing and execution moved into `src/spark_cli/runtime_policy.py`; the misleading `run_shell` API was removed. |
| Approval engine | Planned only | Sensitive-action approval policy is deliberately deferred. See `docs/APPROVAL_ENGINE_PLAN_2026-04-26.md` for scope, rollout phases, and test requirements before implementation. |
| Docker sandbox | Deferred optional | Docker isolation should stay optional and additive. It should not be required for normal local Spark usage. |
| T11 sustained-attack tier | Deferred | Do not focus implementation now, but keep spark-character structure compatible with adding the tier later. |
| Dependency audit baseline | Checked | `spark-telegram-bot` `npm audit` and pip-audit checks for `spark-cli`, `domain-chip-memory`, `spark-researcher`, and `spark-character` reported no known vulnerabilities. `spark-agent-site` has no package manifest; do not attribute parent-directory npm findings to it. |

## Secret Verification Notes

Non-destructive checks run on 2026-04-26:

- `git log --all --name-only` plus `git grep`-style content checks for committed `.env` paths, Telegram token shape, rotated Telegram prefix, MiniMax key shape, rotated MiniMax prefix, `sk-` style keys, JWT shape, and sensitive env names.
- Current working-tree scan excluding `.git` and large files for `.env` paths and secret-looking content.
- `git ls-files`, `git check-ignore -v`, and `git status --ignored --short` on local env/temp paths in the repos with hits.

Result:

- History scan found only example env filenames such as `.env.example` / `.env.dspy.example`; no rotated secret prefix hits.
- Working-tree hits are local ignored files or placeholder/test strings. Treat them as private local material and keep them out of commits.
- A full gitleaks baseline would still be useful before any public security claim, but the current custom scan does not justify a history rewrite.

## Remaining Work Queue

1. Decide whether to delete local ignored Builder `.tmp-*` homes after exporting anything useful. This is a local destructive cleanup and should be explicit.
2. Add real Sigstore or cosign attestation metadata to each blessed module once the report-only verifier has aged safely.
3. Turn provenance enforcement on gradually: first fail only missing commit pins, then warn on unsigned commits, then require attestations for blessed modules.
4. Add narrow endpoint regression tests whenever a new HTTP listener or public route is introduced.
5. Implement the approval engine only after the report-only classifier plan in `docs/APPROVAL_ENGINE_PLAN_2026-04-26.md` is reviewed.
6. Add a standard SBOM/dependency audit command per repo so future audits do not depend on ad hoc local tooling.
7. Restart long-lived Spark child processes after secret rotation so launch-time env resolution picks up new values.

## Gitleaks Scan - 2026-04-26

Tool: gitleaks 8.30.1, downloaded locally into `C:\Users\USER\Desktop\spark-security-audit-reports`.

| Repo | Initial result | Resolution |
| --- | --- | --- |
| `spark-cli` | 0 findings | Clean. |
| `spark-intelligence-builder` | 4 findings | False positives from synthetic secret-boundary test vectors in `tests/test_builder_prelaunch_contracts.py`. Added a narrow `.gitleaks.toml` allowlist and split the current encoded JWT fixture; rerun was clean. |
| `spark-telegram-bot` | 0 findings | Clean. |
| `domain-chip-memory` | 4 findings | False positives from historical LongMemEval benchmark artifact text containing redacted placeholders and password-discussion examples. Added a narrow `.gitleaks.toml` allowlist for those ignored benchmark artifact paths; rerun was clean. |
| `spark-researcher` | 0 findings | Clean. |
| `spark-character` | 0 findings | Clean. |
| `spark-agent-site` | 0 findings | Clean. |

Conclusion: no evidence of the rotated Telegram bot token or rotated MiniMax key remains in scanned Git history. The only scanner findings were documented false positives, now handled by repo-local gitleaks configs. No history rewrite is justified by this scan.

## Destructive Actions Requiring Fresh Confirmation

- `git filter-repo`, BFG, or any history rewrite.
- Force-push after history rewrite.
- Deleting local `.env`, `.tmp-*`, state DB, or artifact directories.
- Removing production installer/autostart entries from a live machine.
