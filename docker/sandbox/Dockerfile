FROM python:3.14-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin spark \
    && mkdir -p /workspace/spark-cli /sandbox/home /sandbox/spark-home \
    && chown -R spark:spark /workspace /sandbox

WORKDIR /workspace/spark-cli

COPY --chown=spark:spark pyproject.toml README.md LICENSE registry.json ./
COPY --chown=spark:spark schemas ./schemas
COPY --chown=spark:spark scripts ./scripts
COPY --chown=spark:spark src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

USER spark

ENV HOME=/sandbox/home \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SPARK_HOME=/sandbox/spark-home

ENTRYPOINT ["python", "-m", "spark_cli.cli"]
CMD ["--help"]
