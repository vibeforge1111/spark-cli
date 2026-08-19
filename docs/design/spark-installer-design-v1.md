# Spark Installer — v1 Design

**Status:** draft for review (2026-04-22)
**Companion doc:** [lessons-from-todays-install.md](./lessons-from-todays-install.md)

## Goals

1. **First-time user gets to "working Spark" in three commands.** Install Spark,
   run setup wizard, start. No editing config files, no choosing between
   Python venvs, no reading 4 READMEs.
2. **Builders can ship a Spark module without asking permission.** Anyone can
   publish a chip, skill graph, or tool that installs cleanly via
   `spark install <git-url>`.
3. **Composable.** Users pick what they need. Modules declare what they
   `provide` and `need`. The installer enforces compatibility and prevents
   conflicts (e.g. two Telegram gateways with the same token).
4. **Same logic powers CLI, dashboard, and web installer.** No rewriting the
   install flow three times.

## Non-goals (v1)

- Background daemon (defer; CLI-foreground is fine for v1).
- Windows support (defer to v1.1; macOS + Linux only at launch).
- Hosted package CDN (defer; clone-from-git with `bun`/`uv` is fast enough).
- Mobile app (defer; dashboard via web is the v1 control surface).
- Auto-update of installed modules (defer; users run `spark update <module>`
  explicitly).

## Architectural decisions

### Decision 1: Hybrid registry (blessed + arbitrary URLs)

A central `registry.json` lives in the public Spark org repo
(`github.com/spark/registry`). It lists curated, version-pinned modules:

```json
{
  "modules": {
    "memory": {
      "source": "github.com/spark/spark-memory",
      "blessed": true,
      "summary": "Persistent memory for Spark agents"
    },
    "spawner-ui": {
      "source": "github.com/spark/spawner-ui",
      "blessed": true,
      "summary": "Visual canvas for mission building"
    }
  }
}
```

`spark install memory` resolves through the registry. `spark install
github.com/anyone/cool-chip` works for any repo with a valid `spark.toml`.
Builders submit a PR to add their module to the blessed list — no backend
needed. Graduates to a hosted index when there's enough volume to justify it.

### Decision 2: Clone-based v1 with `bun` + `uv`

Modules ship source. The installer runs `bun install --frozen-lockfile` for
Node modules and `uv pip install` for Python modules — both an order of
magnitude faster than npm/pip. Users never type either command.

The `spark.toml` manifest declares both `[install.dev]` and `[install.release]`
blocks from day one. v1 only uses `dev`. When you stand up a Spark CDN later,
modules add `release` artifacts and `spark install --release` flips to
prebuilt downloads — no manifest redesign.

### Decision 3: CLI-first, dashboard on demand, no daemon

`~/.spark/` is the single source of truth for state, config, and module
metadata. The CLI reads/writes it directly. The dashboard is a SvelteKit app
launched by `spark dashboard` — runs in foreground, opens browser, exits
when user closes the tab. The web installer at `sparkswarm.ai/install` shells out
to a one-shot local helper (à la `npx create-*`) that uses the same CLI logic.

When you genuinely need a background process later (push notifications,
cross-device sync, scheduled jobs), introduce `sparkd`. Don't pay the cost
upfront for features you don't have yet.

## The `spark.toml` manifest

The single most important artifact in this design. Every module has one at its
root. The installer reads only this file to know how to install, configure,
healthcheck, and uninstall the module.

```toml
[module]
name = "memory"
version = "0.3.0"
description = "Persistent memory for Spark agents"
homepage = "https://github.com/spark/spark-memory"
license = "MIT"

[runtime]
kind = "python"           # python | node | go | rust | binary
version = ">=3.11"        # semver range; installer will offer to install if missing

[install.dev]
# Run from cloned source. v1 uses this exclusively.
commands = ["uv pip install -e ."]

[install.release]
# Prebuilt artifact. Ignored in v1; documented for future use.
artifact = "https://cdn.sparkswarm.ai/memory/{{version}}/memory-{{platform}}.tar.gz"
sha256 = "..."

[provides]
# What capabilities this module exposes. Other modules can `need` these.
capabilities = ["memory.store", "memory.recall", "memory.search"]
binary = "spark-memory"   # name of the CLI this module installs (optional)

[needs]
# Other Spark modules this module depends on.
modules = []
# Capabilities required from any provider (registry resolves to a concrete module).
capabilities = []
# Secrets the module reads at runtime — declared here so the wizard knows to ask.
secrets = []

[secrets.openai_api_key]
# Optional. Only declare if [needs.secrets] includes it.
prompt = "OpenAI API key (only if you want OpenAI as a fallback provider)"
required = false
storage = "keychain"      # keychain | file | env
env_var = "OPENAI_API_KEY"

[healthcheck]
command = "spark-memory doctor"
timeout_seconds = 10
# Exit code 0 = healthy. Stdout/stderr captured for `spark status --verbose`.

[hooks]
post_install = "spark-memory init"
pre_uninstall = "spark-memory shutdown"
post_uninstall = ""       # optional cleanup; runs after files are removed

[paths]
# All paths declared here are auto-created and exposed as env vars to the module.
# Module code references $SPARK_MODULE_HOME etc., never hard-coded paths.
home = "~/.spark/modules/memory"
state = "~/.spark/state/memory"
logs = "~/.spark/logs/memory"
```

Schema is versioned: `spark.toml` itself implies schema v1. Future versions
add a `schema = 2` field; the CLI handles old + new manifests.

## CLI surface (v1)

```
spark setup                    # interactive wizard, run once after install
spark install <module>         # by name (registry) or git URL
spark uninstall <module>       # runs pre_uninstall hook, removes files, rotates secrets
spark update [module]          # update one or all
spark list                     # installed modules with version + status
spark status [--verbose]       # healthcheck all modules
spark start [module]           # launch long-running modules (telegram bot, dashboards)
spark stop [module]            # stop running modules
spark dashboard                # open browser dashboard (foreground)
spark config get/set <key>     # read/write user config
spark secrets set <key>        # store a secret in keychain (for re-keying)
spark doctor                   # run all healthchecks + diagnostic env dump
spark logs <module>            # tail module logs
```

### `spark setup` flow

1. Detect existing tools: Claude Code? Bun? uv? Telegram CLI? Record what's
   found; offer to install what's missing via Homebrew.
2. Read blessed registry. Show curated bundles ("Starter: telegram + canvas",
   "Full: telegram + canvas + memory + skill graphs"). User picks.
3. Resolve dependencies. Show the resulting module graph for confirmation.
4. Collect required secrets (one prompt per `[secrets.*]` block across all
   selected modules, deduped). Skip any secret already inferable
   (Claude Code OAuth → no `ANTHROPIC_API_KEY` needed).
5. Install each module: clone → `uv`/`bun` → run `post_install` hook.
6. Run all healthchecks. Show status.
7. Optionally `spark start` everything that's start-able.

### `spark install <module>` lifecycle

```
1. Resolve         registry lookup OR validate git URL
2. Fetch           git clone --depth=1 to ~/.spark/modules/<name>/
3. Validate        parse spark.toml, check schema, check runtime version
4. Conflict check  fail if `provides.capabilities` overlap with installed modules
                   (with --force to override after warning)
5. Runtime install  uv/bun install
6. Secrets         prompt for any [needs.secrets] not already in keychain
7. Hook            run post_install
8. Healthcheck     run [healthcheck.command]; fail install if it returns non-zero
9. Register        write entry to ~/.spark/state/installed.json
```

Each step is idempotent and resumable. `spark install --resume` picks up where
a failed install left off.

### `spark uninstall <module>` lifecycle

```
1. pre_uninstall hook
2. Stop module if running
3. Remove ~/.spark/modules/<name>/ and state/ and logs/
4. Rotate any secrets declared as `[secrets.*]` with rotation_url set
   (e.g. "Open https://t.me/BotFather to revoke the bot token")
5. post_uninstall hook
6. Remove from installed.json
```

The rotation step addresses the principle from the lessons doc (#8 from
context): when a module is removed, its secrets are no longer trusted.

## Secrets handling

- **Storage:** OS keychain (macOS Keychain, Linux libsecret, Windows Cred
  Manager) via a thin shim. Falls back to AES-encrypted file in
  `~/.spark/secrets.enc` if no keychain available, with a master passphrase.
- **Module access:** at runtime, modules read secrets from env vars (declared
  via `[secrets.*].env_var`). The CLI exports them when invoking module
  binaries via `spark start <module>`. Modules never see the keychain
  directly.
- **Rotation:** `spark secrets set <key>` updates keychain and prompts for
  module restarts.
- **Audit:** `spark secrets list` shows what's stored (key names, never values).

## Module composition: capabilities

A module declares what it `provides` and what it `needs`. The installer is
a constraint solver:

- If a module needs `telegram.gateway` and only one installed module provides
  it → wire automatically.
- If two modules provide `telegram.gateway` with different bot tokens → fine.
- If two modules provide `telegram.gateway` with the **same** bot token →
  conflict; `spark install` refuses with a clear error.

Capability names are reverse-DNS namespaced
(`telegram.gateway`, `memory.store`, `chip.coding`) and listed in a public
schema doc.

## Status / healthcheck contract

Every module's `healthcheck.command` must:

- Exit 0 = healthy, non-zero = unhealthy.
- Print one line of human summary to stdout.
- Optionally print structured JSON to stderr for `spark status --json`.

Example output of `spark status`:

```
Spark v0.1.0 (3 modules installed)

✓ spark-intelligence  v0.4.0  telegram polling, 0 jobs, last seen 12s ago
✓ spawner-ui          v0.0.1  http://localhost:5173, claude-cli OAuth
✗ memory              v0.3.0  sqlite locked by another process — run `spark stop memory` then retry
```

Red lines always include a fix hint. No silent failures.

## Dashboard

A SvelteKit app served at `localhost:NNNN` by `spark dashboard`. Same code
that powers `spawner-ui`, with onboarding/admin views added. It calls into
the CLI via spawned subprocesses (e.g. `spark status --json`,
`spark install <name>`) — no separate API server. Process exits when the
user closes the tab or hits Ctrl-C.

The hosted web installer at `sparkswarm.ai/install` is the same dashboard
running locally in onboarding mode. The website only serves the install
script (`curl -fsSL sparkswarm.ai/install | sh`) and a static landing page —
no backend.

## What we deliberately defer

- **Auto-update / version pinning across modules.** v1 is "user runs
  `spark update foo`."
- **Background daemon.** v1 is foreground-only.
- **Cross-device sync.** v1 is single-machine.
- **Mobile app.** v1 is dashboard-via-web.
- **Hosted CDN for prebuilt artifacts.** v1 clones source.
- **Windows.** v1.1.
- **Plugin marketplace UI.** v1 is `spark install` from CLI; dashboard adds
  a "Browse" tab in v1.1.

## Licensing & Spark Pro

Spark is freemium. A single **Spark Pro** subscription unlocks all paid
modules. This section covers how the installer handles paid modules,
license verification, and graceful degradation. Strategic context lives
in a separate strategy document; this section covers the mechanics.

### Manifest `[license]` block

Every module declares its license tier in `spark.toml`:

```toml
[license]
tier = "pro"              # free | pro | community
provider = "spark"        # who issues the license check; "spark" for first-party
sku = "spark-pro"         # which subscription unlocks it
trial_days = 0            # optional free trial period
grace_period_days = 7     # offline grace before disabling on sub-check failure
```

- **`free`** — installs and runs without account.
- **`pro`** — requires active Spark Pro subscription on the user's
  Spark account.
- **`community`** — third-party module; no license check. (Module author
  may implement their own gating; not Spark's concern.)

Default if `[license]` block omitted: `tier = "free"`.

### Spark account model

A Spark account is a lightweight identity for license attribution.
Created at `sparkswarm.ai/signup`. Two pieces of metadata:

- Email (login + receipts)
- Subscription state (`free` | `pro` | `team` | `enterprise` | `none`)

Login from CLI: `spark login` opens a browser tab to
`sparkswarm.ai/login?cli=<one-time-code>`. User authenticates in browser,
clicks "authorize this CLI"; CLI receives a long-lived license token
(JWT, signed by Spark, includes user ID + sub state + expiry).

Token storage: OS keychain, key `spark.license_token`.

### Install flow when a Pro module is requested

```
1. Resolve module manifest, see tier = "pro"
2. Check local license token from keychain
   - Missing → prompt: "This is a Spark Pro module. Run `spark login` first."
   - Present and not expired → continue
   - Present but expired → attempt silent refresh; on failure prompt re-login
3. Send sub-check request to sparkswarm.ai/api/license/verify with token
   - Online + valid sub → continue install
   - Online + sub canceled/lapsed → show upgrade CTA, abort install
   - Offline + within grace_period_days → continue install with warning
   - Offline + past grace → abort with "reconnect to verify subscription"
4. Continue normal install lifecycle (clone, runtime install, hooks, healthcheck)
5. Cache verification timestamp in installed.json for future grace calculation
```

### Periodic re-verification for installed Pro modules

- On `spark start <pro-module>`, read cached verification timestamp.
- If older than 7 days, attempt online sub-check in background.
- If still within grace and offline, allow start with warning.
- If past grace and unable to verify, refuse to start with clear message
  pointing user to `spark login` or `sparkswarm.ai/billing`.

This means a paying user who's offline for a week is fine. A user who
canceled and went offline gets blocked after the grace period, not
immediately (avoid "I just canceled and now my agent is dead" UX).

### What happens when sub is canceled or lapses

Soft-disable, not uninstall:

- Pro modules remain installed and visible in `spark list`.
- They're marked `(Pro — subscription required)` in `spark status`.
- `spark start <pro-module>` shows: *"This module needs Spark Pro. Resubscribe at sparkswarm.ai/billing."*
- User keeps their data (`~/.spark/state/<module>/` is untouched).
- On resubscribe, modules just work again — no reinstall needed.

Never delete user data on sub lapse. Ever.

### Free trial mechanic

Modules can declare `trial_days = N` in `[license]`. On first install of
any Pro module, the user gets a trial activated against their account.
Trial is a single account-wide window (not per-module) — install all the
Pro you want during trial, no payment until it ends.

### Offline-first design principles

- License token is a signed JWT — verifiable offline by checking
  signature against Spark's public key (shipped with the CLI).
- Sub state in token has a `valid_until` field; CLI checks this locally
  without network round-trip.
- Network sub-check is for catching cancellations between token refreshes,
  not for blocking normal use.
- Grace period exists specifically so flaky network never blocks a paying
  user.

### Open-format-paid-corpus principle (technical statement)

- The `spark.toml` schema, the H70-C+ skill format spec, the registry
  format, and the CLI itself: **MIT-licensed, open source.**
- Spark Swarm is **AGPL-licensed.** Other Spark repos are **MIT** unless
  their `LICENSE` file says otherwise.
- The Spark-curated H70 skill corpus, the spark-blessed premium chips,
  the Spark Cloud / hosted dashboard infrastructure, private corpuses,
  brand assets, deployment secrets, and Pro drops: **proprietary,
  Spark Pro.** Pro drops do not grant redistribution rights unless a
  separate written license says so.
- A community module author can ship an H70 skill catalog of their own
  under any license they choose. They can charge for it themselves
  (their own license server in `[license.provider]`) or give it away
  for free.

This split is enforced by being clear about each repo's `LICENSE` file
and by keeping proprietary Spark Pro artifacts out of MIT/AGPL repos. Do
not mix them in the same repo. The blessed registry manifest itself is MIT
(`github.com/spark/registry`). The corpus content is in a separate
proprietary repo (`github.com/spark/corpus`) that the registry points at
via signed URLs requiring license tokens.

### Anti-piracy posture

- **None at the file level.** H70 skills are YAML; once on disk, they're
  on disk. Don't waste engineering effort on DRM.
- **License verification at install/start, not at every read.** Pirates
  exist; the value is in being the trusted, vetted, up-to-date source —
  pirated copies go stale within days as new skills land.
- **Pro drops grant access, not redistribution.** They are not covered by
  open-source repo licenses unless a separate written license says so.
- **Curated corpus updates ship through registry pulls,** so a pirated
  v1 corpus becomes obsolete the moment v2 ships.

This is the same posture as Tailwind UI, Sanity, dbt Cloud — sustainable
because the value is curation + freshness + support, not file secrecy.

## Open questions to resolve before implementation

1. **Implementation language for the CLI.** Go (single binary, easy
   distribution, mature for CLIs) or Rust (faster, better type system, but
   slower to build features)? Recommendation: **Go** for v1 — Spark needs to
   ship features fast and Go's distribution story is unmatched.

2. **Where does the registry live?** `github.com/spark/registry` (public Git
   repo) is my recommendation. Alternative: hosted JSON endpoint at
   `registry.sparkswarm.ai`. Git is cheaper to start and trivially auditable
   (every change is a PR).

3. **How do we name the org / brand the CLI?** Manifest is
   `spark.toml`, CLI is `spark`, registry is `github.com/spark/registry`. If
   the GitHub org `spark` is taken, we need a fallback (e.g.
   `github.com/spark-dev/registry`).

4. **Telemetry.** Opt-in install counts and crash reports help prioritize
   bugs. Off by default, prompt during `spark setup`. Recommendation:
   opt-in, anonymous, easy to inspect what's sent.

5. **Trust model for arbitrary git URLs.** `spark install github.com/X/Y`
   runs that repo's `post_install` hook. v1 should print the manifest's
   `[hooks]` block and require user confirmation before running anything
   from a non-blessed source.

## Next steps

1. Review and revise this doc.
2. Spike the CLI in Go — `spark install <git-url>` end to end with a real
   module manifest. Treat existing repos (`spark-intelligence-builder`,
   `spawner-ui`) as the first two test cases. Each repo needs a
   `spark.toml` added.
3. Stand up `github.com/spark/registry` with those two modules listed.
4. Build the wizard.
5. Build the dashboard view (start with `spark status` rendered as a web
   page; grow from there).