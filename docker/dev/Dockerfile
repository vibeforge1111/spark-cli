FROM python:3.14-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/spark-cli

COPY pyproject.toml README.md LICENSE registry.json ./
COPY schemas ./schemas
COPY scripts ./scripts
COPY src ./src
COPY tests ./tests

RUN python -m pip install --upgrade pip \
    && python -m pip install -e . pytest

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SPARK_HOME=/tmp/spark-home

CMD ["bash", "-lc", "python -m pytest tests/test_cli.py -q && python -m spark_cli.cli verify --installers"]
