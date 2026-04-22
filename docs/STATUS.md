# Spark CLI — Status Audit

**Last updated:** 2026-04-22 (end of day)
**Scope:** the `spark-cli` spike at `C:\Users\USER\Desktop\spark-cli`
**Source of truth:** `src/spark_cli/cli.py` (1826 LOC) + `tests/test_cli.py` (922 LOC)
**Test state:** 56/56 passing on this machine
**Branch:** `master` at commit `f779d47`

This document is the ground-truth index of what the spike does, what it does
not, and where to look. Update it at the end of any session that changes the
surface area of the CLI.

---

## TL;DR

The spike covers the **full install → setup → start → status → stop →
uninstall lifecycle** for modules declared in a local `registry.json`,
with git-based fetch, keychain-backed secrets, an interactive setup
wizard, dependency-aware start/stop ordering, repair hints, and a
capability resolver.

What it still does **not** do: runtime version enforcement, manifest
schema versioning, license/Pro gating, `spark login`, a dashboard or
web installer, module scaffolding (`spark init`), and `--resume` on
failed installs. None of those are blockers for "a fresh user gets to
`spark setup telegram-starter` working end-to-end."

---

## Shipped feature matrix

Tracked across 15 commits on `master`. Every entry is covered by tests
unless noted.

### Install lifecycle

| Feature | Code | Test |
|---|---|---|
| Manifest parsing into a `Module` dataclass | `cli.py:30-123` | via fixtures |
| Local `registry.json` with modules + bundles | `cli.py:126-218` | `test_resolve_bundle_names_reads_registry_bundle` |
| `list` | `cmd_list` | — |
| `install <module>` (registry name or local path) | `cmd_install` | `test_resolve_install_target_*` |
| `install <bundle>` with ingress-owner enforcement | `cmd_install` | `test_detect_ingress_owner_*` |
| `install <git-url>` / `install <registry-name>` with git source | `clone_module_source`, `resolve_install_target` | `test_clone_module_source_clones_and_pull_updates_from_local_bare_repo` |
| Capability conflict guard (multiple `telegram.ingress` owners) | `detect_capability_conflicts` | `test_detect_capability_conflicts_*` |
| Capability needs resolver (`needs.capabilities`) | `validate_capability_needs_for_install` | `test_validate_capability_needs_*` |
| `[install.dev].commands` execution with failure surfacing | `execute_install_commands` | `test_execute_install_commands_*` |
| `post_install` / `pre_uninstall` / `post_uninstall` hooks | `run_module_hook` | — |
| Install provenance (`installed_via`, `bundle_provenance`, `last_install`, `last_update`) | `install_module_record` | `test_install_module_record_writes_provenance_metadata` |

### Setup

| Feature | Code | Test |
|---|---|---|
| Bundle resolution + single-ingress enforcement | `resolve_bundle`, `detect_ingress_owner` | — |
| Manifest-driven secret collection | `collect_secret_requirements`, `collect_secret_values` | `test_collect_secret_*` |
| Interactive setup wizard (TTY prompts via `getpass`) | `run_setup_wizard` | `test_run_setup_wizard_*` |
| Preflight runtime detection (`claude`, `uv`, `bun`, `node`, `python`) | `detect_runtime_binary`, `print_setup_preflight` | `test_detect_runtime_binary_*`, `test_required_runtimes_for_modules_*` |
| `--non-interactive` mode | `setup_is_interactive` | `test_setup_is_interactive_*` |
| `--secret key=value` plus legacy `--bot-token` etc. | `parse_secret_pairs`, `collect_secret_values` | `test_collect_secret_values_*` |
| Generated module env files in `~/.spark/config/modules/` | `write_generated_env` | — |
| Idempotent `# --- spark-cli managed start/end ---` block in module `.env` | `update_env_file`, `remove_managed_env_block` | `test_update_env_file_*`, `test_remove_managed_env_block_*` |
| Ingress-only telegram secret routing | `build_module_envs` | `test_build_module_envs_routes_telegram_secret_only_to_gateway` |

### Secrets

| Feature | Code | Test |
|---|---|---|
| OS keychain backend via `python-keyring` with probe | `keychain_available`, `store_secret`, `fetch_secret`, `delete_secret` | `test_store_and_fetch_secret_roundtrip_via_file_backend` |
| File fallback at `~/.spark/config/secrets.local.json` (mode 0o600) | same | same |
| Manifest `storage = "keychain"` routes to keychain at setup time | `persist_keychain_secrets`, `split_secret_bindings` | `test_persist_keychain_secrets_*` |
| Keychain env vars stripped from plaintext env files | `strip_keychain_env_vars` | `test_strip_keychain_env_vars_*` |
| Keychain secrets injected into subprocess env at start time | `keychain_env_for_module`, `start_module` | `test_keychain_env_for_module_*` |
| `spark secrets list / set / get / delete` (masking, `--reveal`) | `cmd_secrets_*` | — (smoke-tested end-to-end against real Credential Manager) |

### Status and doctor

| Feature | Code | Test |
|---|---|---|
| `status` + `status --json` with per-module healthcheck | `collect_status_payload`, `cmd_status` | `test_build_module_repair_hints_*` |
| `doctor` + `doctor --json` | `cmd_doctor` | — |
| Dep-aware repair hints (missing deps, unhealthy deps, missing ingress owner, stale bundle) | `build_module_repair_hints`, `build_status_repair_hints` | `test_build_status_repair_hints_*` |
| Healthcheck `failure_hint` / `success_hint` surfacing | `evaluate_module_health` | — |
| npm `> cmd` prefix stripping in healthcheck output | `summarize_command_output` | `test_summarize_command_output_*` |

### Update and uninstall

| Feature | Code | Test |
|---|---|---|
| `update [target]` re-runs install commands and `post_install` hook | `cmd_update` | — |
| `git pull --ff-only` for git-managed modules | `pull_module_source`, `module_is_git_managed` | `test_clone_module_source_*` (covers pull) |
| Env resync into module `.env` | `sync_generated_env_to_module` | — |
| `uninstall [target]` with dep protection and `--force` | `cmd_uninstall`, `detect_uninstall_blockers` | `test_detect_uninstall_blockers_*` |
| Clone dir teardown on uninstall | `remove_module_clone` | — |
| Setup-state repair after uninstall | `update_setup_state_after_uninstall` | `test_update_setup_state_after_uninstall_*` |

### Start / stop / logs

| Feature | Code | Test |
|---|---|---|
| `start [target]` in topological order from `needs.modules` | `resolve_start_modules`, `topologically_sort_modules` | `test_resolve_start_modules_*` |
| Pid tracking in `~/.spark/state/pids.json` | `load_pids`, `save_pids` | — |
| Stale pid detection; re-launch when dead | `pid_is_running`, `start_module` | `test_pid_is_running_*` |
| Ready-check polling (HTTP + shell) | `wait_for_ready_check` | `test_wait_for_ready_check_*` |
| `stop [target]` in reverse-topological order | `resolve_stop_module_names` | `test_resolve_stop_module_names_*` |
| Windows-safe process groups (`DETACHED_PROCESS`, `taskkill /T /F`) | `start_module`, `stop_module` | — |
| `logs <module> [-n N] [-f]` with tail + follow | `cmd_logs`, `tail_log_lines`, `follow_log_file` | `test_tail_log_lines_*`, `test_module_log_path_*` |

### Git fetch

| Feature | Code | Test |
|---|---|---|
| URL shape detection (`https://`, `git@`, `github.com/...`, `.git`) | `is_git_source` | `test_is_git_source_*` |
| URL normalization (github shorthand → https) | `normalize_git_url` | `test_normalize_git_url_*` |
| Name inference from URL | `infer_module_name_from_url` | `test_infer_module_name_from_url_*` |
| Clone into `~/.spark/modules/<name>/source/` | `clone_module_source` | integration test with local bare repo |
| Prefer cloned copy over registry path during discovery | `discover_modules` | — |
| Detect spark-managed module paths | `module_is_git_managed` | `test_module_is_git_managed_*` |

---

## Not yet implemented

Rough order of value-per-lift. None are blockers for the
`spark setup telegram-starter` first-run story.

### Small lift

- **`spark config get/set`** — user-level config at `~/.spark/config.toml`.
- **Manifest schema version** (`schema = 1`) — one-field forward-compat hook.
- **Runtime version range** from `[runtime].version` (`>=3.11`, `>=22`) — semver check before `[install.dev]` runs.

### Medium lift

- **Trust prompt for non-blessed git URLs** — print the manifest's `[hooks]` block and require confirmation before running.
- **`--resume` on failed installs** — each install step is already idempotent; needs a resume cursor in `installed.json`.
- **Telemetry opt-in prompt** during `spark setup`.
- **`spark search`** over the blessed registry.

### Larger scope

- **`spark init <name>`** — module scaffolder.
- **`spark dashboard`** — SvelteKit foreground app shelling out to `spark <cmd> --json`.
- **`spark login` + license/Pro gating** — JWT, offline grace, sub-check at install/start.
- **Web installer at `sparkswarm.ai/install`** — same dashboard in onboarding mode.
- **Full `needs.capabilities` wizard path** — today the resolver reports unmet needs; an interactive flow would offer to install a suggested provider in place.

---

## Unsure — verify before acting

1. **`spawner-ui` `npm run health:spark`** — declared in its manifest; has never been confirmed to exist in its `package.json`. If the script is missing, `spark status` will always show red for spawner-ui.
2. **`python -m spark_intelligence.cli doctor`** — the builder's declared healthcheck. Run it once to confirm the entry point still exists.
3. **PATH collision** — if another tool named `spark` is already on PATH, `pip install -e .` will not overwrite it. `spark-local` is the safe alias.
4. **Existing `~/.spark/state/installed.json`** — was written under the older provenance schema. Any `install` will upgrade the record in place; not broken, just means current on-disk shape predates commit `bb850aa`.

---

## File layout

```
spark-cli/
├── pyproject.toml                 # name=spark-cli, deps=[keyring>=24.0], scripts=spark + spark-local
├── registry.json                  # modules and bundles (local paths today)
├── README.md                      # command reference
├── docs/
│   ├── STATUS.md                  # this file
│   └── design/
│       ├── spark-installer-design-v1.md
│       ├── lessons-from-todays-install.md
│       └── user-flows-and-diagrams.md
├── src/spark_cli/
│   ├── __init__.py
│   └── cli.py                     # everything: primitives + commands + argparse
└── tests/
    └── test_cli.py                # 56 tests; unittest + mock
```

`~/.spark/` layout created and managed by the CLI:

```
~/.spark/
├── state/
│   ├── installed.json             # installed modules + provenance
│   ├── setup.json                 # configured bundle + ingress owner
│   └── pids.json                  # running process pids
├── config/
│   ├── modules/<name>.env         # generated module env files (non-secret)
│   ├── secrets_index.json         # which backend holds each secret
│   └── secrets.local.json         # only when keychain is unavailable
├── modules/<name>/source/         # clone target for git-sourced modules
└── logs/<name>/process.log        # process logs from `spark start`
```

---

## Quick operator reference

```bash
# First-time setup
python -m spark_cli.cli setup telegram-starter       # interactive preflight + prompts
python -m spark_cli.cli setup telegram-starter --non-interactive --secret telegram.bot_token=... --secret telegram.admin_ids=...

# Lifecycle
python -m spark_cli.cli list
python -m spark_cli.cli install <module|bundle|path|git-url>
python -m spark_cli.cli update [target]
python -m spark_cli.cli uninstall [target] [--force]

# Operation
python -m spark_cli.cli start [target]
python -m spark_cli.cli stop  [target]
python -m spark_cli.cli status [--json]
python -m spark_cli.cli doctor [--json]
python -m spark_cli.cli logs <module> [-n 200] [-f]

# Secrets
python -m spark_cli.cli secrets list
python -m spark_cli.cli secrets set <secret_id> [--value ...] [--backend keychain|file]
python -m spark_cli.cli secrets get <secret_id> [--reveal]
python -m spark_cli.cli secrets delete <secret_id>
```
