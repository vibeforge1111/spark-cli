# Spark Normie Onboarding and Gateway Test

Last updated: 2026-04-24

This is the launch-facing contract for a fresh Spark install. The user should not install Spark repos one by one. They should install Spark CLI, run setup once, paste a Telegram bot token and one LLM provider key, then have the starter ecosystem wired together.

## What The Default Install Brings

`spark setup` defaults to the `telegram-starter` bundle:

1. `spark-researcher`
2. `spark-character`
3. `spark-intelligence-builder`
4. `domain-chip-memory`
5. `spawner-ui`
6. `spark-telegram-bot`

The CLI clones or discovers these modules, validates each `spark.toml`, checks capability conflicts, installs in dependency order, records the bundle, writes module env, stores declared secrets, and generates the local relay secret shared by Telegram and Spawner.

## Official Reference Decisions

- Telegram launch v1 uses long polling. Telegram's Bot API says `getUpdates` is the long polling path and that `getUpdates` cannot receive updates while an outgoing webhook is set. It also provides `deleteWebhook` for switching back to `getUpdates`: https://core.telegram.org/bots/api
- Spark therefore starts the bot in polling mode, refuses webhook env, and deletes any active Telegram webhook before polling.
- OpenHands and Aider both make LLM provider setup a first-run concern: provider, model, and API key must be explicit enough that the agent can talk to a model immediately. Spark mirrors that with `--llm-provider` plus provider key/model/base-url flags.

## Fresh Install Path

### Windows PowerShell

```powershell
iwr https://raw.githubusercontent.com/vibeforge1111/spark-cli/master/scripts/install.ps1 -OutFile .\install.ps1
Get-Content .\install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 `
  -BotToken "<BOTFATHER_TOKEN>" `
  -AdminTelegramIds "<YOUR_TELEGRAM_NUMERIC_ID>" `
  -LlmProvider zai `
  -ZaiApiKey "<ZAI_API_KEY>"
```

### macOS, Linux, WSL

The shell installer auto-detects Apple Silicon, Intel Mac, Linux x64, Linux arm64, and WSL before downloading managed Node.

```bash
curl -fsSLO https://raw.githubusercontent.com/vibeforge1111/spark-cli/master/scripts/install.sh
less install.sh
bash ./install.sh \
  --bot-token "<BOTFATHER_TOKEN>" \
  --admin-telegram-ids "<YOUR_TELEGRAM_NUMERIC_ID>" \
  --llm-provider zai \
  --zai-api-key "<ZAI_API_KEY>"
```

The launch docs intentionally avoid `curl | bash` and `iwr | iex`. If a good Node/npm is already installed, the installer uses it to avoid a slow first-run download. Otherwise it downloads a managed Node runtime and verifies the archive against Node's published `SHASUMS256.txt` before extraction.

## BotFather and Telegram Owner Setup

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Copy the token into `--bot-token`.
4. Start the new bot and send `/myid`.
5. Re-run setup or edit your setup args with that numeric ID as `--admin-telegram-ids`.

Only `/start` and `/myid` are public onboarding commands. Normal chat, memory, Builder, LLM, and Spawner actions require `ADMIN_TELEGRAM_IDS`, `ALLOWED_TELEGRAM_IDS`, or explicit public mode.

## LLM Provider Setup

Use one provider for the first launch test.

### Z.AI GLM Coding Endpoint

```bash
spark setup \
  --bot-token "<BOTFATHER_TOKEN>" \
  --admin-telegram-ids "<YOUR_TELEGRAM_NUMERIC_ID>" \
  --llm-provider zai \
  --zai-api-key "<ZAI_API_KEY>" \
  --zai-base-url "https://api.z.ai/api/coding/paas/v4/" \
  --zai-model "glm-5.1"
```

### OpenAI

```bash
spark setup \
  --bot-token "<BOTFATHER_TOKEN>" \
  --admin-telegram-ids "<YOUR_TELEGRAM_NUMERIC_ID>" \
  --llm-provider openai \
  --openai-api-key "<OPENAI_API_KEY>" \
  --openai-model "gpt-5.5"
```

### Anthropic

```bash
spark setup \
  --bot-token "<BOTFATHER_TOKEN>" \
  --admin-telegram-ids "<YOUR_TELEGRAM_NUMERIC_ID>" \
  --llm-provider anthropic \
  --anthropic-api-key "<ANTHROPIC_API_KEY>" \
  --anthropic-model "claude-sonnet-4.5"
```

### Local Ollama

```bash
spark setup \
  --bot-token "<BOTFATHER_TOKEN>" \
  --admin-telegram-ids "<YOUR_TELEGRAM_NUMERIC_ID>" \
  --llm-provider ollama \
  --ollama-url "http://localhost:11434" \
  --ollama-model "kimi-k2.5:cloud"
```

Cloud keys and the Telegram bot token are stored through the Spark secret backend when the module manifest declares keychain storage. Generated module env must not be treated as the durable secret store.

## Expected Wiring After Setup

`spark-telegram-bot` receives at runtime, through generated env plus secret-backed start-time injection:

- `BOT_TOKEN`
- `ADMIN_TELEGRAM_IDS`
- `SPARK_BUILDER_REPO`
- `SPARK_BUILDER_HOME`
- `SPARK_BUILDER_BRIDGE_MODE=required`
- `SPARK_CHARACTER_ROOT`
- `SPAWNER_UI_URL=http://127.0.0.1:5173`
- `TELEGRAM_GATEWAY_MODE=polling`
- `TELEGRAM_RELAY_SECRET`
- selected LLM provider metadata and the declared provider key

`spawner-ui` receives:

- `MISSION_CONTROL_WEBHOOK_URLS=http://127.0.0.1:8788/spawner-events`
- `TELEGRAM_RELAY_SECRET`
- non-secret LLM provider metadata

`spark-intelligence-builder` receives:

- non-secret LLM provider metadata
- `SPARK_INTELLIGENCE_HOME`
- `SPARK_RESEARCHER_ROOT`
- `SPARK_CHARACTER_ROOT`
- `SPARK_DOMAIN_CHIP_MEMORY_ROOT`
- default memory initialized with `spark.memory.enabled=true`, `spark.memory.shadow_mode=false`, and `domain-chip-memory` active

The starter path should not require `SPARK_API_URL`, `SPARK_DASHBOARD_URL`, or anything on port `8787`.

## Real-Time Launch Test

Run these after install:

```bash
spark status --json
spark secrets list
spark start spawner-ui
spark start spark-telegram-bot
```

In Telegram:

1. Send `/start`.
2. Send `/myid` and confirm it matches setup.
3. Send `/diagnose`.
4. Send a normal message: `What can you do with my Spark memory and missions?`
5. Send `/remember Spark launch test memory is connected`.
6. Send `/remember my preferred Spark reply style is concise but warm`.
7. Send `/recall Spark launch test`.
8. Send `/run Create a small launch-readiness checklist for this Spark install`.
9. Send `/board`.
10. Send `/mission status <mission-id>` using the ID returned by `/run`.

Pass means:

- `/diagnose` shows Telegram, Builder memory bridge, Spawner, and the selected LLM provider as reachable or gives a specific repair hint.
- Normal chat returns an LLM-backed response, not a dead fallback.
- `/remember` and `/recall` go through Builder memory when available.
- explicit style saves return a short saved confirmation and never expose internal headings such as `Working Memory`.
- `/run` creates a Spawner mission and Telegram receives mission lifecycle updates through the secret-protected local relay.
- No launch step asks the user to start or configure a dashboard on `8787`.

## Sandbox Smoke Test Contract

Before shipping installer changes, run at least one sandbox setup with temp state:

```bash
SPARK_HOME="$(mktemp -d)" python -m spark_cli.cli setup \
  --non-interactive \
  --no-autostart \
  --no-start-now \
  --skip-install-commands \
  --skip-runtime-check \
  --skip-telegram-token-check \
  --secret telegram.bot_token=123456:test-token \
  --secret telegram.admin_ids=111222333 \
  --llm-provider zai \
  --zai-api-key test-zai-key
```

For local development, patch the registry to point at sibling local repos or run the unit test fixture. The smoke must verify:

- installed module records in starter order
- Telegram ingress owner is `spark-telegram-bot`
- `TELEGRAM_GATEWAY_MODE=polling`
- one shared `TELEGRAM_RELAY_SECRET` between Telegram and Spawner
- Telegram generated env includes `SPARK_BUILDER_HOME`, `SPARK_BUILDER_REPO`, and `SPARK_BUILDER_BRIDGE_MODE`
- Builder state has memory enabled, shadow mode disabled, `domain-chip-memory` active, and `spark-researcher` connected
- no raw cloud API key in Spawner or Builder generated env
- no generated `SPARK_API_URL`, `SPARK_DASHBOARD_URL`, or `8787` dependency

## Common Repair Hints

- Bot receives no messages: run `/getWebhookInfo` through Telegram or start the bot; Spark deletes active webhooks before polling, but only one polling process can own updates.
- Bot says admin only: send `/myid`, add that numeric ID to `ADMIN_TELEGRAM_IDS`, and rerun setup.
- LLM is offline: rerun `spark setup --llm-provider <provider> ...key...`, then `spark status`.
- `/run` fails: start `spawner-ui`, confirm `SPAWNER_UI_URL`, and check that Spawner has the same `TELEGRAM_RELAY_SECRET`.
- `/remember` says `Working Memory`, gives a vague answer, or later `/recall` misses it: rerun `spark setup`, restart `spark-telegram-bot`, and confirm Telegram env points to the same `SPARK_BUILDER_HOME` that Builder initialized. Launch setup should use `SPARK_BUILDER_BRIDGE_MODE=required`, so broken Builder memory fails visibly instead of silently falling back.
- Memory fallback appears: check Builder health and confirm `domain-chip-memory` is installed, active, and `spark.memory.shadow_mode=false`.

## Future Webhook Work

Webhook support is intentionally out of launch v1. Reintroduce it only through a hosted gateway migration with secret-token validation, replay protection, ingress tests, and public-network threat modeling. Do not document webhook setup as a user launch path until that exists.
## Known UX Gap — Architecture Explanation (Mission #16 QA, 2026-05-22)

### Bug: Bot misidentifies surface and gives incomplete first response

**Trigger:** User sends "I'm confused about which AI is doing what"

**Expected:** Bot explains Spark, outside LLM, Spawner, and Builder
clearly in one response without requiring follow-up questions.

**Actual observed behavior:**
- Bot said "Claude Code" — wrong surface, user was on Telegram
- Bot said "one AI, Claude" — skipped Spawner, Builder, memory entirely
- Correct explanation only appeared after two follow-up questions

**Fix needed:**
First response to architecture confusion questions must:
1. Correctly identify the surface (Telegram, not Claude Code)
2. Cover Spark, outside LLM, Spawner, and Builder in one reply
3. Not require follow-up to get a complete picture
