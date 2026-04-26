#!/usr/bin/env bash
set -euo pipefail

SPARK_PREFIX="${SPARK_PREFIX:-$HOME/.spark}"
SPARK_CLI_SOURCE="${SPARK_CLI_SOURCE:-https://github.com/vibeforge1111/spark-cli}"
SPARK_DEFAULT_CLI_REF="spark-cli-launch-2026-04-26"
SPARK_CLI_REF_USER_SET=0
if [ -n "${SPARK_CLI_REF:-}" ]; then
  SPARK_CLI_REF_USER_SET=1
fi
SPARK_CLI_REF="${SPARK_CLI_REF:-$SPARK_DEFAULT_CLI_REF}"
SPARK_NODE_VERSION="${SPARK_NODE_VERSION:-22.18.0}"
SPARK_SKIP_SETUP="${SPARK_SKIP_SETUP:-0}"
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
SPARK_CANONICAL_CLI_SOURCE="https://github.com/vibeforge1111/spark-cli"
SPARK_ALLOW_DEV_SOURCE="${SPARK_ALLOW_DEV_SOURCE:-0}"
SPARK_SECRET_FILES=()
trap 'cleanup_secret_files' EXIT HUP INT TERM

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Install Spark CLI into a local prefix without depending on system Node.

Options:
  --prefix DIR              Install prefix (default: ~/.spark)
  --source URL_OR_PATH      developer override for spark-cli source; requires --allow-dev-source
  --ref REF                 developer override for git ref; requires --allow-dev-source
  --node-version VERSION    Managed Node version (default: 22.18.0)
  --managed-node            Force Spark's verified managed Node download even if system Node is good
  --bundle NAME             Bundle for setup (default: telegram-starter)
  --bot-token TOKEN         Telegram BotFather token passed to setup
  --admin-telegram-ids IDS  Comma-separated Telegram admin IDs passed to setup
  --llm-provider PROVIDER   Provider passed to setup: openai, codex, anthropic, zai, minimax, or ollama
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
  --no-shell-profile        Do not add Spark to the user's shell profile
  --local-registry PATH     developer registry override; requires --allow-dev-source
  --allow-dev-source        Allow source/ref/local-registry overrides for local development
  --skip-setup              Install CLI only; do not run spark setup
  --no-autostart            Do not install the login autostart hook after setup
  -h, --help                Show this help

Environment mirrors these flags:
  SPARK_PREFIX, SPARK_CLI_SOURCE, SPARK_CLI_REF, SPARK_NODE_VERSION,
  SPARK_BUNDLE, SPARK_SETUP_ARGS, SPARK_LOCAL_REGISTRY, SPARK_SKIP_SETUP,
  SPARK_AUTOSTART, SPARK_ALLOW_DEV_SOURCE, SPARK_MANAGED_NODE,
  SPARK_BOT_TOKEN, SPARK_ADMIN_TELEGRAM_IDS, SPARK_LLM_PROVIDER,
  SPARK_ZAI_API_KEY, SPARK_OPENAI_API_KEY, SPARK_ANTHROPIC_API_KEY,
  SPARK_MINIMAX_API_KEY,
  SPARK_NON_INTERACTIVE_SETUP, SPARK_SETUP_SKIP_INSTALL_COMMANDS,
  SPARK_SETUP_SKIP_RUNTIME_CHECK, SPARK_SHELL_PROFILE,
  SPARK_NODE_PLATFORM.
EOF
}

extra_setup_args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      SPARK_PREFIX="$2"; shift 2 ;;
    --source)
      SPARK_CLI_SOURCE="$2"; shift 2 ;;
    --ref)
      SPARK_CLI_REF="$2"; SPARK_CLI_REF_USER_SET=1; shift 2 ;;
    --node-version)
      SPARK_NODE_VERSION="$2"; shift 2 ;;
    --managed-node)
      SPARK_MANAGED_NODE=1; shift ;;
    --bundle)
      SPARK_BUNDLE="$2"; shift 2 ;;
    --bot-token)
      SPARK_BOT_TOKEN="$2"; shift 2 ;;
    --admin-telegram-ids)
      SPARK_ADMIN_TELEGRAM_IDS="$2"; shift 2 ;;
    --llm-provider)
      SPARK_LLM_PROVIDER="$2"; shift 2 ;;
    --zai-api-key)
      SPARK_ZAI_API_KEY="$2"; shift 2 ;;
    --openai-api-key)
      SPARK_OPENAI_API_KEY="$2"; shift 2 ;;
    --anthropic-api-key)
      SPARK_ANTHROPIC_API_KEY="$2"; shift 2 ;;
    --minimax-api-key)
      SPARK_MINIMAX_API_KEY="$2"; shift 2 ;;
    --non-interactive-setup)
      SPARK_NON_INTERACTIVE_SETUP=1; shift ;;
    --setup-skip-install-commands)
      SPARK_SETUP_SKIP_INSTALL_COMMANDS=1; shift ;;
    --setup-skip-runtime-check)
      SPARK_SETUP_SKIP_RUNTIME_CHECK=1; shift ;;
    --setup-arg)
      extra_setup_args+=("$2"); shift 2 ;;
    --no-shell-profile)
      SPARK_SHELL_PROFILE=0; shift ;;
    --local-registry)
      SPARK_LOCAL_REGISTRY="$2"; shift 2 ;;
    --allow-dev-source)
      SPARK_ALLOW_DEV_SOURCE=1; shift ;;
    --skip-setup)
      SPARK_SKIP_SETUP=1; shift ;;
    --no-autostart)
      SPARK_AUTOSTART=0; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

log() {
  printf '[spark-install] %s\n' "$*"
}

cleanup_secret_files() {
  if [ "${#SPARK_SECRET_FILES[@]}" -gt 0 ]; then
    rm -f "${SPARK_SECRET_FILES[@]}"
    SPARK_SECRET_FILES=()
  fi
}

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
  python3 - "$1" <<'PY'
import os, sys
print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
}

require_python_version() {
  python3 - <<'PY'
import sys

required = (3, 11)
if sys.version_info < required:
    version = ".".join(str(part) for part in sys.version_info[:3])
    print(
        f"Python >= {required[0]}.{required[1]} is required for Spark. Found Python {version}. "
        "Install a newer python3 and rerun the installer.",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
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
    git clone --depth=1 "$SPARK_CLI_SOURCE" "$target"
  fi
  checkout_cli_ref "$target"
}

install_cli_venv() {
  local cli_dir="$SPARK_PREFIX/tools/spark-cli"
  local venv_dir="$SPARK_PREFIX/tools/spark-cli-venv"
  log "Creating Spark CLI virtualenv"
  python3 -m venv "$venv_dir"
  log "Upgrading pip in Spark CLI virtualenv"
  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
  log "Installing Spark CLI package"
  "$venv_dir/bin/python" -m pip install -e "$cli_dir"
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
    cat <<EOF

Next:
  $SPARK_PREFIX/bin/spark setup $SPARK_BUNDLE
EOF
    return
  fi

  local cli_dir="$SPARK_PREFIX/tools/spark-cli"
  if [ -n "$SPARK_LOCAL_REGISTRY" ]; then
    log "Using registry override $SPARK_LOCAL_REGISTRY"
    cp "$SPARK_LOCAL_REGISTRY" "$cli_dir/registry.json"
  fi

  local spark_setup_cmd=("$SPARK_PREFIX/bin/spark" setup "$SPARK_BUNDLE")
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
  "${spark_setup_cmd[@]}" || setup_exit=$?
  cleanup_secret_files
  return "$setup_exit"
}

run_autostart() {
  if [ "$SPARK_SKIP_SETUP" = "1" ]; then
    return
  fi
  if [ "$SPARK_AUTOSTART" != "1" ]; then
    log "Skipping Spark autostart"
    cat <<EOF

To start Spark manually:
  $SPARK_PREFIX/bin/spark start $SPARK_BUNDLE
EOF
    return
  fi

  log "Installing Spark autostart"
  if ! "$SPARK_PREFIX/bin/spark" autostart install "$SPARK_BUNDLE" --now; then
    cat <<EOF

Spark autostart could not be enabled automatically.
Manual fallback for this session:
  $SPARK_PREFIX/bin/spark start $SPARK_BUNDLE

To try autostart again:
  $SPARK_PREFIX/bin/spark autostart install --now
EOF
  fi
}

main() {
  need_cmd python3
  require_python_version
  normalize_macos_locale
  SPARK_PREFIX="$(normalize_path "$SPARK_PREFIX")"
  if [ -z "$SPARK_NODE_PLATFORM" ]; then
    SPARK_NODE_PLATFORM="$(detect_node_platform)"
  fi
  validate_install_settings
  mkdir -p "$SPARK_PREFIX"
  install_node
  export PATH="$SPARK_NODE_BIN_DIR:$PATH"
  log "Node runtime: $(node -v)"
  checkout_cli
  install_cli_venv
  write_wrapper
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

Operational checks:
  $SPARK_PREFIX/bin/spark status
  $SPARK_PREFIX/bin/spark providers status
  $SPARK_PREFIX/bin/spark verify --onboarding
  $SPARK_PREFIX/bin/spark autostart status

Finish in Telegram:
  1. Open your Spark bot and send /start
  2. Pick an access level when Spark asks. Most people should use /access 3
  3. Send /diagnose
  4. Try memory: /remember I like concise warm replies
  5. Try a tiny build: /run say exactly OK

If Telegram is quiet or memory is not responding:
  $SPARK_PREFIX/bin/spark fix telegram
  $SPARK_PREFIX/bin/spark logs spark-telegram-bot
EOF
}

main "$@"
