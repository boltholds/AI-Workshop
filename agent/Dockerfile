FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential curl fd-find git jq nodejs npm ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g pnpm

RUN useradd --create-home --uid 1000 --shell /bin/bash workshop
WORKDIR /opt/ai-workshop

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . uv poetry

COPY agent/entrypoint.sh /usr/local/bin/ai-workshop-agent
RUN chmod +x /usr/local/bin/ai-workshop-agent

USER workshop
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/ai-workshop-agent"]
