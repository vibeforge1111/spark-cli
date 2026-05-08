# Spark CLI Production Prep Tasks

**Last updated:** 2026-05-08
**Branch:** `codex/fix-railway-smoke-remote-failures-20260508`
**Push status:** prepared locally; do not push until paired Spark repo updates are ready.

## Current State

Spark CLI is through the main Railway/VPS/remote-sandbox hardening work. The
remaining work is release hygiene and cross-repo coordination, not a new feature
build-out.

Verified locally:

- `python -m pytest` -> 497 passed, 5 skipped
- `python -m spark_cli.cli verify --installers --json` -> OK
- `python -m spark_cli.cli verify --installers --hosted-installers --json` -> OK
- `python -m spark_cli.cli verify --sandboxes --json` -> OK
- `python -m spark_cli.cli support bundle --json` -> no raw local path leak found
- `git diff --check` -> OK

Expected local-only limitation:

- `verify --hosted --json` and `live verify --json` can fail on this desktop
  when no hosted LLM provider/API keys are configured. That is an environment
  readiness signal, not a Spark CLI code blocker.

## Completed Phases

- [x] Read user feedback and convert it into a production hardening scope.
- [x] Hide paused Spark Pro connection-token and bearer-token surfaces from
  user-facing docs and diagnostics.
- [x] Document Railway/VPS hosted Spark Live deployment and verification paths.
- [x] Add secure SSH sandbox docs and CLI readiness checks.
- [x] Add secure Modal sandbox docs and no-secret smoke checks.
- [x] Align OWASP/agentic security docs with the shipped sandbox surfaces.
- [x] Add launch runbook release gates for installers, sandboxes, and hosted
  Spark Live.
- [x] Harden SSH/Modal diagnostics against secrets, URL credentials, private
  key paths, bearer tokens, and local audit paths.
- [x] Harden public diagnostics, support bundle output, and installer
  provenance against raw local path leaks.
- [x] Verify installer, sandbox, support bundle, and test-suite gates locally.
- [x] Prepare agent-facing safe sandbox guidance and future installer option
  docs without advertising them as shipped installer features.
- [x] Prepare detailed sandbox test runbook and evidence template for the May 9,
  2026 SSH, Modal, Railway/VPS, and Telegram smoke session.

## Remaining Phases

### Phase 1: Final Cosmetic Security Normalization

Optional but recommended before the bundled push.

- [x] Normalize generic repair hints such as
  `~/.spark/config/secrets.local.json` to `<spark-home>/config/...` in
  shareable JSON output.
- [x] Re-run focused diagnostics after that change.
- [x] Commit the normalization if changed.

### Phase 2: Cross-Repo Release Bundle

Required before production push.

- [ ] Wait for the paired Spark repo updates the user wants to ship together.
- [x] Re-run the Spark CLI launch gate from `docs/LAUNCH_RUNBOOK.md` on the
  current prepared branch.
- [x] Run the hosted installer gate against `https://agent.sparkswarm.ai`.
- [ ] Run a real Railway/VPS smoke when production credentials are available.
- [ ] Re-run the launch gate again after paired Spark repo updates are landed
  into the final push bundle.
- [ ] Push only after the full Spark update set is ready.

Latest Phase 2 prep check:

- `python -m pytest` -> 497 passed, 5 skipped
- `python -m spark_cli.cli verify --installers --json` -> OK
- `python -m spark_cli.cli verify --installers --hosted-installers --json` -> OK
- `python -m spark_cli.cli verify --sandboxes --json` -> OK
- `python -m spark_cli.cli verify --registry-pins --json` -> OK
- `python -m spark_cli.cli verify --provenance --json` -> OK
- `git diff --check` -> OK
- safe sandbox agent guidance and future installer option docs are prepared
- detailed sandbox test runbook and evidence template are prepared
- `python -m spark_cli.cli verify --hosted --json` -> expected local failure:
  no hosted LLM provider configured in this desktop environment
- `python -m spark_cli.cli live verify --json` -> expected local failure:
  hosted mission smoke needs production API keys

## Deferred On Purpose

These are not blockers for this release and should not be advertised as shipped:

- SSH prepare/deploy, remote log tailing, and arbitrary remote shell.
- Modal arbitrary run, artifact pull, persistent volumes, and provider-secret
  passthrough.
- Spark Pro connection tokens and bearer-token entitlement flow.
- Public inbound hosted services beyond the reviewed Spark Live lane.
