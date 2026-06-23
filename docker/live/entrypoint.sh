#!/usr/bin/env bash
set -euo pipefail
umask 077

log() {
  printf '[spark-live] %s\n' "$*"
}

die() {
  log "ERROR: $*"
  exit 2
}

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    die "$name is required. Set it as a platform secret/env var, not in the image."
  fi
}

looks_like_telegram_bot_token() {
  printf '%s' "$1" | grep -Eq '^[0-9]{6,}:'
}

has_telegram_bot_token_env() {
  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || [ -n "${BOT_TOKEN:-}" ]
}

has_telegram_admin_ids_env() {
  [ -n "${TELEGRAM_ADMIN_IDS:-}" ] || [ -n "${ADMIN_TELEGRAM_IDS:-}" ]
}

looks_like_telegram_admin_ids() {
  printf '%s' "$1" | grep -Eq '[0-9]{5,}'
}

is_public_spawner_bind() {
  local host="${SPARK_SPAWNER_HOST:-0.0.0.0}"
  [ "$host" = "0.0.0.0" ] || [ "$host" = "::" ] || [ -n "${SPARK_ALLOWED_HOSTS:-}" ]
}

validate_allowed_hosts() {
  local raw="${SPARK_ALLOWED_HOSTS:-}"
  if [ -z "$raw" ]; then
    die "SPARK_ALLOWED_HOSTS is required when Spawner binds publicly. Use exact hosted domains only."
  fi
  local IFS=','
  local host
  for host in $raw; do
    host="$(printf '%s' "$host" | xargs)"
    case "$host" in
      ""|"*"|"0.0.0.0"|"::"|"localhost"|"127.0.0.1"|"::1")
        die "SPARK_ALLOWED_HOSTS contains unsafe host '$host'. Use exact public hostnames only."
        ;;
      http://*|https://*|*/*|*:* )
        die "SPARK_ALLOWED_HOSTS must contain hostnames only, with no scheme, path, wildcard, or port."
        ;;
    esac
  done
}

require_strong_secret() {
  local name="$1"
  require_env "$name"
  local value="${!name}"
  if [ "${#value}" -lt 24 ]; then
    die "$name must be at least 24 characters for hosted/public Spark."
  fi
  case "$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')" in
    *changeme*|*change-me*|*placeholder*|*default*|*password*|*secret*|*token*|*spark*|*admin*|*test*)
      die "$name looks like a placeholder. Use a fresh random secret."
      ;;
  esac
  if printf '%s' "$value" | grep -q '[[:space:]]'; then
    die "$name must not contain whitespace."
  fi
}

if [ "$(id -u)" = "0" ] && [ "${SPARK_LIVE_PRIVILEGE_DROPPED:-0}" != "1" ]; then
  log "Preparing writable Spark state and dropping to the spark user..."
  mkdir -p "${SPARK_HOME:-/data/spark}" /home/spark
  chown -R spark:spark "${SPARK_HOME:-/data/spark}" /home/spark
  export SPARK_LIVE_PRIVILEGE_DROPPED=1
  exec gosu spark "$0" "$@"
fi

provider="${SPARK_LLM_PROVIDER:-}"
if [ -z "$provider" ]; then
  die "SPARK_LLM_PROVIDER is required. Good VPS/Railway choices: zai, codex with OPENAI_API_KEY, openai, openrouter, kimi, huggingface, minimax, anthropic with API key."
fi

telegram_mode="${SPARK_LIVE_TELEGRAM_MODE:-monolith}"
case "$telegram_mode" in
  monolith)
    require_env TELEGRAM_BOT_TOKEN
    require_env TELEGRAM_ADMIN_IDS
    ;;
  external)
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && looks_like_telegram_bot_token "$TELEGRAM_BOT_TOKEN"; then
      die "SPARK_LIVE_TELEGRAM_MODE=external but TELEGRAM_BOT_TOKEN looks like a real bot token. Put the token only on spark-telegram-bot."
    fi
    if [ -n "${BOT_TOKEN:-}" ] && looks_like_telegram_bot_token "$BOT_TOKEN"; then
      die "SPARK_LIVE_TELEGRAM_MODE=external but BOT_TOKEN looks like a real bot token. Put the token only on spark-telegram-bot."
    fi
    if [ -n "${TELEGRAM_ADMIN_IDS:-}" ] && looks_like_telegram_admin_ids "$TELEGRAM_ADMIN_IDS"; then
      die "SPARK_LIVE_TELEGRAM_MODE=external but TELEGRAM_ADMIN_IDS looks like real admin IDs. Put admin IDs only on spark-telegram-bot."
    fi
    if [ -n "${ADMIN_TELEGRAM_IDS:-}" ] && looks_like_telegram_admin_ids "$ADMIN_TELEGRAM_IDS"; then
      die "SPARK_LIVE_TELEGRAM_MODE=external but ADMIN_TELEGRAM_IDS looks like real admin IDs. Put admin IDs only on spark-telegram-bot."
    fi
    if has_telegram_bot_token_env || has_telegram_admin_ids_env; then
      log "Scrubbing Telegram ingress env vars from Spark Live external mode."
    fi
    unset TELEGRAM_BOT_TOKEN TELEGRAM_ADMIN_IDS BOT_TOKEN ADMIN_TELEGRAM_IDS
    log "Using external Telegram ingress owner; Spark Live will not require or start a local bot poller."
    ;;
  *)
    die "SPARK_LIVE_TELEGRAM_MODE must be 'monolith' or 'external'."
    ;;
esac

export SPARK_SPAWNER_PORT="${SPARK_SPAWNER_PORT:-${PORT:-5173}}"
export SPARK_SPAWNER_HOST="${SPARK_SPAWNER_HOST:-0.0.0.0}"

if is_public_spawner_bind; then
  validate_allowed_hosts
  require_strong_secret SPARK_BRIDGE_API_KEY
  require_strong_secret SPARK_UI_API_KEY
  if [ "$SPARK_BRIDGE_API_KEY" = "$SPARK_UI_API_KEY" ]; then
    die "SPARK_BRIDGE_API_KEY and SPARK_UI_API_KEY must be different."
  fi
fi

if [ -n "${SPARK_BRIDGE_API_KEY:-}" ]; then
  export MCP_API_KEY="${MCP_API_KEY:-$SPARK_BRIDGE_API_KEY}"
  export EVENTS_API_KEY="${EVENTS_API_KEY:-$SPARK_BRIDGE_API_KEY}"
fi

setup_args=(
  setup
  telegram-starter
  --non-interactive
  --no-autostart
  --no-start-now
  --run-install-commands
  --llm-provider
  "$provider"
  --spawner-ui-url
  "http://127.0.0.1:${SPARK_SPAWNER_PORT}"
)

if [ "$telegram_mode" = "external" ]; then
  setup_args+=(--external-telegram-ingress)
else
  setup_args+=(
    --bot-token
    "@env:TELEGRAM_BOT_TOKEN"
    --admin-telegram-ids
    "$TELEGRAM_ADMIN_IDS"
  )
fi

case "$provider" in
  zai)
    require_env ZAI_API_KEY
    setup_args+=(--zai-api-key "@env:ZAI_API_KEY")
    ;;
  openai)
    require_env OPENAI_API_KEY
    setup_args+=(--openai-api-key "@env:OPENAI_API_KEY")
    if [ -n "${OPENAI_BASE_URL:-}" ]; then
      setup_args+=(--openai-base-url "$OPENAI_BASE_URL")
    fi
    ;;
  openrouter)
    require_env OPENROUTER_API_KEY
    setup_args+=(--openrouter-api-key "@env:OPENROUTER_API_KEY")
    ;;
  kimi)
    require_env KIMI_API_KEY
    setup_args+=(--kimi-api-key "@env:KIMI_API_KEY")
    ;;
  huggingface)
    require_env HF_TOKEN
    setup_args+=(--huggingface-api-key "@env:HF_TOKEN")
    ;;
  minimax)
    require_env MINIMAX_API_KEY
    setup_args+=(--minimax-api-key "@env:MINIMAX_API_KEY")
    ;;
  anthropic)
    require_env ANTHROPIC_API_KEY
    setup_args+=(--anthropic-api-key "@env:ANTHROPIC_API_KEY")
    ;;
  codex)
    require_env OPENAI_API_KEY
    export CODEX_HOME="${CODEX_HOME:-${SPARK_HOME:-/data/spark}/codex}"
    mkdir -p "$CODEX_HOME"
    printenv OPENAI_API_KEY | codex login --with-api-key >/dev/null
    ;;
  lmstudio)
    setup_args+=(--lmstudio-base-url "${LMSTUDIO_BASE_URL:-http://host.docker.internal:1234/v1}" --lmstudio-model "${LMSTUDIO_MODEL:-local-model}")
    ;;
  ollama)
    setup_args+=(--ollama-url "${OLLAMA_URL:-http://host.docker.internal:11434}" --ollama-model "${OLLAMA_MODEL:-llama3.2:3b}")
    ;;
  *)
    die "Unsupported SPARK_LLM_PROVIDER '$provider'."
    ;;
esac

if [ -n "${SPARK_MODEL:-}" ]; then
  case "$provider" in
    zai) setup_args+=(--zai-model "$SPARK_MODEL") ;;
    openai) setup_args+=(--openai-model "$SPARK_MODEL") ;;
    openrouter) setup_args+=(--openrouter-model "$SPARK_MODEL") ;;
    kimi) setup_args+=(--kimi-model "$SPARK_MODEL") ;;
    huggingface) setup_args+=(--huggingface-model "$SPARK_MODEL") ;;
    minimax) setup_args+=(--minimax-model "$SPARK_MODEL") ;;
    anthropic) setup_args+=(--anthropic-model "$SPARK_MODEL") ;;
    codex) setup_args+=(--codex-model "$SPARK_MODEL") ;;
    lmstudio) setup_args+=(--lmstudio-model "$SPARK_MODEL") ;;
    ollama) setup_args+=(--ollama-model "$SPARK_MODEL") ;;
  esac
fi

cleanup() {
  log "Stopping Spark Live..."
  spark live stop >/dev/null 2>&1 || true
  if [ -n "${log_pid:-}" ]; then
    kill "$log_pid" 2>/dev/null || true
    wait "$log_pid" 2>/dev/null || true
  fi
}
trap cleanup TERM INT

log "Configuring Spark in ${SPARK_HOME} with provider '${provider}'..."
spark "${setup_args[@]}"

if [ "${SPARK_LIVE_SKIP_UPDATE:-0}" != "1" ]; then
  log "Refreshing installed modules to the image registry pins..."
  spark update --skip-dirty
fi

log "Starting Spark Live on Spawner ${SPARK_SPAWNER_HOST}:${SPARK_SPAWNER_PORT}..."
spark live start

log "Spark Live is running. Combined logs follow."
spark live logs --follow --lines 80 &
log_pid="$!"
wait "$log_pid"
