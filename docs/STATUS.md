# Spark CLI — Status Audit

**Last updated:** 2026-05-08 (Railway/VPS/sandbox hardening pass)
**Scope:** the `spark-cli` repo at `<workspace>\spark-cli`
**Source of truth:** `src/spark_cli/cli.py` (~12.9k LOC) + `src/spark_cli/sandbox/*` + `tests/test_cli.py` (~9.5k LOC)
**Test state:** 497 passed / 5 skipped on this machine after the remote sandbox hardening pass
**Working branch:** `codex/fix-railway-smoke-remote-failures-20260508`

---

## Release prep update (2026-05-08)

Spark CLI now has a production-prep hardening layer for hosted Spark Live,
Railway/VPS docs, SSH remote targets, Modal smoke checks, installer integrity,
and shareable diagnostics.

Shipped in this pass:

- `spark verify --installers --json` checks installer manifest metadata and
  local installer checksums.
- `spark verify --sandboxes --json` reports remote sandbox readiness without
  running cloud smoke jobs.
- SSH sandbox lane: `add`, `list`, `trust`, `doctor`, optional
  `doctor --remote-probe`, `smoke`, and `remove`.
- Modal sandbox lane: `doctor` and explicit no-secret `smoke`.
- Hosted Spark Live docs and verification cover Docker, Railway, and VPS
  deployment shapes.
- Remote sandbox outputs redact secret-like values, URL credentials, bearer
  tokens, PEM blocks, Telegram tokens, provider tokens, private key paths,
  local audit paths, and local diagnostic paths.
- Pro connection-token/bearer-token mentions are paused in docs until the
  downstream Spark Pro entitlement path exists.

Verified during this pass:

- `python -m pytest` -> 497 passed, 5 skipped
- `python -m spark_cli.cli verify --installers --json` -> OK
- `python -m spark_cli.cli verify --sandboxes --json` -> OK, with Modal auth
  correctly reported as optional when no local Modal auth marker exists
- `python -m spark_cli.cli support bundle --json` -> no raw local path leak
- `git diff --check` -> OK

Still intentionally deferred:

- SSH prepare/deploy, remote log tailing, and arbitrary remote shell.
- Modal arbitrary run, artifact pull, persistent volumes, and provider-secret
  passthrough.
- Public inbound hosted services beyond the reviewed Spark Live lane.
- Spark Pro connection tokens and bearer-token entitlement flow.

---

## Installer bootstrap update (2026-04-24)

Spark now has the first real one-shot installer layer:

- `scripts/install.sh`
- installs into a local prefix (`~/.spark` by default)
- downloads managed Node 22 into `~/.spark/tools/`
- creates an isolated Python virtualenv for `spark-cli`
- writes `~/.spark/bin/spark`
- runs `spark setup telegram-starter` by default
- supports local registry overrides for WSL/offline smoke tests

This brings Spark closer to the OpenClaw/Hermes installer pattern: a local
prefix, managed runtime tools, an explicit setup step, and a doctor/status
repair loop.

Verified in WSL sandbox:

- `spark setup` with a local registry override installed/registers the
  starter modules in a disposable `$HOME`
- generated per-module config files for all starter modules
- selected `spark-telegram-bot` as the only Telegram ingress owner

Verified again during the launch pass:

- `python -m pytest tests/test_cli.py -q` -> 98 passed
- Windows temp `SPARK_HOME` setup cloned/registers all starter modules
- WSL Ubuntu temp `SPARK_HOME` setup cloned/registers all starter modules
- default LLM provider wiring supports Z.AI GLM (`glm-5.1`) without writing raw keys to generated module env files
- dashboard/resonance API is deferred; starter installs should not require `SPARK_API_URL`, `SPARK_DASHBOARD_URL`, or a local service on port 8787

Still needs a future installer-hardening pass:

- full dependency-install smoke with install command logs per module
- bundle lock file with repo refs/SHAs
- installer checksum verification for downloaded Node tarballs
- first-class `spark doctor --fix-runtime` or equivalent repair mode

---

## Launch readiness snapshot (2026-04-23)

Fresh-machine install path is verified end to end.

| Check | Result |
|---|---|
| `spark-cli` repo public on GitHub | `vibeforge1111/spark-cli` (PRIVATE, MIT) |
| `pip install -e .` works from clone | yes |
| `python -m pytest tests/ -q` | 84 pass |
| Three starter modules have `spark.toml` on `origin/main` | yes: `spark-telegram-bot`, `vibeship-spawner-ui`, `spark-intelligence-builder` |
| `registry.json` points at git URLs | yes (commit `b05cb43`) |
| `discover_modules` + `ensure_bundle_modules_available` clones bundle members on first run | verified against all three starter repos |
| Keychain round-trip against Windows Credential Manager | verified |
| `spark init <name>` scaffolds a module that installs + passes healthcheck | verified |

### Reconciliation log for `spark-intelligence-builder`

The local `~/Desktop/spark-intelligence-builder` branch was 97 ahead / 7 behind
`origin/main` going into launch prep. Reconciled via themed squash-merged PRs:

| PR | Title | Commits | Sha on main |
|---|---|---|---|
| #14 | Define builder installer contract | 1 | `9933362` |
| #15 | Batch 2: Telegram memory lanes and stress tests | 39 | `d782937` |
| #16 | Batch 3: Runtime architecture, evidence observations, bootstrap | 13 | `48769b3` |
| #17 | Batch 5: Memory architecture, beliefs, Phase A + Phase B | 49 | `36b683c` |
| (none) | Batch 4 shadow-validation (6 commits) | dropped as patch-id-equivalent to origin's PR #13 | — |

One merge conflict across the sequence: Batch 3's `c60a845` vs Batch 1 on
`README.md` (both added a "Current Live Telegram Architecture" section).
Resolved by keeping the Batch 1 version; the rest of `c60a845`'s edits to
the README's ingress-ownership section applied cleanly.

**Local-history note.** `~/Desktop/spark-intelligence-builder` is now 108
ahead / 11 behind `origin/main` because the original 97 commits are still
in local history while origin has 4 new squash commits. The *content* is
fully reconciled. To finish the local reconciliation later, pick one:
- `git fetch && git reset --hard origin/main` (destroys local history)
- `git pull --rebase origin main` (empties dropped, possible conflicts)
- `git merge origin/main` (preserves divergent history with a merge commit)

Not a launch blocker.

---

This document is the ground-truth index of what the spike does, what it does
not, and where to look. Update it at the end of any session that changes the
surface area of the CLI.

---

## TL;DR

The repo ships the **full install lifecycle** for both registry-backed and
git-sourced modules, plus a **module scaffolder** (`spark init`), **user
config**, **registry search**, **OS-keychain secrets**, **interactive setup
wizard**, **dependency-aware start/stop**, **trust prompt for non-blessed
installs**, **`--resume`** on failed installs, **runtime version enforcement**,
**schema-version guard**, **hosted Spark Live verification**, **remote sandbox
doctor/smoke checks**, and **shareable redacted diagnostics**.

What it still does **not** do: a dashboard, license/Pro gating via
`spark login`, and a web installer. All three are explicit large-scope
items deferred pending architectural decisions about backend URLs,
signing keys, and hosted infra.

---

## CLI surface

```
spark list                            # discovered modules
spark init <name> [--kind] [--path]   # scaffold a new module
spark install <target> [--resume]     # registry name | bundle | path | git url
spark update [target]                 # re-run install commands; git pull for managed clones
spark uninstall [target] [--force]    # tear down + rotate secrets
spark setup <bundle> [--non-interactive]   # interactive preflight + prompts
spark start [target]                  # topological launch with ready-check
spark stop  [target]                  # reverse-topological kill
spark status [--json]                 # healthchecks + repair hints
spark doctor [--json]                 # diagnostic variant of status
spark verify [--installers|--sandboxes|--hosted] [--json]
spark sandbox ssh <add|list|trust|doctor|smoke|remove>
spark sandbox modal <doctor|smoke>
spark live <status|start|run|restart|stop|logs|verify>
spark logs <module> [-n N] [-f]       # tail process logs
spark search [query]                  # registry browse + installed badge
spark secrets list|set|get|delete     # keychain-backed secret store
spark config get|set|unset|list       # user-level config at ~/.spark/config/config.json
```

Global install-time flags on `install` and `setup`:
- `--skip-install-commands` — skip `[install.dev].commands`
- `--skip-runtime-check` — skip `[runtime].version` enforcement
- `--trust` — approve non-blessed install without prompt
- `--resume` — skip steps recorded complete on a prior attempt
- `--non-interactive` (`setup` only) — require secrets via flags, skip preflight prompts

---

## Shipped feature matrix

The original April launch matrix is kept as historical feature inventory. New
May remote-sandbox and hosted-live surfaces are covered in the release-prep
update above and in the dedicated sandbox docs.

### Install lifecycle

| Feature | Code | Test |
|---|---|---|
| Manifest parsing into a `Module` dataclass | `cli.py` | via fixtures |
| Local `registry.json` with modules + bundles | `load_registry_definition` | `test_resolve_bundle_names_reads_registry_bundle` |
| `list` | `cmd_list` | — |
| `install <module>` (registry name, path, git URL) | `cmd_install`, `resolve_install_target` | `test_resolve_install_target_*` |
| `install <bundle>` with ingress-owner enforcement | `cmd_install`, `detect_ingress_owner` | `test_detect_ingress_owner_*` |
| Capability conflict guard | `detect_capability_conflicts` | `test_detect_capability_conflicts_*` |
| `needs.capabilities` resolver | `validate_capability_needs_for_install` | `test_validate_capability_needs_*` |
| `[install.dev].commands` execution | `execute_install_commands` | `test_execute_install_commands_*` |
| Install provenance in `installed.json` | `install_module_record` | `test_install_module_record_writes_provenance_metadata` |
| Trust prompt for non-blessed modules | `ensure_trust_for_install`, `describe_install_risk`, `is_blessed_registry_entry` | `test_ensure_trust_for_install_*`, `test_describe_install_risk_*` |
| `--resume` with per-target progress file | `run_install_commands_with_progress`, `record_install_step`, `clear_install_progress` | `test_install_progress_*`, `test_run_install_commands_with_progress_*` |
| Runtime version constraint enforcement | `enforce_runtime_versions`, `check_runtime_version_for_module`, `runtime_version_satisfies` | `test_check_runtime_version_*`, `test_runtime_version_satisfies_*` |
| Manifest schema version guard (`schema = 1`) | `validate_manifest_schema`, `manifest_schema_version` | `test_validate_manifest_schema_*` |

### Setup wizard

| Feature | Code | Test |
|---|---|---|
| Bundle resolution + single-ingress enforcement | `resolve_bundle`, `detect_ingress_owner` | — |
| Interactive TTY prompts via `getpass` | `run_setup_wizard`, `prompt_for_secret` | `test_run_setup_wizard_*` |
| Preflight: Claude Code + runtime binaries + per-module constraints | `print_setup_preflight`, `detect_claude_code`, `detect_runtime_binary` | `test_detect_runtime_binary_*` |
| `--non-interactive` mode | `setup_is_interactive` | `test_setup_is_interactive_*` |
| Manifest-driven secret collection with dedup | `collect_secret_requirements`, `collect_secret_values` | `test_collect_secret_*` |
| Generated module env files | `write_generated_env`, `update_env_file` | `test_update_env_file_*` |

### Secrets

| Feature | Code | Test |
|---|---|---|
| OS keychain via `python-keyring` (Windows Credential Manager probed green) | `keychain_available`, `store_secret`, `fetch_secret`, `delete_secret` | `test_store_and_fetch_secret_*` |
| File fallback at `~/.spark/config/secrets.local.json` (mode 0o600) | same | same |
| Manifest `storage = "keychain"` routes into keychain at setup | `persist_keychain_secrets`, `split_secret_bindings` | `test_persist_keychain_secrets_*` |
| Keychain env vars stripped from plaintext envs | `strip_keychain_env_vars` | `test_strip_keychain_env_vars_*` |
| Keychain injected into subprocess env at start | `keychain_env_for_module`, `start_module` | `test_keychain_env_for_module_*` |
| `spark secrets list|set|get|delete` | `cmd_secrets_*` | — (smoke-tested against real Credential Manager) |

### Start / stop / logs

| Feature | Code | Test |
|---|---|---|
| `start [target]` topological from `needs.modules` | `resolve_start_modules`, `topologically_sort_modules` | `test_resolve_start_modules_*` |
| Stale-pid detection + re-launch | `pid_is_running`, `start_module` | `test_pid_is_running_*` |
| Ready-check polling (HTTP + shell) | `wait_for_ready_check` | `test_wait_for_ready_check_*` |
| `stop [target]` reverse-topological | `resolve_stop_module_names` | `test_resolve_stop_module_names_*` |
| Windows-safe process groups | `start_module`, `stop_module` | — |
| `logs <module> [-n N] [-f]` | `cmd_logs`, `tail_log_lines`, `follow_log_file` | `test_tail_log_lines_*` |

### Status / doctor

| Feature | Code | Test |
|---|---|---|
| `status` + `--json` | `collect_status_payload`, `cmd_status` | `test_build_module_repair_hints_*` |
| `doctor` + `--json` | `cmd_doctor` | — |
| Dep-aware repair hints | `build_module_repair_hints`, `build_status_repair_hints` | `test_build_status_repair_hints_*` |
| Healthcheck `failure_hint` / `success_hint` | `evaluate_module_health` | — |

### Git fetch

| Feature | Code | Test |
|---|---|---|
| URL shape detection + shorthand normalization | `is_git_source`, `normalize_git_url`, `infer_module_name_from_url` | `test_is_git_source_*`, `test_normalize_git_url_*` |
| `git clone --depth=1` into `~/.spark/modules/<name>/source/` | `clone_module_source` | integration test with local bare repo |
| `git pull --ff-only` in `update` | `pull_module_source` | covered in clone test |
| Spark-managed path detection | `module_is_git_managed` | `test_module_is_git_managed_*` |

### Update / uninstall

| Feature | Code | Test |
|---|---|---|
| `update [target]` re-runs install commands + `post_install` hook | `cmd_update` | — |
| `git pull --ff-only` for managed clones | `pull_module_source` | covered by clone integration test |
| Env resync into module `.env` | `sync_generated_env_to_module` | — |
| `uninstall` with dep protection + `--force` | `cmd_uninstall`, `detect_uninstall_blockers` | `test_detect_uninstall_blockers_*` |
| Clone-dir teardown on uninstall | `remove_module_clone` | — |
| Setup-state repair after uninstall | `update_setup_state_after_uninstall` | `test_update_setup_state_after_uninstall_*` |

### Scaffolder and discovery

| Feature | Code | Test |
|---|---|---|
| `spark init <name> [--kind python|node]` | `cmd_init`, `scaffold_module_files`, `render_init_spark_toml`, `validate_init_module_name` | `test_validate_init_module_name_*`, `test_render_init_spark_toml_*`, `test_scaffold_module_files_*` |
| `spark search [query]` with blessed/installed badges | `cmd_search` | — |
| `spark config get|set|unset|list` with dotted keys + JSON coercion | `cmd_config_*`, `dotted_get`, `dotted_set`, `dotted_unset`, `coerce_config_value` | `test_dotted_*`, `test_coerce_config_value_*` |

---

## Not yet implemented

All remaining items are large-scope and need product / architecture
decisions before coding. Deliberately deferred.

- **`spark dashboard`** — SvelteKit foreground app shelling out to
  `spark <cmd> --json`. Needs: subproject layout, port allocation,
  which commands to surface first. One full session minimum.
- **`spark login` + Pro gating** — JWT, signing key, offline grace,
  sub-check endpoint, billing webhook. Needs: hosted license server
  URL, keypair, subscription model. Blocks every Pro-tier module.
- **Web installer at `sparkswarm.ai/install`** — landing page +
  one-shot install script. Needs: domain, landing copy, the install
  script itself (Homebrew tap? curl-to-bash script?).
- **Telemetry opt-in** — intentionally skipped for now per direction.

See [design/spark-installer-design-v1.md](./design/spark-installer-design-v1.md)
for the intended shape of each.

---

## Unsure — verify before acting

1. ~~`spawner-ui`'s `npm run health:spark` — declared in its manifest~~ → **verified 2026-04-22**: `spawner-ui/package.json:9` → `node scripts/health-spark.mjs`.
2. ~~`python -m spark_intelligence.cli doctor` — builder healthcheck~~ → **verified 2026-04-22**: runs end-to-end, reports `degraded` due to known `watchtower-freshness` gap (per user memory); all other subchecks green.
3. **PATH collision** — if another `spark` is on PATH, `pip install -e .` will not overwrite it. `spark-local` is the safe alias.
4. **Legacy `~/.spark/state/installed.json`** — written under an older provenance schema before commit `bb850aa`. Any `install` upgrades the record in place; not broken, just pre-dated.

---

## File layout

```
spark-cli/
├── pyproject.toml                 # deps=[keyring>=24.0], scripts=spark + spark-local
├── registry.json                  # modules and bundles
├── README.md                      # command reference
├── docs/
│   ├── STATUS.md                  # this file
│   └── design/
│       ├── spark-installer-design-v1.md
│       ├── lessons-from-todays-install.md
│       └── user-flows-and-diagrams.md
├── src/spark_cli/
│   ├── __init__.py
│   └── cli.py                     # 2397 LOC; everything in one module
└── tests/
    └── test_cli.py                # 1250 LOC, 83 tests, unittest + mock
```

`~/.spark/` tree managed by the CLI:

```
~/.spark/
├── state/
│   ├── installed.json             # installed modules + provenance
│   ├── setup.json                 # configured bundle + ingress owner
│   ├── pids.json                  # running process pids
│   └── install_progress.json      # checkpoint for --resume
├── config/
│   ├── config.json                # user-level config via `spark config`
│   ├── modules/<name>.env         # generated per-module env files (non-secret)
│   ├── secrets_index.json         # which backend holds each secret
│   └── secrets.local.json         # only when keychain is unavailable
├── modules/<name>/source/         # clone target for git-sourced modules
└── logs/<name>/process.log        # process logs from `spark start`
```

---

## Quick operator reference

```bash
# Fresh onboarding
python -m spark_cli.cli setup telegram-starter     # interactive preflight + prompts
python -m spark_cli.cli setup telegram-starter --non-interactive \
    --secret telegram.bot_token=... --secret telegram.admin_ids=...

# Registry + scaffolder
python -m spark_cli.cli search [query]
python -m spark_cli.cli init my-module --kind python

# Install lifecycle
python -m spark_cli.cli install <name|bundle|path|git-url> [--resume]
python -m spark_cli.cli update [target]
python -m spark_cli.cli uninstall [target] [--force]

# Run
python -m spark_cli.cli start [target]
python -m spark_cli.cli stop  [target]
python -m spark_cli.cli status [--json]
python -m spark_cli.cli doctor [--json]
python -m spark_cli.cli logs <module> [-n 200] [-f]

# Config + secrets
python -m spark_cli.cli config set dashboard.port 8765
python -m spark_cli.cli secrets list
python -m spark_cli.cli secrets set telegram.bot_token

# Release and remote sandbox checks
python -m spark_cli.cli verify --installers --json
python -m spark_cli.cli verify --sandboxes --json
python -m spark_cli.cli sandbox ssh doctor <name> --remote-probe --json
python -m spark_cli.cli sandbox ssh smoke <name> --json
python -m spark_cli.cli sandbox modal doctor --json
python -m spark_cli.cli sandbox modal smoke --json
```
