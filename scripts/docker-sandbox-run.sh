#!/usr/bin/env bash
set -euo pipefail

image="${SPARK_DOCKER_SANDBOX_IMAGE:-spark-cli-sandbox:local}"
network="${SPARK_DOCKER_SANDBOX_NETWORK:-none}"

if [[ "${SPARK_DOCKER_NO_BUILD:-0}" != "1" ]]; then
  docker build -f docker/sandbox/Dockerfile -t "${image}" .
fi

if [[ "$#" -eq 0 ]]; then
  set -- --help
fi

docker run --rm \
  --user 1000:1000 \
  --network "${network}" \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 128 \
  --memory 512m \
  --memory-swap 512m \
  --cpus 1.0 \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --tmpfs /sandbox:rw,noexec,nosuid,uid=1000,gid=1000,size=512m \
  "${image}" \
  "$@"
