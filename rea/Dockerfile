FROM node:24-bookworm-slim AS rea-runtime
WORKDIR /opt/rea
COPY rea/package.json rea/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

FROM eclipse-temurin:21-jdk-noble
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates binutils file \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir 'mcp==2.3.0' 'uvicorn>=0.35,<1' \
    && mkdir -p /data /workspace/target /run/rea \
    && chown 10001:10001 /data /run/rea
COPY --from=rea-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=rea-runtime /opt/rea /opt/rea
COPY src/ai_workshop/__init__.py /opt/ai-workshop/src/ai_workshop/__init__.py
COPY src/ai_workshop/rea /opt/ai-workshop/src/ai_workshop/rea
RUN chmod -R a+rX /opt/ai-workshop /opt/rea
ENV PATH="/opt/venv/bin:/opt/rea/node_modules/.bin:${PATH}" \
    PYTHONPATH=/opt/ai-workshop/src \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/data \
    GHIDRA_INSTALL_DIR=/opt/ghidra \
    REA_ANALYSIS_PROVIDER=ghidra
USER 10001:10001
WORKDIR /data
CMD ["python", "-m", "uvicorn", "ai_workshop.rea.bridge:load_app", "--factory", "--uds", "/run/rea/mcp.sock"]
