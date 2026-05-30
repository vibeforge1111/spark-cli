#!/usr/bin/env bash
set -euo pipefail

image="${SPARK_DOCKER_DEV_IMAGE:-spark-cli-dev:local}"
cmd="${SPARK_DOCKER_DEV_CMD:-python -m pytest tests/test_docker_entrypoint.py -q && spark --help >/tmp/spark-help.txt}"

if [[ "${SPARK_DOCKER_REGISTRY_PINS:-0}" == "1" ]]; then
  cmd="${cmd} && python -m spark_cli.cli verify --registry-pins --json"
fi

if [[ "${SPARK_DOCKER_PROVENANCE:-0}" == "1" ]]; then
  cmd="${cmd} && python -m spark_cli.cli verify --provenance --json"
fi

if [[ "${SPARK_DOCKER_NO_BUILD:-0}" != "1" ]]; then
  docker build -f docker/dev/Dockerfile -t "${image}" .
fi

docker run --rm \
  -e SPARK_HOME=/tmp/spark-home \
  "${image}" \
  bash -lc "${cmd}"
