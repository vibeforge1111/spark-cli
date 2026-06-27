# Spark R30 Installer Preparation Checklist

Date: 2026-06-27
Status: installer preparation checklist, not a publication record

## Current Installer State

- Local `scripts/installer-manifest.json` points at `spark-cli-public-installer-2026-06-22-r28`.
- Local `scripts/install.sh` and `scripts/install.ps1` also pin R28.
- Hosted `agent.sparkswarm.ai` currently reports self-consistent `spark-cli-public-installer-2026-06-26-r29`.
- R30 must not be claimed until the local source release, installer manifest, hosted installer bytes, hosted checksums, `/install/commands.json`, and `/install/release-manifest.json` all agree.

## Pre-Manifest Work

Complete these before changing `scripts/installer-manifest.json` or installer script pins:

1. Land or port source-owner commits for the runtime changes R30 is claiming.
2. Decide whether `spark-voice-comms` should pin a release tag or a newer proven remote head.
3. Update `registry.json` only after owner-source commits exist remotely.
4. Run:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --json
PYTHONPATH=src python3 -m spark_cli.cli verify --registry-pins --json
PYTHONPATH=src python3 -m spark_cli.cli verify --provenance --json
spark os compile --json
```

Expected before manifest edit:

- `publication_order` passes because installer pins have not been advanced while source/registry truth is still red
- R30 release gate blocks only on installer pins awaiting the authorized R30 manifest batch
- registry pins pass
- provenance passes
- Spark OS compile reports `ok=true`, `gaps=0`, `dirty_repo_count=0`, `blocked_release_count=0`
- `critical_duplicate_truth_count=0`

## Manifest And Script Update

Only after pre-manifest work is green:

1. Create the source release tag or release commit for `spark-cli`.
2. Update all release pins together:
   - `scripts/installer-manifest.json`
   - `scripts/install.sh`
   - `scripts/install.ps1`
3. Recompute installer hashes and write them into `scripts/installer-manifest.json`.
4. Run:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json
PYTHONPATH=src python3 -m pytest tests/test_cli.py -q
git diff --check
```

Do not publish hosted installer files until the local installer gate passes.

## Hosted Publication Gate

After deploying R30 to `agent.sparkswarm.ai`, run:

```bash
PYTHONPATH=src python3 -m spark_cli.cli verify --r30 --hosted-installers --json
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --hosted-installers --json
```

The gate must prove:

- hosted `install.sh` hash matches hosted checksum metadata
- hosted `install.ps1` hash matches hosted checksum metadata
- hosted script release pins match R30
- `/install/commands.json` references R30 and the same hashes
- `/install/release-manifest.json` references R30 and the same source ref

## Fresh Install Smoke

Use an isolated Spark home for every smoke:

```bash
export SPARK_HOME="$(mktemp -d /tmp/spark-r30-smoke-XXXXXX)"
```

### Unattended Identity-Mutation Guard

The installer and CLI must fail closed when a non-interactive run tries to pass
Telegram identity or operator access flags. This is expected and should happen
before any runtime config or secret files are written:

```bash
spark setup --non-interactive \
  --bot-token "fake-token" \
  --admin-telegram-ids "12345" \
  --llm-provider codex \
  --skip-telegram-token-check \
  --no-autostart \
  --no-start-now \
  --skip-runtime-check ; echo "exit=$?"
```

Expected result:

- exit code `2`
- output says Spark blocked a sensitive `identity_access_mutation`
- `$SPARK_HOME` remains empty or contains no generated module env/state files

Then scan any generated state for accidental secrets:

```bash
grep -R "fake-token\\|BEGIN .*PRIVATE KEY\\|SPARK_API_URL\\|SPARK_DASHBOARD_URL" \
  "$SPARK_HOME/config" "$SPARK_HOME/state" "$SPARK_HOME/logs" 2>/dev/null || true
```

The fake token must not appear in generated module env files. The old dashboard and port `8787` path must not reappear.

### Interactive Identity Setup Smoke

After R30 source, registry, and installer truth are green, run the identity setup
path in an interactive terminal so Spark can request the approval phrase:

```bash
spark setup telegram-starter \
  --bot-token "@env:SPARK_TEST_TELEGRAM_BOT_TOKEN" \
  --admin-telegram-ids "@env:SPARK_TEST_TELEGRAM_ADMIN_IDS" \
  --llm-provider codex \
  --skip-telegram-token-check \
  --no-autostart \
  --no-start-now \
  --skip-install-commands \
  --skip-runtime-check
spark status --json
```

Only use a real disposable test bot for this lane. Do not use the fake token
lane to claim runtime setup success.

## Upgrade Smoke

After hosted R30 is published, upgrade a disposable R29 install to R30 and verify:

```bash
spark setup --resume
spark status --json
spark verify --deep
spark providers status
spark live status --json
```

If Telegram is intentionally tested live, use the release-gate visual/live confirmation path before calling R30 ready.

## Publication Rule

R30 publication is blocked until local verification, hosted verification, registry truth, and installed runtime truth all agree. If one surface is ahead of another, document the handoff instead of changing release claims.
