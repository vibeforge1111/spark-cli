# Spark launch runbook

This is the launch path for a fresh Spark install. It should leave the user with
the core ecosystem installed, configured, and ready to answer through Telegram
without requiring the deferred dashboard or resonance API.

## Launch scope

`spark setup` defaults to the `telegram-starter` bundle:

1. `spark-researcher`
2. `spark-intelligence-builder`
3. `domain-chip-memory`
4. `spawner-ui`
5. `spark-telegram-bot`

Spawner UI is included as the local execution plane and mission surface. The old
dashboard/resonance API is not part of launch. A starter install should not need
`SPARK_API_URL`, `SPARK_DASHBOARD_URL`, or anything on port `8787`.

## Fresh install

Windows PowerShell:

```powershell
iwr https://raw.githubusercontent.com/vibeforge1111/spark-cli/master/scripts/install.ps1 -OutFile .\install.ps1
Get-Content .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

macOS, Linux, or WSL. The shell installer auto-detects Apple Silicon, Intel Mac, Linux x64, Linux arm64, and WSL before downloading managed Node:

```bash
curl -fsSLO https://raw.githubusercontent.com/vibeforge1111/spark-cli/master/scripts/install.sh
less install.sh
bash ./install.sh
```

Both installers install the CLI, run the default starter setup, and write Spark
state under `~/.spark` unless `SPARK_HOME` is set.

## Non-interactive setup

Use a BotFather token and at least one Telegram admin id. Keep secrets in
environment variables or a shell prompt; do not paste them into files that may be
committed.

```bash
spark setup --non-interactive \
  --bot-token "$TELEGRAM_BOT_TOKEN" \
  --admin-telegram-ids "$TELEGRAM_ADMIN_IDS" \
  --llm-provider zai \
  --zai-api-key "$ZAI_API_KEY"
```

Z.AI launch defaults:

- endpoint: `https://api.z.ai/api/coding/paas/v4/`
- model: `glm-5.1`

OpenAI launch default:

- model: `gpt-5.5`

The installer stores cloud keys through the Spark secret backend. Generated
module env files should contain secret references and non-secret metadata, not
raw LLM API keys.

## First verification

Run:

```bash
spark status --json
spark secrets list
```

Expected setup state:

- bundle is `telegram-starter`
- all five starter modules are installed
- `telegram.ingress` is owned by `spark-telegram-bot`
- Telegram launch mode is long polling; no Telegram webhook env is generated
- Telegram and Spawner share a generated relay secret
- LLM provider is configured when a provider key was supplied
- repair hints do not mention dashboard URLs or port `8787`

Start or restart the bot after setup:

```bash
spark start spark-telegram-bot
```

Then verify in Telegram:

- `/start` returns the launch command surface
- `/status` reports the launch core online
- a normal message receives an LLM-backed response
- `/diagnose` reports Telegram, LLM, memory, and mission relay state

## Sandbox smoke

Before launch, run at least one clean install with an isolated `SPARK_HOME`.

Windows PowerShell:

```powershell
$env:SPARK_HOME = Join-Path $env:TEMP "spark-launch-smoke"
spark setup --non-interactive `
  --bot-token "fake-token" `
  --admin-telegram-ids "12345" `
  --llm-provider zai `
  --zai-api-key "fake-zai-key" `
  --skip-install-commands `
  --skip-runtime-check
spark status --json
```

Linux or WSL:

```bash
export SPARK_HOME="$(mktemp -d /tmp/spark-launch-smoke-XXXXXX)"
spark setup --non-interactive \
  --bot-token "fake-token" \
  --admin-telegram-ids "12345" \
  --llm-provider zai \
  --zai-api-key "fake-zai-key" \
  --skip-install-commands \
  --skip-runtime-check
spark status --json
```

After the smoke, scan generated env files and source checkouts for accidental
secrets or deferred dashboard configuration:

```bash
grep -R "fake-zai-key\|SPARK_API_URL\|SPARK_DASHBOARD_URL\|8787" "$SPARK_HOME" || true
```

The fake LLM key must not appear in generated module env files. Non-secret Z.AI
metadata such as provider, base URL, and model is expected.

## Troubleshooting

If the bot does not respond:

1. Confirm only one polling process owns the Telegram token.
2. Run `spark status --json` and check repair hints.
3. Check `spark logs spark-telegram-bot`.
4. Confirm `telegram.bot_token` and the selected LLM API key exist in
   `spark secrets list`.
5. Send `/diagnose` after the bot is running.

If Spawner UI cannot connect to an MCP bridge, that is expected unless
`PUBLIC_MCP_URL` or `PUBLIC_PRODUCTION_MCP_URL` is explicitly configured.
Launch should degrade gracefully without trying `localhost:8787`.

## Current launch residuals

- Spawner UI has two remaining moderate npm audit findings through `svelvet` and
  `uuid`. The available automated fix changes the `svelvet` major line and needs
  a separate UI regression pass, so it is not treated as a launch-blocking
  installer issue.
- Existing Svelte check warnings are present in Spawner UI, but `npm run check`
  and `npm run build` pass.
