#!/usr/bin/env bash
set -euo pipefail

SPARK_PREFIX="${SPARK_PREFIX:-$HOME/.spark}"
SPARK_CLI_SOURCE="${SPARK_CLI_SOURCE:-https://github.com/vibeforge1111/spark-cli}"
SPARK_CLI_REF="${SPARK_CLI_REF:-}"
SPARK_NODE_VERSION="${SPARK_NODE_VERSION:-22.18.0}"
SPARK_SKIP_SETUP="${SPARK_SKIP_SETUP:-0}"
SPARK_AUTOSTART="${SPARK_AUTOSTART:-1}"
SPARK_BUNDLE="${SPARK_BUNDLE:-telegram-starter}"
SPARK_SETUP_ARGS="${SPARK_SETUP_ARGS:-}"
SPARK_LOCAL_REGISTRY="${SPARK_LOCAL_REGISTRY:-}"
SPARK_NODE_PLATFORM="${SPARK_NODE_PLATFORM:-}"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Install Spark CLI into a local prefix without depending on system Node.

Options:
  --prefix DIR              Install prefix (default: ~/.spark)
  --source URL_OR_PATH      spark-cli git URL or local path
  --ref REF                 Optional git ref to checkout
  --node-version VERSION    Managed Node version (default: 22.18.0)
  --bundle NAME             Bundle for setup (default: telegram-starter)
  --setup-arg ARG           Extra arg passed to `spark setup`; repeatable
  --local-registry PATH     Copy a registry.json override before setup
  --skip-setup              Install CLI only; do not run spark setup
  --no-autostart            Do not install the login autostart hook after setup
  -h, --help                Show this help

Environment mirrors these flags:
  SPARK_PREFIX, SPARK_CLI_SOURCE, SPARK_CLI_REF, SPARK_NODE_VERSION,
  SPARK_BUNDLE, SPARK_SETUP_ARGS, SPARK_LOCAL_REGISTRY, SPARK_SKIP_SETUP,
  SPARK_AUTOSTART,
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
      SPARK_CLI_REF="$2"; shift 2 ;;
    --node-version)
      SPARK_NODE_VERSION="$2"; shift 2 ;;
    --bundle)
      SPARK_BUNDLE="$2"; shift 2 ;;
    --setup-arg)
      extra_setup_args+=("$2"); shift 2 ;;
    --local-registry)
      SPARK_LOCAL_REGISTRY="$2"; shift 2 ;;
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
  local tools_dir="$SPARK_PREFIX/tools"
  local node_dir="$tools_dir/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM"
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
    git -C "$target" fetch --depth=1 origin "${SPARK_CLI_REF:-HEAD}"
  else
    log "Cloning spark-cli from $SPARK_CLI_SOURCE"
    rm -rf "$target"
    git clone --depth=1 "$SPARK_CLI_SOURCE" "$target"
  fi
  if [ -n "$SPARK_CLI_REF" ]; then
    git -C "$target" checkout "$SPARK_CLI_REF"
  fi
}

install_cli_venv() {
  local cli_dir="$SPARK_PREFIX/tools/spark-cli"
  local venv_dir="$SPARK_PREFIX/tools/spark-cli-venv"
  log "Creating Spark CLI virtualenv"
  python3 -m venv "$venv_dir"
  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
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
export PATH="$SPARK_PREFIX/tools/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM/bin:\$PATH"
exec "$SPARK_PREFIX/tools/spark-cli-venv/bin/python" -m spark_cli.cli "\$@"
EOF
  chmod +x "$wrapper"
  cat > "$env_file" <<EOF
export SPARK_HOME="$SPARK_PREFIX"
export PATH="$SPARK_PREFIX/bin:$SPARK_PREFIX/tools/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM/bin:\$PATH"
EOF
  log "Wrote wrapper $wrapper"
  log "Wrote shell env helper $env_file"
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
  if [ -n "$SPARK_SETUP_ARGS" ]; then
    # shellcheck disable=SC2206
    local setup_words=($SPARK_SETUP_ARGS)
    spark_setup_cmd+=("${setup_words[@]}")
  fi
  if [ "${#extra_setup_args[@]}" -gt 0 ]; then
    spark_setup_cmd+=("${extra_setup_args[@]}")
  fi
  log "Running spark setup $SPARK_BUNDLE"
  "${spark_setup_cmd[@]}"
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
  normalize_macos_locale
  SPARK_PREFIX="$(normalize_path "$SPARK_PREFIX")"
  if [ -z "$SPARK_NODE_PLATFORM" ]; then
    SPARK_NODE_PLATFORM="$(detect_node_platform)"
  fi
  mkdir -p "$SPARK_PREFIX"
  install_node
  export PATH="$SPARK_PREFIX/tools/node-v$SPARK_NODE_VERSION-$SPARK_NODE_PLATFORM/bin:$PATH"
  log "Node runtime: $(node -v)"
  checkout_cli
  install_cli_venv
  write_wrapper
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

To make that permanent, add this line to your shell profile:
  source "$SPARK_PREFIX/env"

Operational checks:
  $SPARK_PREFIX/bin/spark status
  $SPARK_PREFIX/bin/spark providers status
  $SPARK_PREFIX/bin/spark verify
  $SPARK_PREFIX/bin/spark autostart status

If Telegram is quiet or memory is not responding:
  $SPARK_PREFIX/bin/spark fix telegram
  $SPARK_PREFIX/bin/spark logs spark-telegram-bot
EOF
}

main "$@"
