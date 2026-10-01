FROM python:3.12-slim

ARG UID=10001
ARG GID=10001

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl jq ripgrep build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid ${GID} workshop \
    && useradd --uid ${UID} --gid ${GID} --create-home --shell /bin/bash workshop

WORKDIR /opt/ai-workshop
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER workshop
WORKDIR /workspace
ENTRYPOINT ["ai-workshop"]
