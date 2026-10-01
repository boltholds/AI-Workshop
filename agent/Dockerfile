FROM node:24-bookworm-slim AS node-runtime

FROM python:3.12-slim

ARG UID=10001
ARG GID=10001

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g pnpm@10 \
    && apt-get update \
    && apt-get install -y --no-install-recommends git curl wget jq ripgrep fd-find build-essential ca-certificates \
    && ln -s /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid ${GID} workshop \
    && useradd --uid ${UID} --gid ${GID} --create-home --shell /bin/bash workshop

WORKDIR /opt/ai-workshop
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . uv poetry pytest

USER workshop
WORKDIR /workspace
ENTRYPOINT ["ai-workshop"]
