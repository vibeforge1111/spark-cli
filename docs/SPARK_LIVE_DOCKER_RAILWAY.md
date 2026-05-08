# Spark Live on Docker, Railway, and VPS

Last updated: 2026-05-03

Spark should be easy to test in an environment that is not the operator's laptop. This lane is for realtime sandbox agents: a disposable or persistent container that runs Spark Live, Telegram long polling, Builder, memory, character, and Spawner together.

This is separate from the locked-down Docker workbench in `docs/OPTIONAL_DOCKER_WORKBENCH.md`. The live lane has network on by design because Telegram and the selected LLM provider need it.

## What Runs

The live container starts:

- as `root` only long enough to prepare the mounted state volume, then drops to the non-root `spark` user;
- `spark setup telegram-starter` in `/data/spark`;
- `spark update --skip-dirty` so persistent volumes move to the image's current registry pins on redeploy;
- `spark live start`;
- `spawner-ui`, bound to `0.0.0.0:$SPARK_SPAWNER_PORT`;
- `spark-telegram-bot`, using Telegram long polling;
- Builder, memory, researcher, and character as installed modules/configured roots.

Secrets are read from environment variables only. They are not baked into the image.

## Best First Host

Use Docker locally for smoke tests, then Railway for a hosted sandbox.

Railway is a good first target because it gives:

- a public HTTPS app URL for Spawner/Canvas/Kanban;
- app secrets as environment variables;
- optional persistent volumes for `/data/spark`;
- simple redeploys when Spark CLI is pinned to a new release.

Any VPS with Docker also works.

## What We Learned From Other Agent Hosts

OpenClaw-style hosted deployments show why browser-first onboarding matters:
users understand a single `/setup` or control-panel surface much faster than
SSH plus many terminal commands. Railway templates also proved that a persistent
volume, setup wizard, model/channel picker, and one public HTTPS URL are a good
shape for nontechnical users.

The same pattern creates risk if it is not locked down. Spark Live should keep
these standards:

- one public surface, protected by a user-chosen access key;
- API routes require `SPARK_BRIDGE_API_KEY`, not just a browser cookie;
- setup is browser-friendly, but repeat setup is not an unauthenticated open URL;
- public hosts must set `SPARK_ALLOWED_HOSTS` to exact domains;
- the runtime drops to a non-root user before starting Spark services;
- no Docker socket, host root, cloud credentials, SSH keys, browser profiles, or
  real local `~/.spark` mounts;
- headless hosts use API-key providers, not interactive OAuth CLIs;
- every hosted release must pass `spark live verify --quick`; release-candidate
  pins must also pass `spark live verify` before they are promoted publicly.

Hermes-style approval systems are also relevant for future full-access hosted
agents: dangerous shell/file operations should ask in-chat or in-UI, with
allowlists that users can inspect and remove. Spark Live is not ready for a
public "full operating system access" VPS mode until those approvals and
sandbox boundaries are first-class.

## Hosted Provider Recommendation

For Railway and other headless hosts, use API-first provider auth. Hosted Spark
should be boring: bot, Spawner, Mission Control, previews, and private relays run
in the container; model work goes to an API provider or to a model server the
container can reach.

Safe hosted defaults:

- `zai`, `openai`, `openrouter`, `kimi`, `huggingface`, and `minimax` use
  provider API keys.
- `anthropic` uses `ANTHROPIC_API_KEY` in hosted containers. Claude Code OAuth
  stays a local desktop route.
- `codex` may use the Codex CLI in hosted containers only with a dedicated
  `OPENAI_API_KEY`. The live image writes that key into `CODEX_HOME` at startup.
- `lmstudio` and `ollama` should point at a reachable model server. Do not expect
  Railway to run large local models inside the Spark container.

Do not copy personal `~/.codex`, Claude Code, browser profile, or desktop OAuth
state into Railway. Use revocable service keys for hosted sandboxes.

## Required Environment

Choose one Telegram polling owner before setting secrets:

- Monolith Spark Live: this container owns Telegram long polling, so set
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS` here.
- Split Railway/VPS: a standalone `spark-telegram-bot` service owns Telegram
  long polling, so do not set `TELEGRAM_BOT_TOKEN` on Spark Live. Put the token
  only on the bot service as `BOT_TOKEN`, and set
  `SPARK_LIVE_TELEGRAM_MODE=external` on Spark Live.

If both Spark Live and `spark-telegram-bot` receive the same bot token, Telegram
will terminate one poller with `409 Conflict: terminated by other getUpdates
request`.

Minimum for monolith Spark Live:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_IDS=123456789
SPARK_LLM_PROVIDER=zai
ZAI_API_KEY=...
```

Minimum for split Railway/VPS Spark Live:

```text
SPARK_LIVE_TELEGRAM_MODE=external
SPARK_LLM_PROVIDER=zai
ZAI_API_KEY=...
```

Minimum for the separate split `spark-telegram-bot` service:

```text
BOT_TOKEN=...
ADMIN_TELEGRAM_IDS=123456789
TELEGRAM_GATEWAY_MODE=polling
TELEGRAM_RELAY_SECRET=<same-random-relay-secret-as-Spark-Live>
TELEGRAM_RELAY_URL=http://spark-telegram-bot.railway.internal:8788/spawner-events
```

Supported `SPARK_LLM_PROVIDER` values for headless hosts:

| Provider | Required env | Notes |
|---|---|---|
| `zai` | `ZAI_API_KEY` | Good default for API-key VPS sandboxes. |
| `codex` | `OPENAI_API_KEY` | Codex CLI in the container, authenticated from a dedicated OpenAI key. |
| `openai` | `OPENAI_API_KEY` | Use this for OpenAI API keys. |
| `openrouter` | `OPENROUTER_API_KEY` | Broad model gateway. |
| `kimi` | `KIMI_API_KEY` | Moonshot/Kimi OpenAI-compatible route. |
| `huggingface` | `HF_TOKEN` | Hugging Face router. |
| `minimax` | `MINIMAX_API_KEY` | MiniMax OpenAI-compatible route. |
| `anthropic` | `ANTHROPIC_API_KEY` | API-key mode only in containers. |
| `lmstudio` | `LMSTUDIO_BASE_URL`, optional `LMSTUDIO_MODEL` | Only if the container can reach your LM Studio server. |
| `ollama` | `OLLAMA_URL`, optional `OLLAMA_MODEL` | Only if the container can reach your Ollama server. |

Codex OAuth is an interactive local CLI sign-in path. It belongs on a user's
machine, not in a hosted container. For hosted Codex, use `SPARK_LLM_PROVIDER=codex`
with `OPENAI_API_KEY`, or use `SPARK_LLM_PROVIDER=openai` if you want the direct
OpenAI API route instead of the Codex CLI route.

Optional:

```text
SPARK_MODEL=provider-specific-model-id
SPARK_SPAWNER_PORT=5173
SPARK_SPAWNER_HOST=0.0.0.0
```

On Railway, map `SPARK_SPAWNER_PORT` to `$PORT` if you expose the web process.

## Local Docker Smoke

From the `spark-cli` repo:

```bash
docker build -f docker/live/Dockerfile -t spark-live:local .
```

Run with a disposable Spark home:

```bash
docker run --rm -it \
  -p 5173:5173 \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_ADMIN_IDS="$TELEGRAM_ADMIN_IDS" \
  -e SPARK_LLM_PROVIDER=zai \
  -e ZAI_API_KEY="$ZAI_API_KEY" \
  spark-live:local
```

For persistence:

```bash
docker volume create spark-live-data
docker run --rm -it \
  -p 5173:5173 \
  -v spark-live-data:/data/spark \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_ADMIN_IDS="$TELEGRAM_ADMIN_IDS" \
  -e SPARK_LLM_PROVIDER=zai \
  -e ZAI_API_KEY="$ZAI_API_KEY" \
  spark-live:local
```

Then check:

```bash
docker exec -it <container> spark live status
docker exec -it <container> spark live verify --quick
```

## Railway Shape

Recommended Railway settings:

```text
Build: Dockerfile
Dockerfile path: docker/live/Dockerfile
Start command: leave empty; the image entrypoint starts Spark Live
Volume mount: /data/spark
```

Set Spark Live secrets in Railway Variables, never in source control:

```text
RAILWAY_DOCKERFILE_PATH=docker/live/Dockerfile
RAILWAY_RUN_UID=0
SPARK_ALLOWED_HOSTS=<your-railway-domain>.up.railway.app
SPARK_UI_API_KEY=<different-random-secret-at-least-24-chars>
SPARK_BRIDGE_API_KEY=<different-random-secret-at-least-24-chars>
SPARK_LLM_PROVIDER
ZAI_API_KEY / OPENAI_API_KEY / etc.
CODEX_HOME=/data/spark/codex
SPARK_SPAWNER_PORT=${PORT}
```

Only add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS` to Spark Live for a
monolith deployment where Spark Live owns Telegram polling.

For split Railway deploys, omit `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS`
from this Spark Live service. The separate `spark-telegram-bot` service should
hold `BOT_TOKEN`, `ADMIN_TELEGRAM_IDS`, `TELEGRAM_GATEWAY_MODE=polling`, relay
settings, and the shared bridge secret. Set `SPARK_LIVE_TELEGRAM_MODE=external`
on Spark Live so the Docker entrypoint configures the runtime without requiring
or starting a local Telegram poller.

`RAILWAY_RUN_UID=0` lets the entrypoint repair Railway volume ownership. Spark then
drops to the non-root `spark` user before setup and runtime work starts.
`SPARK_ALLOWED_HOSTS` lets Spawner's Vite server accept the generated Railway
domain without disabling host-header protection for every possible host. Use
hostnames only: no `https://`, no paths, no wildcards, no loopback values.
`SPARK_UI_API_KEY` protects the hosted Spawner UI. Open the Railway URL and Spark
will redirect browser users to `/spark-live/login`; paste the UI key there to set
an httpOnly browser cookie. The `?uiKey=<SPARK_UI_API_KEY>` route is a legacy
automation/bootstrap escape hatch only. Do not share it with humans or paste it
into chat; query-string secrets can leak through browser history and request
logs.
`SPARK_BRIDGE_API_KEY` protects mission-start/control APIs.

## Hardened VPS Compose

For VPS hosts where you control Docker runtime flags, start from
`docker/live/docker-compose.vps.yml`. It uses the Docker hardening controls that
the hosted audit checks for:

- `security_opt: no-new-privileges:true`
- `cap_drop: [ALL]`
- `read_only: true`
- tmpfs `/tmp`
- one writable Spark state mount at `/data/spark`

Before the first start, create the state directory and give it to the `spark`
image UID. This avoids needing root capabilities inside the running container:

```bash
cd docker/live
mkdir -p spark-data
sudo chown -R 1001:1001 spark-data
cp spark-live.env.example spark-live.env
```

Then put the same Railway-style variables in `spark-live.env` and start:

```bash
docker compose -f docker-compose.vps.yml up -d --build
docker compose -f docker-compose.vps.yml exec spark-live spark security audit --hosted
```

If you need the entrypoint to repair an existing root-owned volume, do that as a
one-time maintenance step without `cap_drop: [ALL]`, then restore the hardened
Compose file before running the public service.

After deploy:

1. Open the Railway logs and confirm `Spark Live is running`.
2. Run `spark live status` inside the container or over `railway ssh`.
3. Run `spark live verify --quick` for the fast hosted security gate.
4. Run `spark live verify` for a release-candidate gate. It may start a protected
   mission smoke and spend real LLM credits.
5. Open the Railway URL and sign in at `/spark-live/login`.
6. Open `/spark-live/setup` and confirm the checklist shows browser auth,
   bridge auth, allowed hosts, Telegram, agent LLM, mission LLM, and full-access
   safety as ready.
7. Send `/diagnose` to the sandbox Telegram bot.
8. Send `/remember Railway sandbox works`, then `/recall Railway sandbox`.
9. Send this constrained static build smoke:

   ```text
   /run Build a tiny static HTML page called Spark Production Smoke. It should have one file, index.html, with a dark Mission Control panel, a green "Spark Live OK" status, and the text "Telegram to Spawner relay worked on May 8, 2026". Do not add package files, do not install dependencies, and keep it simple enough to finish fast.
   ```

Pass criteria:

- `/diagnose` shows the bot relay and Spawner UI as reachable.
- If plain chat times out but Spawner mission ping passes, treat that as a chat
  provider timeout to tune, not a failed build path.
- The mission plan has the constrained static steps: `Create Exact Static Index
  HTML` and `Verify One-File Static Contract`.
- The mission completes with `2` completed tasks and `0` failed tasks.
- The generated workspace contains `index.html` with `Spark Live OK` and
  `Telegram to Spawner relay worked on May 8, 2026`.
- The generated workspace does not need `package.json`, `node_modules`, or
  dependency installation.

For a repeatable operator-side check across the split Railway services, run:

```powershell
.\scripts\railway-production-smoke.ps1 `
  -SparkLiveCwd C:\path\to\spark-cli-prod-worktree `
  -TelegramBotCwd C:\path\to\spark-telegram-bot `
  -PublicUrl https://spark-live-production.up.railway.app
```

The script checks public health, `spark live status`, the installed Spawner
registry pin, Telegram bot runtime health, and the bot service's authenticated
health/providers/mission-board calls into Spawner. It does not start a new LLM
mission, so use the Telegram `/run` smoke above for the full paid-provider path.

The hosted deep smoke is intentionally not part of the fast default check. It
uses the configured mission provider and may spend real LLM credits.

## Release Gate Before Public Pins

Do not point `agent.sparkswarm.ai` or a public release manifest at a new Spark
Live CLI/image until this gate passes:

```bash
python -m pytest tests/test_cli.py -q
python -m spark_cli.cli verify --registry-pins
python -m spark_cli.cli verify --provenance
python -m spark_cli.cli verify --sandboxes
railway up --detach --service spark-live
railway ssh --service spark-live spark live status
railway ssh --service spark-live spark live verify --quick
```

Then check Railway logs for:

- the entrypoint dropping from `root` to the non-root `spark` user;
- setup completing without raw secret values in output;
- `spark update --skip-dirty` resolving every pinned module;
- `spark live start` starting both `spawner-ui` and `spark-telegram-bot`;
- no `upload-pack: not our ref` errors from a mistyped or unpushed registry pin.

If Docker Desktop is available locally, also run the local Docker smoke first.
If it is not running, record that as an environment limitation rather than
calling the release gate complete.

## Security Rules

- Use a fresh Telegram bot for every hosted sandbox.
- Keep sandbox API keys scoped and revocable.
- Prefer separate hosted sandbox provider keys from the operator's main personal keys.
- Require `SPARK_UI_API_KEY` and `SPARK_BRIDGE_API_KEY` before exposing Spawner on a public host.
- Make `SPARK_UI_API_KEY` and `SPARK_BRIDGE_API_KEY` different random values,
  at least 24 characters each. Do not use placeholders such as `changeme`,
  `password`, `secret`, or `spark`.
- Keep hosted secret files private. `spark live verify --quick` fails if a POSIX
  `secrets.local.json` is group/world-readable.
- Do not mount or copy a real local `~/.spark` into hosted containers.
- Never mount `/var/run/docker.sock`, `/`, `/root`, cloud credential directories, SSH keys, or browser profiles.
- Prefer Docker hardening flags on VPS: `--cap-drop=ALL`, `--security-opt no-new-privileges`, resource limits, and only one writable Spark state volume.
- Use a persistent volume only when you intentionally want memory/state to survive redeploys.
- Rotate tokens after demos if screenshots/logs might have exposed them.
- Do not expose shell/terminal access in the browser until it is behind a separate
  admin auth layer and a dangerous-command approval system.
- Keep public health probes shallow. Deep health checks that reveal providers,
  mission ids, logs, or memory state must require an admin key.

## Recommended Hosted UX

For Spark to feel easier than current agent VPS setups, the target flow should be:

1. Click "Deploy Spark Live" from the site.
2. Choose a host template such as Railway for the easiest first path.
3. Enter one setup password/UI key, Telegram bot token, Telegram admin id, and one LLM provider.
4. Spark generates bridge secrets, stores them as platform variables, and starts.
5. Browser opens `/spark-live/login`, then Mission Control shows a guided checklist.
6. Telegram `/diagnose` and `spark live verify` both pass.

For VPS users who want full control, offer a Docker Compose path with the same
checks, but do not make them discover firewall, host header, volume ownership,
and secret rules by accident.

## References Used For This Standard

- OpenClaw Docker docs: non-root image, persistence paths, health checks,
  gateway bind modes, sandbox behavior, and Docker socket caveats.
- Railway OpenClaw templates: browser setup, model/channel picker, admin
  dashboard, persistent `/data`, and single-port deployment pattern.
- Hermes Agent security docs: dangerous-command approval, gateway allowlists,
  pairing, and Docker terminal backend resource/security settings.

## What This Proves

This lane proves Spark can:

- install the whole ecosystem on a clean Linux host;
- run Telegram long polling without webhooks;
- keep Spawner, Telegram, memory, and LLM routing alive under one foreground process;
- support VPS/Railway users who do not want to keep a laptop terminal open.

It does not replace the local installer. Local users should still use the hosted installer from `agent.sparkswarm.ai`.
