FROM node:22-bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        bubblewrap \
        ca-certificates \
        git \
        gosu \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1001 --create-home --shell /bin/bash spark \
    && mkdir -p /opt/spark-cli /opt/spark-venv /data/spark/codex \
    && chown -R spark:spark /opt/spark-cli /opt/spark-venv /data/spark

WORKDIR /opt/spark-cli

COPY --chown=spark:spark pyproject.toml README.md LICENSE registry.json ./
COPY --chown=spark:spark schemas ./schemas
COPY --chown=spark:spark scripts ./scripts
COPY --chown=spark:spark src ./src
COPY --chown=spark:spark docker/live/entrypoint.sh /usr/local/bin/spark-live-entrypoint

RUN python3 -m venv /opt/spark-venv \
    && /opt/spark-venv/bin/python -m pip install --upgrade pip \
    && /opt/spark-venv/bin/python -m pip install -e . \
    && npm install -g @openai/codex@0.1.2505092 \
    && npm cache clean --force \
    && chown -R spark:spark /opt/spark-cli /opt/spark-venv /data/spark /home/spark \
    && chmod +x /usr/local/bin/spark-live-entrypoint

ENV HOME=/home/spark \
    PATH=/opt/spark-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CODEX_HOME=/data/spark/codex \
    SPARK_HOME=/data/spark \
    SPARK_LIVE_CONTAINER=1 \
    SPARK_STRICT_RUNTIME_PINS=1 \
    SPARK_SPAWNER_HOST=0.0.0.0 \
    SPARK_SPAWNER_PORT=5173

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD spark live status >/dev/null || exit 1

USER root
ENTRYPOINT ["spark-live-entrypoint"]
