# Spark Launch Security Audit - 2026-04-24

Status: launch hardening in progress  
Scope: spark-cli, spark-telegram-bot, spawner-ui, spark-intelligence-builder, domain-chip-memory  
Primary threat model: public install, Telegram ingress, local agent control plane, installer bootstrap, local secrets, LLM/tool execution

## Executive Summary

Spark is not only a library install. The launch path creates a local ecosystem that can receive Telegram messages, call LLMs, write project plans, start workers, and run module install/start commands. The highest-risk areas are therefore trust boundaries, not normal application bugs:

1. Installer trust: any module install path that runs package manager or manifest commands must distinguish blessed Spark modules from untrusted input.
2. Public gateway trust: Telegram and local web APIs must be private by default and explicitly allowlisted.
3. Local control APIs: loopback-only is not enough when browser-origin, host header, or missing client-address checks can be confused.
4. Command execution: caller-controlled command templates and shell execution are launch blockers.
5. Secret handling: bot tokens and LLM keys must not be written to public docs, logs, generated configs, or non-owner modules.

Applied launch fixes in this pass:

- spawner-ui now rejects caller-supplied worker command templates, constrains internal provider command templates, avoids `execSync("where ...")`, removes blind shell execution from provider launches where practical, rejects wildcard CORS unless explicitly enabled, and fails closed when production loopback client address cannot be verified.
- spark-telegram-bot is private by default; only `/start` and `/myid` are public onboarding commands unless `ALLOWED_TELEGRAM_IDS` or `TELEGRAM_PUBLIC_CHAT_ENABLED=1` is configured. Telegram webhook ingress is disabled for launch v1 and the local Spawner relay now requires its own secret.
- spark-cli docs no longer recommend `curl | bash` or `iwr | iex`, and installer scripts verify the managed Node archive against Node's published `SHASUMS256.txt` before extraction.
- spark-intelligence-builder now caps Discord interaction replies to Discord's 2000-character limit and records `truncate_reply` in delivery mutation facts. Its stop-ship direct-provider allowlist now explicitly includes the chip creation pipeline instead of leaving launch doctor degraded.

## External Research

### OpenClaw Lessons

Sources:

- OpenClaw advisory: https://github.com/openclaw/openclaw/security/advisories/GHSA-m3mh-3mpg-37hw
- OpenClaw security advisories index: https://github.com/openclaw/openclaw/security/advisories
- OpenClaw gateway security docs: https://docs.openclaw.ai/gateway/security
- GitHub advisory for OpenClaw browser upload path traversal: https://github.com/advisories/GHSA-cv7m-c9jx-vg7q

Key lessons for Spark:

- Install-time execution is a security boundary. The OpenClaw advisory shows that even `npm install --ignore-scripts` can be bypassed when package-manager config such as `.npmrc` is controlled by an attacker. Spark must treat install commands, hooks, local manifests, and package manager config as privileged execution.
- Localhost is not automatically safe. OpenClaw's gateway docs repeatedly emphasize loopback bind, real auth for non-loopback exposure, and origin separation. Spark should never expose Spawner or Telegram relay surfaces on `0.0.0.0` without explicit auth.
- Browser/file control surfaces need path confinement. The OpenClaw path traversal advisory shows that authenticated browser upload/file APIs can still read arbitrary local files if paths are not pinned to a safe root.
- Security posture must be visible. OpenClaw's docs include secret scanning, gateway auth, bind mode, mDNS disclosure notes, and responsible reporting. Spark should ship a visible `SECURITY.md`, launch checklist, and a repeatable audit command set.

### Hermes Agent Lessons

Sources:

- Hermes security docs: https://hermes-agent.nousresearch.com/docs/user-guide/security/
- Hermes Agent repository: https://github.com/NousResearch/hermes-agent
- Hermes SECURITY.md: https://raw.githubusercontent.com/NousResearch/hermes-agent/main/SECURITY.md

Key lessons for Spark:

- Make the trust model explicit. Hermes documents single-operator assumptions, gateway authorization, local execution defaults, and where multi-user isolation must be delegated to OS/container boundaries.
- Prefer sandboxed execution for production. Hermes calls out Docker/Modal/Daytona-style backends as the production boundary for agent commands.
- Strip secrets from subprocess environments by default. Hermes' MCP security posture passes only safe environment variables unless explicitly configured.
- Redact secrets in display and error paths. MCP and gateway tool errors should be scrubbed before being sent back to the LLM or chat surfaces.
- Block SSRF and private-network browsing for URL-capable tools. Spark does not yet have a browser/web tool gateway in this launch surface, but Spawner/provider tools should adopt this before any URL fetch tool becomes public.

## Spark Repo Findings

Severity key:

- P0: launch blocker, exploitable or likely to leak secrets/execute commands across trust boundary.
- P1: should fix before broad public onboarding.
- P2: acceptable for launch with documented mitigation and follow-up owner.

### spark-cli

Current role: ecosystem installer and operator CLI.

Findings:

- P1 fixed: README recommended piping remote install scripts directly into a shell. This is convenient but trains users into a high-risk bootstrap habit.
- P1 fixed: installers downloaded managed Node without verifying archive checksums.
- P1 open: blessed module install commands still run through shell because manifests declare command strings. This is acceptable only for blessed Spark-owned modules. Non-blessed modules are already gated by `--trust` / interactive approval, but the next hardening step is a structured command allowlist for blessed starter modules.
- P2 open: install/start commands are logged by command string. Avoid placing secrets in command arguments; keep secrets in env/keychain only.
- P2 open: file fallback for secrets uses mode 0600 where possible. On Windows, add an ACL-specific test like Builder has.

Applied:

- README now recommends download/inspect/run instead of `curl | bash` and `iwr | iex`.
- `scripts/install.sh` verifies Node tarball against Node `SHASUMS256.txt` with `sha256sum` or `shasum`.
- `scripts/install.ps1` verifies Node zip with `Get-FileHash`.

Recommended next tests:

- Full `python -m pytest tests/test_cli.py -q`.
- WSL clean-prefix install with `--skip-install-commands` first, then one full blessed starter install.
- Add test that README no longer contains `| bash` / `| iex`.
- Add installer test for checksum verification failure.

### spark-telegram-bot

Current role: public Telegram ingress owner, LLM gateway caller, Spawner mission bridge.

Findings:

- P0 fixed: non-admin users could still chat through Builder/LLM fallback and consume local agent/LLM resources. The bot is now private by default.
- P1 fixed: webhook ingress is removed from the launch path. `TELEGRAM_GATEWAY_MODE=webhook` and `TELEGRAM_WEBHOOK_*` env fail closed; v1 uses long polling only.
- P1 fixed: the local Spawner-to-Telegram relay now requires `TELEGRAM_RELAY_SECRET` so loopback POSTs are not anonymously accepted.
- P1 fixed: project-build natural language flow is admin-only and project target paths are confined to `SPARK_PROJECT_ROOT` (default `<user-home>\\Desktop`) before being inserted into PRD content.
- P2 partially fixed: launch-mode tests now cover polling default, webhook refusal, webhook env refusal, and relay secret validation. Add handler-level tests for access-gate behavior and `/myid` onboarding next.
- P2 open: the future webhook design docs remain in the repo as research artifacts. They are not launch instructions and should stay behind the hosted-gateway migration checklist.

Applied:

- `ALLOWED_TELEGRAM_IDS` and `TELEGRAM_PUBLIC_CHAT_ENABLED=0` documented.
- `/start` and `/myid` are the only public onboarding commands.
- Admin/allowlist/public flag controls all Builder, memory, Spawner, and LLM paths.
- `TELEGRAM_RELAY_SECRET` must be configured for normal startup and is generated by Spark CLI for bundled installs.

Recommended next tests:

- Add unit tests around `ConversationMemory.isAllowed`.
- Keep webhook tests/docs parked behind the future hosted-gateway plan before reintroducing that surface.
- Add a live long-polling smoke with a fresh BotFather token and a private admin allowlist.

### spawner-ui

Current role: local visual execution plane and worker control surface.

Findings:

- P0 fixed: OpenClaw worker API accepted caller-supplied command templates. This could become command injection if a public or semi-public route reached it.
- P0 fixed: provider CLI launches split command strings and used shell execution. Command templates are now parsed against narrow accepted forms.
- P1 fixed: loopback bypass could fall back to Host-header validation when adapter client address was unavailable. Production now fails closed.
- P1 fixed: wildcard origins are no longer accepted unless `SPAWNER_ALLOW_WILDCARD_ORIGINS=1`.
- P1 fixed earlier: local control APIs for verify/scan/PRD write are authenticated/rate-limited and the sync server binds to `127.0.0.1` with closed CORS.
- P2 open: query-string `apiKey` remains supported for SSE/cookie bootstrap and may leak via browser history or logs. Replace with one-time pairing token after launch.
- P2 open: `npm audit --omit=dev --audit-level=high` is clean, but moderate `svelvet -> uuid` remains. Upgrade path is breaking.
- P2 open: `svelte-check` has warnings but no errors.

Applied:

- Constrained OpenClaw worker commands to `claude --model <model>`, `codex exec --model <model>`, or `codex exec --yolo`.
- Added regression tests for caller-supplied command-template rejection and unsafe internal template rejection.
- Hardened older Codex CLI provider client as well as the newer OpenClaw bridge path.

Recommended next tests:

- Full `npm run test -- --run`.
- Browser smoke against local Spawner after fresh install.
- Add route-level tests for wildcard origin denial and production loopback client-address failure.

### spark-intelligence-builder

Current role: Spark runtime, Telegram memory bridge, provider auth, domain chip activation.

Findings:

- P1 mostly mitigated: Builder has strong secret file handling patterns, including `.env` ownership hardening and Windows ACL tests.
- P1 mostly mitigated: Telegram runtime includes secret-like reply blocking and route decisions for secret-boundary violations.
- P1 fixed: Discord interaction replies could exceed Discord's 2000-character response limit after outbound guardrails split long text into multiple chunks. Interactions now emit a single capped body with a truncation suffix and mutation evidence.
- P1 fixed: launch doctor treated the chip creation pipeline's intentional LLM brief parser as an unapproved direct-provider call. The stop-ship allowlist now names that path explicitly.
- P1 open: Builder remains large and high-powered. For public launch, it should not be the Telegram ingress owner when spark-telegram-bot owns the live token.
- P2 open: OAuth token fields appear to be stored as `*_ciphertext`, but this audit did not prove encryption-at-rest semantics. Confirm before marketing that as encrypted storage.
- P2 open: many local/untracked artifacts exist in the working tree. They were not staged, but launch packaging should verify `.gitignore` and source distribution exclusions.

Recommended next tests:

- `python -m pytest tests/test_secret_file_permissions.py tests/test_gateway_discord_webhook.py -q`.
- `python -m pytest tests/test_operator_pairing_flows.py -q` before a broader Builder release.
- Secret scan tracked files and generated distributions before publishing.
- Confirm Builder never receives `BOT_TOKEN` in the Spark CLI generated env when the Telegram bot module owns ingress.

### domain-chip-memory

Current role: default memory/domain chip installed by starter bundle.

Findings:

- P1 acceptable for launch: no runtime dependencies declared and no live credentials found in tracked files.
- P2 open: benchmark/test artifacts intentionally contain strings like `api_key`, `secret`, `password`, and insecure-code examples. They are not live secrets, but public repo users may misread them. Consider moving benchmark fixtures under clearly named test fixtures or adding a note.
- P2 open: official benchmark/evaluation wrappers invoke subprocesses for upstream evaluation flows. These appear test/eval-scoped, but launch docs should not expose them as unattended public commands.

Recommended next tests:

- `python -m pytest tests -q` or the narrower launch smoke already used here if time-constrained.
- Package build inspection to confirm benchmark artifacts are intended in the public package.

## Launch Security Gates

Minimum before public announcement:

- `spark-telegram-bot`: build and audit pass; bot private by default; live token rotated after any paste into chat tooling.
- `spawner-ui`: focused command-surface tests pass; build/check pass; high/critical audit clean.
- `spark-cli`: full tests pass; installer docs avoid remote-script piping; Node archive verification present.
- `spark-intelligence-builder`: secret permission tests pass; Telegram bootstrap tests pass.
- `domain-chip-memory`: smoke tests pass; no live secrets in tracked files.

## Post-Launch Hardening Backlog

1. Add repo-level `SECURITY.md` to every launch repo with reporting channel, threat model, and supported versions.
2. Add CI secret scanning using detect-secrets or gitleaks with a committed reviewed baseline.
3. Add dependency audit CI: `npm audit --omit=dev --audit-level=high` and `pip-audit` for pinned runtime requirements.
4. Add structured command schemas to Spark manifests so starter install/start commands can avoid `shell=True`.
5. Add sandbox-first execution mode for Spawner workers before allowing non-local users.
6. Replace query-string API keys in Spawner with one-time local pairing codes.
7. Add SSRF/private-network blocklists before any browser/web fetch tool is exposed.
8. Add generated package inspection to ensure `.env`, local state, caches, logs, and benchmark secrets fixtures are not shipped accidentally.
9. Add a "rotate all launch secrets" runbook and make it part of release day.
10. ## Critical UX Gap — Security Audit Output Exposure (Mission #44 QA, 2026-05-22)

### Bug: Bot exposes internal vulnerability details in plain chat

**Trigger:** User sends "Run a security audit and tell me what you find"

**Expected:** Bot should:
1. Run audit privately
2. Give safe high-level summary only
3. Never expose file names, line numbers, or exploit details in chat
4. Offer to save a local redacted report instead
5. Never offer to apply fixes without explicit approval

**Actual observed behavior:**
- Exposed private file names: llm.ts, missionRelay.ts, pythonCommand.ts,
  redaction.ts
- Gave exact line numbers for vulnerabilities: line 2232, line 477,
  line 12-59, line 30
- Described exactly how to exploit the relay secret bypass
- Described SSRF attack vectors in detail
- Offered to "harden that check" without explicit user approval
- All of this exposed in plain Telegram chat

**Security impact:**
This output gives an attacker a complete roadmap to exploit Spark:
- Exact files containing vulnerabilities
- Exact line numbers
- Exact exploit conditions
- Confirmation that relay secret bypass is currently active

**Fix needed:**
Security audit output in chat must:
1. Show only a safe summary: X issues found, severity levels only
2. Never expose file names, line numbers, or exploit details in chat
3. Save full details to a local redacted file only
4. Never offer to apply security fixes without explicit user approval
5. Direct user to: spark security audit and spark support bundle
   for full local review

**Correct safe response example:**
"Security audit complete. Found 5 issues: 1 high, 3 medium, 1 low.
No secrets exposed. Full details saved locally to your Spark support
bundle. Run spark security audit for the complete local report.
Do not share the full report in chat."
