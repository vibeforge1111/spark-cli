# Security Policy

Spark CLI installs and supervises an autonomous agent that, at its recommended
access level, can read, write, and run code inside a working folder on your
machine. This document is the plain-language disclosure of what Spark stores,
what the agent can do at each access level, what leaves your computer, and the
preconditions for the autonomous mission lane. Read the Privacy, Access Model,
and Telemetry sections before granting access.

## Privacy and Local Data Storage

Spark stores its working data locally, under `~/.spark/` (override with
`SPARK_HOME`). Nothing in this directory is uploaded by Spark itself.

- `~/.spark/state/` - install state, pids, setup state.
- `~/.spark/config/` - user config, generated module env files, the
  keychain-backed secret index, and `secrets.local.json` on the file backend.
- `~/.spark/logs/<module>/` - per-module process logs, including the
  metadata-only trace material that `spark trace` reconstructs.
- `~/.spark/modules/<name>/source/` - the installed module checkouts.
- `~/.spark/workspaces/` - the safe working folder agents use at Level 4.

Conversational memory and learned domain-chip insights live in the local
Builder home (`SPARK_BUILDER_HOME`) and the `domain-chip-memory` store. This can
include the content of your Telegram messages, saved notes, and recalled facts.
It is kept on your machine. It is not sent anywhere by Spark, but it is visible
to the LLM provider you configure as part of normal chat and recall (see
Telemetry). Treat `~/.spark/` and the Builder home as private: they can contain
message content, local paths, and secret material, and must never be committed
to git (see Files That Must Never Be Committed).

To remove this data, use `spark uninstall` (rotates secrets and removes generated
config) or delete `~/.spark/` directly. `spark security revoke-all` clears
Spark-managed local secrets and writes a redacted incident bundle.

## Access Model

Spark gates what the agent may touch behind explicit access levels. The default
recommended level for builders is Level 4; whole-computer access (Level 5) is
never enabled silently.

- Level 1 - Chat, memory, recall, and diagnostics. No missions, no local files.
- Level 2 - Plus explicitly requested missions/builds. Still no public research
  or local file access.
- Level 3 - Plus public web and GitHub research. Still no local file access.
- Level 4 - Recommended for builders. The agent works inside one safe workspace
  (`~/.spark/workspaces/default` by default) with Mission Control builds,
  debugging, and repo inspection. Destructive filesystem, credential reveal,
  git history rewrite, publish/deploy, and similar actions still require explicit
  per-action approval.
- Level 5 - Whole-computer operator mode. Removes the workspace boundary. It is
  explicit opt-in only, via `spark access setup --level 5 --enable-high-agency`,
  writes an audit event, and can be reverted with `spark access disable-level5`.
  Even at Level 5, deletion, secret-reveal, and publish/deploy actions still
  require approval.

Approval classification is enforced by the command guard; you can inspect how any
command is classified with `spark approval classify -- <command>`.

Recommendation: keep the agent scoped to its workspace. Let Spark create and use
`~/.spark/workspaces/` (the Level 4 default) rather than pointing it at your
Desktop, home directory, or a folder with unrelated personal files. The workspace
boundary is a practical file boundary, not a hardened container; for stronger
isolation use the optional Docker or Modal sandbox lanes.

## Telemetry and Outbound Network

Spark CLI has no usage telemetry, analytics, or phone-home. There is no
analytics SDK in the code (verified: no PostHog, Segment, Mixpanel, Amplitude,
Sentry, or beacon). It does not upload your memory, traces, logs, or workspace.

Spark does make these outbound connections, all of which you control or expect:

- The LLM provider you configure (for example OpenAI, Anthropic, Z.AI, MiniMax,
  OpenRouter, or a local Ollama/LM Studio endpoint). Chat, builder, memory, and
  mission roles send prompts there, which can include message and memory content.
- The Telegram Bot API (`api.telegram.org`), because Spark runs your Telegram
  bot.
- `localhost`/`127.0.0.1`, for the local Spawner UI and mission relay.
- `agent.sparkswarm.ai`, only when you explicitly run
  `spark verify --installers --hosted-installers` to compare installer bytes and
  checksums against the published manifest. This is opt-in integrity
  verification, not background reporting.

`spark doctor llm` and `spark doctor llm --include-logs` deliberately send a
redacted local repair plan to your configured LLM provider; `--include-logs`
requires approval because it can include log content.

## Reporting a Vulnerability

Please do not report security vulnerabilities in public issues, public PRs, or
competition comments. Use GitHub private vulnerability reporting instead:

https://github.com/vibeforge1111/spark-cli/security/advisories/new

Include the affected command or workflow, reproduction steps, expected impact,
and any safe proof you can share without exposing live credentials, private
repos, browser cookies, local paths, or wallet material.

Spark's launcher and starter bundle should keep secrets out of tracked files,
generated config, terminal output, and model-visible context.

## Secret Storage

- Use `spark setup` or `spark secrets set` for sensitive values.
- Module manifests declare secrets in `[needs].secrets` and `[secrets.*]`.
- `storage = "keychain"` secrets are stored in the OS keychain when available.
- On Windows, the file backend stores values protected by DPAPI.
- On non-Windows systems, the file backend is disabled unless
  `SPARK_ALLOW_INSECURE_FILE_SECRETS=1` is explicitly set for disposable local
  tests.
- Generated module env files must not contain raw cloud API keys when the module
  declares the matching keychain-backed secret.

## Files That Must Never Be Committed

- `.env`, `.env.*`, except placeholder-only `.env.example`
- `secrets.local.json`
- local state under `~/.spark/state`, `~/.spark/config`, `~/.spark/logs`
- local runtime databases, token files, gateway state, and process logs

## Launch Verification

Before a launch or demo:

1. Run `git status --short` in every touched repo.
2. Run a tracked-file secret scan for API-key and Telegram-token patterns.
3. Run a sandbox `spark setup` with fake tokens and verify generated env files
   do not contain the fake cloud API key.
4. Confirm the real Telegram bot has exactly one polling owner and no Telegram
   webhook env is configured.
5. Rotate any real token that was pasted into a chat, log, or terminal transcript.

## Panic Revocation

If you suspect local Spark credentials or control-plane keys leaked, run:

```bash
spark security revoke-all
```

This stops tracked Spark processes, disables login autostart, rotates generated
local bridge/API keys, disables custom MCP configs, clears Telegram webhook
state where a bot token is available, removes Spark-managed local secrets,
pauses local mission state, and writes a redacted support bundle. Provider-side
tokens still need revocation in BotFather, GitHub, Scanner, or the relevant API
console when applicable.

## Mission Lane Preconditions

The autonomous mission lane (Mission Control builds run from Telegram or the
Spawner UI) needs live runtime pieces in place. It can silently fail to complete
a mission if any are missing. Before relying on it, verify with:

```bash
spark verify --mission
```

The preconditions it checks are:

- `spawner-ui` is running and reachable (default `http://127.0.0.1:3333`). Start
  it with `spark start spawner-ui` if needed.
- The mission provider is signed in. The live default is OpenAI Codex, which
  needs the Codex CLI on PATH and `codex login` completed. A missing or
  unauthenticated provider makes missions 409 or expire.
- `SPARK_GOVERNOR_HMAC_KEY` is provisioned so Governor decisions are signed.
  `spark setup` generates this key; without it, a mission can be blocked as an
  unsigned/`governor_hmac_key_missing` decision.

`spark verify --mission` exits `0` only after a real mission runs to completion
end to end, so it distinguishes "the bot replies" from "missions actually run".

## Threat Model

Spark installs and runs local agent tooling. Treat every connected LLM, browser,
Telegram message, web page, plugin, and repo as potentially untrusted input.
Secrets should be available only to the subprocess that needs them, at runtime,
and never written into prompts, public config, committed files, or launch docs.
