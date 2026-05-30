#!/usr/bin/env bash
set -euo pipefail

SPARK_PREFIX="${SPARK_PREFIX:-$HOME/.spark}"
SPARK_CLI_SOURCE="${SPARK_CLI_SOURCE:-https://github.com/vibeforge1111/spark-cli}"
SPARK_CLI_RELEASE_NAME="${SPARK_CLI_RELEASE_NAME:-spark-cli-public-installer-2026-05-30-r22}"
SPARK_DEFAULT_CLI_REF="spark-cli-public-installer-2026-05-30-r22"
SPARK_CLI_REF_USER_SET=0
if [ -n "${SPARK_CLI_REF:-}" ]; then
  SPARK_CLI_REF_USER_SET=1
fi
SPARK_CLI_REF="${SPARK_CLI_REF:-$SPARK_DEFAULT_CLI_REF}"
SPARK_NODE_VERSION="${SPARK_NODE_VERSION:-22.18.0}"
SPARK_PYTHON_VERSION="${SPARK_PYTHON_VERSION:-3.11}"
SPARK_UV_VERSION="${SPARK_UV_VERSION:-0.11.7}"
SPARK_SKIP_SETUP="${SPARK_SKIP_SETUP:-0}"
SPARK_AUTOSTART_USER_SET=0
if [ -n "${SPARK_AUTOSTART+x}" ]; then
  SPARK_AUTOSTART_USER_SET=1
fi
SPARK_AUTOSTART="${SPARK_AUTOSTART:-1}"
SPARK_BUNDLE="${SPARK_BUNDLE:-telegram-starter}"
SPARK_SETUP_ARGS="${SPARK_SETUP_ARGS:-}"
SPARK_LOCAL_REGISTRY="${SPARK_LOCAL_REGISTRY:-}"
SPARK_NODE_PLATFORM="${SPARK_NODE_PLATFORM:-}"
SPARK_MANAGED_NODE="${SPARK_MANAGED_NODE:-0}"
SPARK_BOT_TOKEN="${SPARK_BOT_TOKEN:-}"
SPARK_ADMIN_TELEGRAM_IDS="${SPARK_ADMIN_TELEGRAM_IDS:-}"
SPARK_LLM_PROVIDER="${SPARK_LLM_PROVIDER:-}"
SPARK_ZAI_API_KEY="${SPARK_ZAI_API_KEY:-}"
SPARK_OPENAI_API_KEY="${SPARK_OPENAI_API_KEY:-}"
SPARK_ANTHROPIC_API_KEY="${SPARK_ANTHROPIC_API_KEY:-}"
SPARK_MINIMAX_API_KEY="${SPARK_MINIMAX_API_KEY:-}"
SPARK_NON_INTERACTIVE_SETUP="${SPARK_NON_INTERACTIVE_SETUP:-0}"
SPARK_SETUP_SKIP_INSTALL_COMMANDS="${SPARK_SETUP_SKIP_INSTALL_COMMANDS:-0}"
SPARK_SETUP_SKIP_RUNTIME_CHECK="${SPARK_SETUP_SKIP_RUNTIME_CHECK:-0}"
SPARK_SHELL_PROFILE="${SPARK_SHELL_PROFILE:-auto}"
SPARK_NODE_BIN_DIR=""
SPARK_PYTHON_BIN=""
SPARK_UV_BIN=""
SPARK_INSTALL_LOG=""
SPARK_CANONICAL_CLI_SOURCE="https://github.com/vibeforge1111/spark-cli"
SPARK_ALLOW_DEV_SOURCE="${SPARK_ALLOW_DEV_SOURCE:-0}"
SPARK_DRY_RUN="${SPARK_DRY_RUN:-0}"
SPARK_PREFLIGHT_ONLY="${SPARK_PREFLIGHT_ONLY:-0}"
SPARK_ASSUME_YES="${SPARK_ASSUME_YES:-0}"
SPARK_EXISTING_MODE="${SPARK_EXISTING_MODE:-abort}"
SPARK_INSTALL_LOCK_DIR=""
SPARK_SECRET_FILES=()

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Install Spark CLI into a local prefix without depending on system Node.

Options:
  --prefix DIR              Install prefix (default: ~/.spark)
  --source URL_OR_PATH      developer override for spark-cli source; requires --allow-dev-source
  --ref REF                 developer override for git ref; requires --allow-dev-source
  --node-version VERSION    Managed Node version (default: 22.18.0)
  --python-version VERSION  Managed Python version used via uv when needed (default: 3.11)
  --uv-version VERSION      Managed uv version used for Python when needed (default: 0.11.7)
  --managed-node            Force Spark's verified managed Node download even if system Node is good
  --bundle NAME             Bundle for setup (default: telegram-starter)
  --bot-token TOKEN         Telegram BotFather token passed to setup
  --admin-telegram-ids IDS  Comma-separated Telegram admin IDs passed to setup
  --llm-provider PROVIDER   Default provider for Agent and Mission: codex, anthropic, zai, kimi, openrouter, huggingface, lmstudio, minimax, ollama, or openai
  --zai-api-key KEY         Z.AI / GLM API key passed to setup
  --openai-api-key KEY      OpenAI API key passed to setup
  --anthropic-api-key KEY   Anthropic API key passed to setup
  --minimax-api-key KEY     MiniMax API key passed to setup
  --non-interactive-setup   Pass --non-interactive to setup
  --setup-skip-install-commands
                            Pass --skip-install-commands to setup
  --setup-skip-runtime-check
                            Pass --skip-runtime-check to setup
  --setup-arg ARG           Extra arg passed to `spark setup`; repeatable
  --dry-run                 Print planned install actions and exit without writing files
  --preflight               Check prerequisites and install plan, then exit
  --yes                     Run after the plan without interactive confirmation
  --no-shell-profile        Do not add Spark to the user's shell profile
  --local-registry PATH     developer registry override; requires --allow-dev-source
  --allow-dev-source        Allow source/ref/local-registry overrides for local development
  --upgrade-existing        Allow updating an existing Spark prefix
  --skip-setup              Install CLI only; do not run spark setup
  --autostart               Install and start the login autostart hook after setup (default)
  --no-autostart            Do not install autostart
  -h, --help                Show this help

Environment mirrors these flags:
  SPARK_PREFIX, SPARK_CLI_SOURCE, SPARK_CLI_REF, SPARK_NODE_VERSION,
  SPARK_PYTHON_VERSION, SPARK_UV_VERSION, SPARK_BUNDLE, SPARK_SETUP_ARGS, SPARK_LOCAL_REGISTRY, SPARK_SKIP_SETUP,
  SPARK_AUTOSTART, SPARK_ALLOW_DEV_SOURCE, SPARK_MANAGED_NODE,
  SPARK_BOT_TOKEN, SPARK_ADMIN_TELEGRAM_IDS, SPARK_LLM_PROVIDER,
  SPARK_ZAI_API_KEY, SPARK_OPENAI_API_KEY, SPARK_ANTHROPIC_API_KEY,
  SPARK_MINIMAX_API_KEY,
  SPARK_NON_INTERACTIVE_SETUP, SPARK_SETUP_SKIP_INSTALL_COMMANDS,
  SPARK_SETUP_SKIP_RUNTIME_CHECK, SPARK_SHELL_PROFILE,
  SPARK_NODE_PLATFORM, SPARK_DRY_RUN, SPARK_PREFLIGHT_ONLY,
  SPARK_ASSUME_YES, SPARK_EXISTING_MODE.
EOF
}

extra_setup_args=()

require_option_value() {
  local option="$1"
  if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
    echo "Missing value for $option." >&2
    usage >&2
    exit 2
  fi
}

require_non_option_value() {
  local option="$1"
  require_option_value "$@"
  case "$2" in
    --*)
      echo "Missing value for $option." >&2
      usage >&2
      exit 2
      ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      require_non_option_value "$@"
      SPARK_PREFIX="$2"; shift 2 ;;
    --source)
      require_non_option_value "$@"
      SPARK_CLI_SOURCE="$2"; shift 2 ;;
    --ref)
      require_non_option_value "$@"
      SPARK_CLI_REF="$2"; SPARK_CLI_REF_USER_SET=1; shift 2 ;;
    --node-version)
      require_non_option_value "$@"
      SPARK_NODE_VERSION="$2"; shift 2 ;;
    --python-version)
      require_non_option_value "$@"
      SPARK_PYTHON_VERSION="$2"; shift 2 ;;
    --uv-version)
      require_non_option_value "$@"
      SPARK_UV_VERSION="$2"; shift 2 ;;
    --managed-node)
      SPARK_MANAGED_NODE=1; shift ;;
    --bundle)
      require_non_option_value "$@"
      SPARK_BUNDLE="$2"; shift 2 ;;
    --bot-token)
      require_non_option_value "$@"
      SPARK_BOT_TOKEN="$2"; shift 2 ;;
    --admin-telegram-ids)
      require_non_option_value "$@"
      SPARK_ADMIN_TELEGRAM_IDS="$2"; shift 2 ;;
    --llm-provider)
      require_non_option_value "$@"
      SPARK_LLM_PROVIDER="$2"; shift 2 ;;
    --zai-api-key)
      require_non_option_value "$@"
      SPARK_ZAI_API_KEY="$2"; shift 2 ;;
    --openai-api-key)
      require_non_option_value "$@"
      SPARK_OPENAI_API_KEY="$2"; shift 2 ;;
    --anthropic-api-key)
      require_non_option_value "$@"
      SPARK_ANTHROPIC_API_KEY="$2"; shift 2 ;;
    --minimax-api-key)
      require_non_option_value "$@"
      SPARK_MINIMAX_API_KEY="$2"; shift 2 ;;
    --non-interactive-setup)
      SPARK_NON_INTERACTIVE_SETUP=1; shift ;;
    --setup-skip-install-commands)
      SPARK_SETUP_SKIP_INSTALL_COMMANDS=1; shift ;;
    --setup-skip-runtime-check)
      SPARK_SETUP_SKIP_RUNTIME_CHECK=1; shift ;;
    --setup-arg)
      require_option_value "$@"
      extra_setup_args+=("$2"); shift 2 ;;
    --dry-run)
      SPARK_DRY_RUN=1; shift ;;
    --preflight)
      SPARK_PREFLIGHT_ONLY=1; shift ;;
    --yes)
      SPARK_ASSUME_YES=1; shift ;;
    --no-shell-profile)
      SPARK_SHELL_PROFILE=0; shift ;;
    --local-registry)
      require_non_option_value "$@"
      SPARK_LOCAL_REGISTRY="$2"; shift 2 ;;
    --allow-dev-source)
      SPARK_ALLOW_DEV_SOURCE=1; shift ;;
    --upgrade-existing)
      SPARK_EXISTING_MODE=upgrade; shift ;;
    --skip-setup)
      SPARK_SKIP_SETUP=1; shift ;;
    --autostart)
      SPARK_AUTOSTART=1; SPARK_AUTOSTART_USER_SET=1; shift ;;
    --no-autostart)
      SPARK_AUTOSTART=0; SPARK_AUTOSTART_USER_SET=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

SPARK_AUTOSTART_AUTO_DISABLED=0
if [ "$SPARK_AUTOSTART_USER_SET" = "0" ] && { [ "$SPARK_ASSUME_YES" = "1" ] || [ ! -t 0 ]; }; then
  SPARK_AUTOSTART=0
  SPARK_AUTOSTART_AUTO_DISABLED=1
fi
if [ "$SPARK_ASSUME_YES" = "1" ] || [ ! -t 0 ]; then
  SPARK_NON_INTERACTIVE_SETUP=1
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

log() {
  printf '[spark-install] %s\n' "$*"
}

bundle_includes_voice() {
  case "$SPARK_BUNDLE" in
    telegram-voice-starter|*voice*) return 0 ;;
    *) return 1 ;;
  esac
}

autostart_plan_label() {
  if [ "$SPARK_AUTOSTART" = "1" ]; then
    printf 'yes; will mutate login items'
  elif [ "$SPARK_AUTOSTART_AUTO_DISABLED" = "1" ]; then
    printf 'no; auto-disabled for --yes/non-interactive run'
  else
    printf 'no'
  fi
}

installer_run_mode_label() {
  if [ "$SPARK_ASSUME_YES" = "1" ]; then
    printf 'unattended (--yes)'
  elif [ ! -t 0 ]; then
    printf 'unattended (non-TTY stdin)'
  else
    printf 'interactive'
  fi
}

cleanup_secret_files() {
  if [ "${#SPARK_SECRET_FILES[@]}" -gt 0 ]; then
    rm -f "${SPARK_SECRET_FILES[@]}"
    SPARK_SECRET_FILES=()
  fi
}

release_install_lock() {
  if [ -n "$SPARK_INSTALL_LOCK_DIR" ] && [ -d "$SPARK_INSTALL_LOCK_DIR" ]; then
    rmdir "$SPARK_INSTALL_LOCK_DIR" 2>/dev/null || true
    SPARK_INSTALL_LOCK_DIR=""
  fi
}

cleanup_on_exit() {
  cleanup_secret_files
  release_install_lock
}

trap 'cleanup_on_exit' EXIT
trap 'cleanup_on_exit; exit 130' HUP INT TERM

normalize_macos_locale() {
  if [ "$(uname -s)" != "Darwin" ]; then
    return
  fi
  if [ "${LC_ALL:-}" = "C.UTF-8" ]; then
    export LC_ALL="en_US.UTF-8"
  fi
  if [ "${LC_CTYPE:-}" = "C.UTF-8" ]; then
    export LC_CTYPE="en_US.UTF-8"
  fi
  if [ "${LANG:-}" = "C.UTF-8" ]; then
    export LANG="en_US.UTF-8"
  fi
}

normalize_path() {
  local path="$1"
  case "$path" in
    "~") path="$HOME" ;;
    "~/"*) path="$HOME/${path#~/}" ;;
  esac
  case "$path" in
    /*) printf '%s\n' "$path" ;;
    *) printf '%s/%s\n' "$PWD" "$path" ;;
  esac
}

python_is_compatible() {
  "$1" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)
PY
}

find_system_python() {
  local candidate
  for candidate in python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_compatible "$candidate"; then
      SPARK_PYTHON_BIN="$(command -v "$candidate")"
      return 0
    fi
  done
  return 1
}

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    local uv_candidate uv_dir
    uv_candidate="$(command -v uv)"
    uv_dir="$(dirname "$uv_candidate")"
    if [ -x "$uv_dir/uvx" ] || command -v uvx >/dev/null 2>&1; then
      SPARK_UV_BIN="$uv_candidate"
      return 0
    fi
  fi
  if [ -x "$HOME/.local/bin/uv" ]; then
    if [ -x "$HOME/.local/bin/uvx" ] || command -v uvx >/dev/null 2>&1; then
      SPARK_UV_BIN="$HOME/.local/bin/uv"
      return 0
    fi
  fi
  if [ -x "$HOME/.cargo/bin/uv" ]; then
    if [ -x "$HOME/.cargo/bin/uvx" ] || command -v uvx >/dev/null 2>&1; then
      SPARK_UV_BIN="$HOME/.cargo/bin/uv"
      return 0
    fi
  fi
  return 1
}

detect_uv_platform() {
  case "$SPARK_NODE_PLATFORM" in
    darwin-arm64) printf 'aarch64-apple-darwin' ;;
    darwin-x64) printf 'x86_64-apple-darwin' ;;
    linux-arm64) printf 'aarch64-unknown-linux-gnu' ;;
    linux-x64) printf 'x86_64-unknown-linux-gnu' ;;
    *)
      echo "Unsupported uv platform for $SPARK_NODE_PLATFORM" >&2
      exit 1
      ;;
  esac
}

uv_asset_sha256() {
  case "$1" in
    uv-aarch64-apple-darwin.tar.gz) printf '66e37d91f839e12481d7b932a1eccbfe732560f42c1cfb89faddfa2454534ba8' ;;
    uv-x86_64-apple-darwin.tar.gz) printf '0a4bc8fcde4974ea3560be21772aeecab600a6f43fa6e58169f9fa7b3b71d302' ;;
    uv-aarch64-unknown-linux-gnu.tar.gz) printf 'f2ee1cde9aabb4c6e43bd3f341dadaf42189a54e001e521346dc31547310e284' ;;
    uv-x86_64-unknown-linux-gnu.tar.gz) printf '6681d691eb7f9c00ac6a3af54252f7ab29ae72f0c8f95bdc7f9d1401c23ea868' ;;
    *)
      echo "No pinned uv checksum for asset: $1" >&2
      exit 1
      ;;
  esac
}

install_uv() {
  if find_uv; then
    log "Using uv at $SPARK_UV_BIN"
    return
  fi
  need_cmd curl
  need_cmd tar
  if ! has_checksum_tool; then
    echo "Missing required checksum command: sha256sum or shasum" >&2
    exit 1
  fi
  local uv_platform asset expected actual tools_dir uv_dir archive extract_dir uv_bin
  uv_platform="$(detect_uv_platform)"
  asset="uv-$uv_platform.tar.gz"
  expected="$(uv_asset_sha256 "$asset")"
  tools_dir="$SPARK_PREFIX/tools"
  uv_dir="$tools_dir/uv-v$SPARK_UV_VERSION-$uv_platform"
  archive="$tools_dir/$asset"
  extract_dir="$tools_dir/uv-extract-$SPARK_UV_VERSION-$uv_platform"
  uv_bin="$uv_dir/uv"
  if [ -x "$uv_bin" ] && [ -x "$uv_dir/uvx" ]; then
    SPARK_UV_BIN="$uv_bin"
    log "Using managed uv at $SPARK_UV_BIN"
    return
  fi
  if [ -x "$uv_bin" ]; then
    log "Refreshing managed uv because uvx is missing"
    rm -f "$uv_bin" "$uv_dir/uvx"
  fi
  mkdir -p "$tools_dir" "$uv_dir"
  log "Downloading pinned uv $SPARK_UV_VERSION for $uv_platform"
  curl -fsSL "https://github.com/astral-sh/uv/releases/download/$SPARK_UV_VERSION/$asset" -o "$archive"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$expected" "$archive" | sha256sum -c -
  else
    actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
    if [ "$actual" != "$expected" ]; then
      echo "uv archive checksum mismatch for $asset" >&2
      exit 1
    fi
  fi
  rm -rf "$extract_dir"
  mkdir -p "$extract_dir"
  tar -C "$extract_dir" -xzf "$archive"
  local extracted_uv extracted_uvx
  extracted_uv="$(find "$extract_dir" -type f -name uv -perm -111 | head -n 1)"
  extracted_uvx="$(find "$extract_dir" -type f -name uvx -perm -111 | head -n 1)"
  if [ -z "$extracted_uv" ]; then
    echo "uv archive did not contain an executable uv binary" >&2
    exit 1
  fi
  cp "$extracted_uv" "$uv_bin"
  chmod +x "$uv_bin"
  if [ -n "$extracted_uvx" ]; then
    cp "$extracted_uvx" "$uv_dir/uvx"
    chmod +x "$uv_dir/uvx"
  fi
  rm -rf "$extract_dir"
  SPARK_UV_BIN="$uv_bin"
  log "Using managed uv at $SPARK_UV_BIN"
}

ensure_uvx_for_browser_use() {
  install_uv
  local uv_dir uvx_bin
  uv_dir="$(dirname "$SPARK_UV_BIN")"
  uvx_bin="$uv_dir/uvx"
  if [ -x "$uvx_bin" ]; then
    return
  fi
  if PATH="$uv_dir:$PATH" command -v uvx >/dev/null 2>&1; then
    return
  fi
  echo "Pinned uv install did not provide uvx, which browser-use needs to install Chromium." >&2
  exit 1
}

ensure_python_runtime() {
  if find_system_python; then
    log "Using Python runtime: $("$SPARK_PYTHON_BIN" --version 2>/dev/null) at $SPARK_PYTHON_BIN"
    return
  fi
  install_uv
  log "Installing Python $SPARK_PYTHON_VERSION via uv"
  "$SPARK_UV_BIN" python install "$SPARK_PYTHON_VERSION" >/dev/null
  SPARK_PYTHON_BIN="$("$SPARK_UV_BIN" python find "$SPARK_PYTHON_VERSION")"
  if [ -z "$SPARK_PYTHON_BIN" ] || ! python_is_compatible "$SPARK_PYTHON_BIN"; then
    echo "Could not resolve managed Python $SPARK_PYTHON_VERSION via uv." >&2
    exit 1
  fi
  log "Using managed Python runtime: $("$SPARK_PYTHON_BIN" --version 2>/dev/null) at $SPARK_PYTHON_BIN"
}

validate_install_settings() {
  case "$SPARK_PREFIX" in
    ""|"/")
      echo "Refusing unsafe install prefix: $SPARK_PREFIX" >&2
      exit 1
      ;;
  esac

  case "$SPARK_NODE_VERSION" in
    *[!0-9.]*|.*|*..*|*.)
      echo "Unsafe Node version value: $SPARK_NODE_VERSION" >&2
      exit 1
      ;;
  esac

  case "$SPARK_PYTHON_VERSION" in
    *[!0-9.]*|.*|*..*|*.)
      echo "Unsafe Python version value: $SPARK_PYTHON_VERSION" >&2
      exit 1
      ;;
  esac

  case "$SPARK_NODE_PLATFORM" in
    ""|linux-x64|linux-arm64|darwin-x64|darwin-arm64) ;;
    *)
      echo "Unsafe managed Node platform value: $SPARK_NODE_PLATFORM" >&2
      exit 1
      ;;
  esac

  local source_without_git="${SPARK_CLI_SOURCE%.git}"
  if [ "$source_without_git" != "$SPARK_CANONICAL_CLI_SOURCE" ]; then
    if [ "$SPARK_ALLOW_DEV_SOURCE" != "1" ]; then
      echo "Refusing non-canonical Spark CLI source: $SPARK_CLI_SOURCE" >&2
      echo "Use --allow-dev-source only for local development after reviewing the source." >&2
      exit 1
    fi
  fi

  if [ "$SPARK_CLI_REF_USER_SET" = "1" ] && [ -n "$SPARK_CLI_REF" ] && [ "$SPARK_ALLOW_DEV_SOURCE" != "1" ]; then
    echo "Refusing custom git ref without --allow-dev-source: $SPARK_CLI_REF" >&2
    exit 1
  fi

  if [ "$SPARK_CLI_REF_USER_SET" = "0" ] && ! printf '%s' "$SPARK_CLI_REF" | grep -Eq '^([0-9a-f]{40}|spark-cli-public-installer-[0-9]{4}-[0-9]{2}-[0-9]{2}-r[0-9]+)$'; then
    echo "Default Spark CLI ref must be a 40-character commit SHA or Spark public release tag: $SPARK_CLI_REF" >&2
    exit 1
  fi

  if [ -n "$SPARK_LOCAL_REGISTRY" ] && [ "$SPARK_ALLOW_DEV_SOURCE" != "1" ]; then
    echo "Refusing local registry override without --allow-dev-source: $SPARK_LOCAL_REGISTRY" >&2
    exit 1
  fi
}

detect_node_platform() {
  local os_name arch os_id arch_id
  os_name="$(uname -s)"
  arch="$(uname -m)"

  case "$os_name" in
    Linux) os_id="linux" ;;
    Darwin) os_id="darwin" ;;
    *)
      echo "Unsupported OS for install.sh: $os_name. Use install.ps1 on Windows." >&2
      exit 1
      ;;
  esac

  case "$arch" in
    x86_64|amd64) arch_id="x64" ;;
    arm64|aarch64) arch_id="arm64" ;;
    *)
      echo "Unsupported CPU architecture for managed Node: $arch" >&2
      exit 1
      ;;
  esac

  printf '%s-%s\n' "$os_id" "$arch_id"
}

has_checksum_tool() {
  command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1
}

has_existing_install() {
  [ -e "$SPARK_PREFIX/bin/spark" ] || [ -e "$SPARK_PREFIX/tools/spark-cli" ] || [ -e "$SPARK_PREFIX/config" ] || [ -e "$SPARK_PREFIX/state" ]
}

acquire_install_lock() {
  SPARK_INSTALL_LOCK_DIR="$SPARK_PREFIX/.install.lock"
  if ! mkdir "$SPARK_INSTALL_LOCK_DIR" 2>/dev/null; then
    echo "Another Spark install appears to be running: $SPARK_INSTALL_LOCK_DIR" >&2
    echo "If this is stale, remove it after confirming no installer is active." >&2
    exit 1
  fi
}

preflight() {
  log "Preflight checks"
  if find_system_python; then
    log "Python runtime: $("$SPARK_PYTHON_BIN" --version 2>/dev/null) at $SPARK_PYTHON_BIN"
  else
    log "Python runtime: Python >=3.11,<3.14 not found; pinned uv $SPARK_UV_VERSION will be downloaded after confirmation"
  fi
  need_cmd git
  need_cmd curl
  need_cmd tar
  if ! has_checksum_tool; then
    echo "Missing required checksum command: sha256sum or shasum" >&2
    exit 1
  fi
  log "OS/platform: $(uname -s) $(uname -m) -> $SPARK_NODE_PLATFORM"
  log "Install prefix: $SPARK_PREFIX"
  log "Spark CLI source: $SPARK_CLI_SOURCE"
  log "Spark CLI ref: $SPARK_CLI_REF"
  log "Python version: $SPARK_PYTHON_VERSION"
  log "Bundle: $SPARK_BUNDLE"
  log "Autostart: $SPARK_AUTOSTART"
  if has_existing_install; then
    log "Existing Spark install detected at $SPARK_PREFIX"
  else
    log "No existing Spark install detected at $SPARK_PREFIX"
  fi
}

enforce_existing_install_policy() {
  if ! has_existing_install; then
    return
  fi
  if [ "$SPARK_EXISTING_MODE" = "upgrade" ]; then
    log "Existing install update explicitly allowed by --upgrade-existing"
    return
  fi
  cat >&2 <<EOF
Existing Spark install detected at:
  $SPARK_PREFIX

This installer will not overwrite or update an existing install by default.
Choose one:
  - use --upgrade-existing after reviewing local changes and backups
  - use --prefix /tmp/spark-install-test for a disposable test install
  - run the existing Spark repair tools instead of reinstalling
EOF
  exit 1
}

print_plan() {
  cat <<EOF
Spark install preview
Nothing has changed yet.

Spark will:
  1. Install the Spark command
  2. Help you choose how Spark thinks
  3. Connect your Telegram bot
  4. Start Spark so you can chat and build

Details:
  Dry-run safety:     no network and no writes in --dry-run mode
  Prefix:              $SPARK_PREFIX
  Node platform:       $SPARK_NODE_PLATFORM
  Node version:        $SPARK_NODE_VERSION
  Python version:      $SPARK_PYTHON_VERSION
  Python source:       existing Python >=3.11,<3.14 or pinned uv $SPARK_UV_VERSION if needed
  Managed Node forced: $SPARK_MANAGED_NODE
  CLI source:          $SPARK_CLI_SOURCE
  CLI release:         $SPARK_CLI_RELEASE_NAME
  CLI commit:          $SPARK_CLI_REF
  Bundle:              $SPARK_BUNDLE
  Voice included:      $(bundle_includes_voice && printf yes || printf no)
  Run mode:            $(installer_run_mode_label)
  Setup enabled:       $([ "$SPARK_SKIP_SETUP" = "1" ] && printf no || printf yes)
  Default provider:    $([ -n "$SPARK_LLM_PROVIDER" ] && printf '%s for Agent and Mission' "$SPARK_LLM_PROVIDER" || printf 'choose during spark setup')
  Shell profile edit:  $([ "$SPARK_SHELL_PROFILE" = "0" ] && printf no || printf "$SPARK_SHELL_PROFILE")
  Autostart:           $(autostart_plan_label)
  Existing mode:       $SPARK_EXISTING_MODE
  Existing install:    $(has_existing_install && printf detected || printf none)
  Install log:         $SPARK_PREFIX/logs/install.log

Would write:
  $SPARK_PREFIX/tools
  $SPARK_PREFIX/tools/spark-cli
  $SPARK_PREFIX/tools/spark-cli-venv
  $SPARK_PREFIX/bin/spark
  $SPARK_PREFIX/env

Would download if needed:
  Node $SPARK_NODE_VERSION from nodejs.org
  uv $SPARK_UV_VERSION from github.com/astral-sh/uv when Python >=3.11,<3.14 is missing
  Python $SPARK_PYTHON_VERSION via uv when Python >=3.11,<3.14 is missing
  Spark CLI from $SPARK_CLI_SOURCE at $SPARK_CLI_REF

Expected installer network access:
  nodejs.org
  github.com/astral-sh/uv
  github.com/vibeforge1111/spark-cli

Would run:
  python -m venv "$SPARK_PREFIX/tools/spark-cli-venv"
EOF
  if [ "$SPARK_SKIP_SETUP" != "1" ]; then
    local preview_setup_cmd
    if [ "$SPARK_AUTOSTART" = "1" ]; then
      preview_setup_cmd=("$SPARK_PREFIX/bin/spark" setup "$SPARK_BUNDLE" "--start-now" "--autostart")
    else
      preview_setup_cmd=("$SPARK_PREFIX/bin/spark" setup "$SPARK_BUNDLE" "--no-start-now" "--no-autostart")
    fi
    if [ "$SPARK_NON_INTERACTIVE_SETUP" = "1" ]; then
      preview_setup_cmd+=("--non-interactive")
    fi
    if [ "$SPARK_SETUP_SKIP_INSTALL_COMMANDS" = "1" ]; then
      preview_setup_cmd+=("--skip-install-commands")
    fi
    if [ "$SPARK_SETUP_SKIP_RUNTIME_CHECK" = "1" ]; then
      preview_setup_cmd+=("--skip-runtime-check")
    fi
    if [ -n "$SPARK_BOT_TOKEN" ]; then
      preview_setup_cmd+=("--bot-token" "<redacted>")
    fi
    if [ -n "$SPARK_ADMIN_TELEGRAM_IDS" ]; then
      preview_setup_cmd+=("--admin-telegram-ids" "$SPARK_ADMIN_TELEGRAM_IDS")
    fi
    if [ -n "$SPARK_LLM_PROVIDER" ]; then
      preview_setup_cmd+=("--llm-provider" "$SPARK_LLM_PROVIDER")
    fi
    if [ -n "$SPARK_ZAI_API_KEY" ]; then
      preview_setup_cmd+=("--zai-api-key" "<redacted>")
    fi
    if [ -n "$SPARK_OPENAI_API_KEY" ]; then
      preview_setup_cmd+=("--openai-api-key" "<redacted>")
    fi
    if [ -n "$SPARK_ANTHROPIC_API_KEY" ]; then
      preview_setup_cmd+=("--anthropic-api-key" "<redacted>")
    fi
    if [ -n "$SPARK_MINIMAX_API_KEY" ]; then
      preview_setup_cmd+=("--minimax-api-key" "<redacted>")
    fi
    if [ -n "$SPARK_SETUP_ARGS" ]; then
      # shellcheck disable=SC2206
      local setup_words=($SPARK_SETUP_ARGS)
      preview_setup_cmd+=("${setup_words[@]}")
    fi
    if [ "${#extra_setup_args[@]}" -gt 0 ]; then
      preview_setup_cmd+=("${extra_setup_args[@]}")
    fi
    printf '  '
    printf '%q ' "${preview_setup_cmd[@]}"
    printf '\n'
  fi
}

confirm_install() {
  if [ "$SPARK_ASSUME_YES" = "1" ]; then
    return
  fi
  if [ ! -t 0 ]; then
    echo "Interactive confirmation is required before installing." >&2
    echo "Rerun with --yes only after reviewing the dry-run plan." >&2
    exit 1
  fi
  printf '\nReady to install Spark now?\nType yes to continue, or press Ctrl-C to cancel: '
  local answer
  IFS= read -r answer
  case "$answer" in
    yes) ;;
    *)
      echo "Skipped."
      exit 0
      ;;
  esac
}

redact_install_log_stream() {
  local line secret
  while IFS= read -r line; do
    for secret in \
      "$SPARK_BOT_TOKEN" \
      "$SPARK_ZAI_API_KEY" \
      "$SPARK_OPENAI_API_KEY" \
      "$SPARK_ANTHROPIC_API_KEY" \
      "$SPARK_MINIMAX_API_KEY"; do
      if [ -n "$secret" ]; then
        line="${line//$secret/[redacted]}"
      fi
    done
    printf '%s\n' "$line"
  done
}

start_install_log() {
  local log_dir="$SPARK_PREFIX/logs"
  mkdir -p "$log_dir"
  SPARK_INSTALL_LOG="$log_dir/install.log"
  touch "$SPARK_INSTALL_LOG"
  chmod 600 "$SPARK_INSTALL_LOG" 2>/dev/null || true
  log "Writing install log to $SPARK_INSTALL_LOG"
  exec > >(redact_install_log_stream | tee -a "$SPARK_INSTALL_LOG") 2>&1
}

install_node() {
  local required_major actual_version actual_major
  if [ "$SPARK_MANAGED_NODE" != "1" ] && command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    required_major="${SPARK_NODE_VERSION%%.*}"
    actual_version="$(node -v 2>/dev/null || true)"
    actual_major="${actual_version#v}"
    actual_major="${actual_major%%.*}"
    if [ -n "$actual_major" ] && [ "$actual_major" -ge "$required_major" ] 2>/dev/null; then
      SPARK_NODE_BIN_DIR="$(dirname "$(command -v node)")"
      log "Using system Node $actual_version at $SPARK_NODE_BIN_DIR"
      log "Use --managed-node to force Spark's verified managed Node download."
      return
    fi
  fi

  local tools_dir="$SPARK_PREFIX/tools"
  local node_dir="$tools_dir/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM"
  SPARK_NODE_BIN_DIR="$node_dir/bin"
  if [ -x "$node_dir/bin/node" ]; then
    log "Node $SPARK_NODE_VERSION already installed at $node_dir"
    return
  fi

  need_cmd curl
  need_cmd tar
  mkdir -p "$tools_dir"
  local archive="$tools_dir/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM.tar.xz"
  local shasums="$tools_dir/node-v$SPARK_NODE_VERSION-SHASUMS256.txt"
  local url="https://nodejs.org/dist/v$SPARK_NODE_VERSION/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM.tar.xz"
  local shasums_url="https://nodejs.org/dist/v$SPARK_NODE_VERSION/SHASUMS256.txt"
  log "Downloading Node $SPARK_NODE_VERSION for $SPARK_NODE_PLATFORM"
  curl -fsSL "$url" -o "$archive"
  curl -fsSL "$shasums_url" -o "$shasums"
  verify_node_archive "$archive" "$shasums"
  tar -C "$tools_dir" -xf "$archive"
}

verify_node_archive() {
  local archive="$1"
  local shasums="$2"
  local archive_name
  archive_name="$(basename "$archive")"
  local expected
  expected="$(awk -v name="$archive_name" '$2 == name { print $1 }' "$shasums")"
  if [ -z "$expected" ]; then
    echo "Could not find $archive_name in Node SHASUMS256.txt" >&2
    exit 1
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$expected" "$archive" | sha256sum -c -
  elif command -v shasum >/dev/null 2>&1; then
    local actual
    actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
    if [ "$actual" != "$expected" ]; then
      echo "Node archive checksum mismatch for $archive_name" >&2
      exit 1
    fi
  else
    echo "Missing sha256sum or shasum for Node archive verification" >&2
    exit 1
  fi
}

checkout_cli_ref() {
  local target="$1"
  if git -C "$target" checkout "$SPARK_CLI_REF" >/dev/null 2>&1; then
    return
  fi
  if git -C "$target" fetch --depth=1 origin "$SPARK_CLI_REF" >/dev/null 2>&1; then
    git -C "$target" checkout FETCH_HEAD
    return
  fi
  if printf '%s' "$SPARK_CLI_REF" | grep -Eq '^[0-9a-f]{40}$'; then
    if [ "$(git -C "$target" rev-parse --is-shallow-repository 2>/dev/null || printf false)" = "true" ]; then
      git -C "$target" fetch --unshallow origin
    else
      git -C "$target" fetch origin
    fi
    git -C "$target" checkout "$SPARK_CLI_REF"
    return
  fi
  git -C "$target" fetch --depth=1 origin "refs/tags/$SPARK_CLI_REF:refs/tags/$SPARK_CLI_REF"
  git -C "$target" checkout "$SPARK_CLI_REF"
}

checkout_cli() {
  local target="$SPARK_PREFIX/tools/spark-cli"
  mkdir -p "$SPARK_PREFIX/tools"
  if [ -d "$SPARK_CLI_SOURCE" ]; then
    log "Copying spark-cli from local path $SPARK_CLI_SOURCE"
    rm -rf "$target"
    mkdir -p "$target"
    (cd "$SPARK_CLI_SOURCE" && tar --exclude=.git --exclude=.venv --exclude=.pytest_cache --exclude=__pycache__ -cf - .) | tar -C "$target" -xf -
    return
  fi

  need_cmd git
  if [ -d "$target/.git" ]; then
    log "Updating existing spark-cli checkout"
  else
    log "Cloning spark-cli from $SPARK_CLI_SOURCE"
    rm -rf "$target"
    if printf '%s' "$SPARK_CLI_REF" | grep -Eq '^[0-9a-f]{40}$'; then
      git clone "$SPARK_CLI_SOURCE" "$target"
    else
      git clone --depth=1 "$SPARK_CLI_SOURCE" "$target"
    fi
  fi
  checkout_cli_ref "$target"
}

install_cli_venv() {
  local cli_dir="$SPARK_PREFIX/tools/spark-cli"
  local venv_dir="$SPARK_PREFIX/tools/spark-cli-venv"
  ensure_uvx_for_browser_use
  local uv_dir
  uv_dir="$(dirname "$SPARK_UV_BIN")"
  log "Creating Spark CLI virtualenv"
  "$SPARK_PYTHON_BIN" -m venv "$venv_dir"
  log "Upgrading pip in Spark CLI virtualenv"
  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
  log "Installing Spark CLI package with browser-use support"
  "$venv_dir/bin/python" -m pip install -e "$cli_dir[browser-use]"
  log "Installing browser-use Chromium dependency"
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PATH="$venv_dir/bin:$uv_dir:$PATH" "$venv_dir/bin/browser-use" install >/dev/null
}

write_wrapper() {
  local bin_dir="$SPARK_PREFIX/bin"
  local wrapper="$bin_dir/spark"
  local env_file="$SPARK_PREFIX/env"
  mkdir -p "$bin_dir"
  cat > "$wrapper" <<EOF
#!/usr/bin/env bash
export SPARK_HOME="$SPARK_PREFIX"
export PATH="$SPARK_NODE_BIN_DIR:\$PATH"
exec "$SPARK_PREFIX/tools/spark-cli-venv/bin/python" -m spark_cli.cli "\$@"
EOF
  chmod +x "$wrapper"
  cat > "$env_file" <<EOF
export SPARK_HOME="$SPARK_PREFIX"
export PATH="$SPARK_PREFIX/bin:$SPARK_NODE_BIN_DIR:\$PATH"
EOF
  log "Wrote wrapper $wrapper"
  log "Wrote shell env helper $env_file"
}

verify_install_layout() {
  local wrapper="$SPARK_PREFIX/bin/spark"
  local env_file="$SPARK_PREFIX/env"
  local cli_dir="$SPARK_PREFIX/tools/spark-cli"
  local python_bin="$SPARK_PREFIX/tools/spark-cli-venv/bin/python"

  log "Verifying install layout"
  if [ ! -d "$SPARK_PREFIX" ]; then
    echo "Install prefix does not exist after install: $SPARK_PREFIX" >&2
    exit 1
  fi
  if [ ! -d "$cli_dir" ]; then
    echo "Spark CLI checkout is missing after install: $cli_dir" >&2
    exit 1
  fi
  if [ ! -x "$python_bin" ]; then
    echo "Spark CLI Python runtime is missing or not executable: $python_bin" >&2
    exit 1
  fi
  if [ ! -x "$wrapper" ]; then
    echo "Spark wrapper is missing or not executable: $wrapper" >&2
    exit 1
  fi
  if [ ! -f "$env_file" ]; then
    echo "Spark shell env helper is missing after install: $env_file" >&2
    exit 1
  fi
  if ! grep -F "SPARK_HOME=\"$SPARK_PREFIX\"" "$wrapper" >/dev/null 2>&1; then
    echo "Spark wrapper does not reference the resolved install prefix: $SPARK_PREFIX" >&2
    exit 1
  fi
  if ! grep -F "$python_bin" "$wrapper" >/dev/null 2>&1; then
    echo "Spark wrapper does not reference the installed Python runtime: $python_bin" >&2
    exit 1
  fi
  log "Install layout verified"
}

write_shell_profile_hook() {
  if [ "$SPARK_SHELL_PROFILE" = "0" ]; then
    log "Skipping shell profile update"
    return
  fi

  local default_prefix
  default_prefix="$(normalize_path "$HOME/.spark")"
  if [ "$SPARK_SHELL_PROFILE" = "auto" ] && [ "$SPARK_PREFIX" != "$default_prefix" ]; then
    log "Skipping shell profile update for non-default prefix $SPARK_PREFIX"
    return
  fi

  local profile=""
  local shell_name
  shell_name="$(basename "${SHELL:-}")"
  case "$shell_name" in
    zsh)
      profile="$HOME/.zshrc"
      ;;
    bash)
      if [ "$(uname -s)" = "Darwin" ]; then
        profile="$HOME/.bash_profile"
      else
        profile="$HOME/.bashrc"
      fi
      ;;
    *)
      profile="$HOME/.profile"
      ;;
  esac

  mkdir -p "$(dirname "$profile")"
  touch "$profile"
  if grep -F "$SPARK_PREFIX/env" "$profile" >/dev/null 2>&1; then
    log "Shell profile already sources $SPARK_PREFIX/env"
    return
  fi
  if [ "$SPARK_PREFIX" = "$default_prefix" ] && grep -F '$HOME/.spark/env' "$profile" >/dev/null 2>&1; then
    log "Shell profile already sources $SPARK_PREFIX/env"
    return
  fi

  cat >> "$profile" <<EOF

# Spark CLI
[ -f "$SPARK_PREFIX/env" ] && source "$SPARK_PREFIX/env"
EOF
  log "Added Spark CLI to shell profile $profile"
}

run_setup() {
  if [ "$SPARK_SKIP_SETUP" = "1" ]; then
    log "Skipping spark setup"
    return
  fi

  local cli_dir="$SPARK_PREFIX/tools/spark-cli"
  if [ -n "$SPARK_LOCAL_REGISTRY" ]; then
    log "Using registry override $SPARK_LOCAL_REGISTRY"
    cp "$SPARK_LOCAL_REGISTRY" "$cli_dir/registry.json"
  fi

  local spark_setup_cmd=("$SPARK_PREFIX/bin/spark" setup "$SPARK_BUNDLE")
  if [ "$SPARK_AUTOSTART" = "1" ]; then
    spark_setup_cmd+=("--start-now" "--autostart")
  else
    spark_setup_cmd+=("--no-start-now" "--no-autostart")
  fi
  local spark_secret_ref_value=""
  spark_secret_ref() {
    local value="$1"
    local secret_file
    secret_file="$(mktemp "${TMPDIR:-/tmp}/spark-secret.XXXXXX")"
    chmod 600 "$secret_file"
    printf '%s' "$value" > "$secret_file"
    SPARK_SECRET_FILES+=("$secret_file")
    spark_secret_ref_value="@file:$secret_file"
  }
  if [ "$SPARK_NON_INTERACTIVE_SETUP" = "1" ]; then
    spark_setup_cmd+=("--non-interactive")
  fi
  if [ "$SPARK_SETUP_SKIP_INSTALL_COMMANDS" = "1" ]; then
    spark_setup_cmd+=("--skip-install-commands")
  fi
  if [ "$SPARK_SETUP_SKIP_RUNTIME_CHECK" = "1" ]; then
    spark_setup_cmd+=("--skip-runtime-check")
  fi
  if [ -n "$SPARK_BOT_TOKEN" ]; then
    spark_secret_ref "$SPARK_BOT_TOKEN"
    spark_setup_cmd+=("--bot-token" "$spark_secret_ref_value")
  fi
  if [ -n "$SPARK_ADMIN_TELEGRAM_IDS" ]; then
    spark_setup_cmd+=("--admin-telegram-ids" "$SPARK_ADMIN_TELEGRAM_IDS")
  fi
  if [ -n "$SPARK_LLM_PROVIDER" ]; then
    spark_setup_cmd+=("--llm-provider" "$SPARK_LLM_PROVIDER")
  fi
  if [ -n "$SPARK_ZAI_API_KEY" ]; then
    spark_secret_ref "$SPARK_ZAI_API_KEY"
    spark_setup_cmd+=("--zai-api-key" "$spark_secret_ref_value")
  fi
  if [ -n "$SPARK_OPENAI_API_KEY" ]; then
    spark_secret_ref "$SPARK_OPENAI_API_KEY"
    spark_setup_cmd+=("--openai-api-key" "$spark_secret_ref_value")
  fi
  if [ -n "$SPARK_ANTHROPIC_API_KEY" ]; then
    spark_secret_ref "$SPARK_ANTHROPIC_API_KEY"
    spark_setup_cmd+=("--anthropic-api-key" "$spark_secret_ref_value")
  fi
  if [ -n "$SPARK_MINIMAX_API_KEY" ]; then
    spark_secret_ref "$SPARK_MINIMAX_API_KEY"
    spark_setup_cmd+=("--minimax-api-key" "$spark_secret_ref_value")
  fi
  if [ -n "$SPARK_SETUP_ARGS" ]; then
    # shellcheck disable=SC2206
    local setup_words=($SPARK_SETUP_ARGS)
    spark_setup_cmd+=("${setup_words[@]}")
  fi
  if [ "${#extra_setup_args[@]}" -gt 0 ]; then
    spark_setup_cmd+=("${extra_setup_args[@]}")
  fi
  log "Running spark setup $SPARK_BUNDLE"
  local setup_exit=0
  local previous_setup_optional="${SPARK_SETUP_OPTIONAL_ON_UPGRADE-}"
  local had_setup_optional=0
  if [ "${SPARK_SETUP_OPTIONAL_ON_UPGRADE+x}" = "x" ]; then
    had_setup_optional=1
  fi
  if [ "$SPARK_EXISTING_MODE" = "upgrade" ]; then
    export SPARK_SETUP_OPTIONAL_ON_UPGRADE=1
  fi
  "${spark_setup_cmd[@]}" || setup_exit=$?
  if [ "$had_setup_optional" = "1" ]; then
    export SPARK_SETUP_OPTIONAL_ON_UPGRADE="$previous_setup_optional"
  else
    unset SPARK_SETUP_OPTIONAL_ON_UPGRADE
  fi
  cleanup_secret_files
  return "$setup_exit"
}

run_autostart() {
  if [ "$SPARK_SKIP_SETUP" = "1" ]; then
    return
  fi
  log "Spark startup was handled by setup"
}

setup_refresh_paused() {
  [ -f "$SPARK_PREFIX/state/setup.pending.json" ] &&
    grep -F '"event": "setup_refresh_paused"' "$SPARK_PREFIX/state/setup.pending.json" >/dev/null 2>&1
}

print_install_outcome() {
  local setup_line runtime_line telegram_line
  if [ "$SPARK_SKIP_SETUP" = "1" ]; then
    setup_line="[SKIP] Setup: skipped by request"
    runtime_line="[MANUAL] Runtime: start after setup"
    telegram_line="[VERIFY] Telegram: run spark verify --onboarding after setup"
  elif setup_refresh_paused; then
    setup_line="[PAUSED] Setup refresh: secrets need a secure backend before Spark rewrites them"
    runtime_line="[OK] Existing runtime: can keep running with the current setup"
    telegram_line="[VERIFY] Telegram: run spark verify --onboarding"
  elif [ -f "$SPARK_PREFIX/state/setup.pending.json" ]; then
    setup_line="[PAUSED] Setup: run spark doctor"
    runtime_line="[MANUAL] Runtime: resume setup before changing secrets"
    telegram_line="[VERIFY] Telegram: run spark verify --onboarding after setup resumes"
  else
    setup_line="[OK] Setup: configured"
    if [ "$SPARK_AUTOSTART" = "1" ]; then
      runtime_line="[STARTED] Runtime: setup handled start/autostart"
    else
      runtime_line="[MANUAL] Runtime: start after setup"
    fi
    telegram_line="[VERIFY] Telegram: run spark verify --onboarding"
  fi
  cat <<EOF

Install outcome:
  [OK] CLI upgrade: complete
  $setup_line
  $runtime_line
  $telegram_line
EOF
}

main() {
  normalize_macos_locale
  SPARK_PREFIX="$(normalize_path "$SPARK_PREFIX")"
  if [ -z "$SPARK_NODE_PLATFORM" ]; then
    SPARK_NODE_PLATFORM="$(detect_node_platform)"
  fi
  validate_install_settings
  if [ "$SPARK_DRY_RUN" = "1" ]; then
    print_plan
    exit 0
  fi
  print_plan
  preflight
  if [ "$SPARK_PREFLIGHT_ONLY" = "1" ]; then
    log "Preflight complete."
    exit 0
  fi
  enforce_existing_install_policy
  confirm_install
  mkdir -p "$SPARK_PREFIX"
  ensure_python_runtime
  start_install_log
  acquire_install_lock
  install_node
  export PATH="$SPARK_NODE_BIN_DIR:$PATH"
  log "Node runtime: $(node -v)"
  checkout_cli
  install_cli_venv
  write_wrapper
  verify_install_layout
  write_shell_profile_hook
  run_setup
  run_autostart
  log "Done."
  cat <<EOF

Spark command:
  $SPARK_PREFIX/bin/spark --help
  $SPARK_PREFIX/bin/spark guide
  $SPARK_PREFIX/bin/spark providers list

To use \`spark\` by name in this terminal:
  source "$SPARK_PREFIX/env"

For default installs, the installer also adds this line to your shell profile:
  source "$SPARK_PREFIX/env"

Install log:
  $SPARK_INSTALL_LOG
EOF
  print_install_outcome
  if [ "$SPARK_SKIP_SETUP" = "1" ]; then
    cat <<EOF

Setup was skipped.
Next:
  $SPARK_PREFIX/bin/spark setup $SPARK_BUNDLE

After setup succeeds:
  $SPARK_PREFIX/bin/spark verify --onboarding
EOF
  else
    cat <<EOF

Operational checks:
  $SPARK_PREFIX/bin/spark live start
  $SPARK_PREFIX/bin/spark live status
  $SPARK_PREFIX/bin/spark providers status
  $SPARK_PREFIX/bin/spark providers test --role chat
  $SPARK_PREFIX/bin/spark verify --onboarding
  $SPARK_PREFIX/bin/spark autostart status
  $SPARK_PREFIX/bin/spark fix autostart

$(if [ "$SPARK_AUTOSTART" = "1" ]; then
    cat <<AUTOSTART_ON
Spark autostart is enabled by default so Spark comes back after login.
To disable it later:
  $SPARK_PREFIX/bin/spark autostart off
AUTOSTART_ON
  else
    cat <<AUTOSTART_OFF
Autostart was not installed for this run.
To enable it later:
  $SPARK_PREFIX/bin/spark autostart on telegram-starter --now
AUTOSTART_OFF
  fi)
EOF
    cat <<EOF

Start chatting and building:
  1. Open your Spark bot in Telegram
  2. If Telegram asks for a start code, send /start
  3. For first builds, choose Level 4 so Mission Control can inspect and build in local workspaces
  4. Use a lower level only when you want chat or public research without local files
  5. Send a normal message, or try: /run say exactly OK
  6. When you are ready, ask Spark how it can improve for your workflows

If Telegram is quiet or memory is not responding:
  $SPARK_PREFIX/bin/spark fix telegram
  $SPARK_PREFIX/bin/spark logs spark-telegram-bot

If Mission Control, Kanban, Canvas, or preview links are not responding:
  $SPARK_PREFIX/bin/spark fix spawner
  $SPARK_PREFIX/bin/spark logs spawner-ui --lines 80
EOF
  fi
}

main "$@"
