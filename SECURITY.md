# Security Policy

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

## Threat Model

Spark installs and runs local agent tooling. Treat every connected LLM, browser,
Telegram message, web page, plugin, and repo as potentially untrusted input.
Secrets should be available only to the subprocess that needs them, at runtime,
and never written into prompts, public config, committed files, or launch docs.
