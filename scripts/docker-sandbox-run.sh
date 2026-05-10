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
  --network "${network}" \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --tmpfs /sandbox:rw,nosuid,uid=1000,gid=1000,size=512m \
  "${image}" \
  "$@"
