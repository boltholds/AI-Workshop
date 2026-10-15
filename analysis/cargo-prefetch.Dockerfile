# Networked, one-shot Cargo dependency preparation. No WAI tokens or Docker socket.
FROM rust:1.90-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace/projects /cargo-cache /cargo-lockfiles \
    && chown -R 10001:10001 /cargo-cache /cargo-lockfiles
COPY src/ai_workshop/analysis /opt/ai-workshop/src/ai_workshop/analysis
COPY src/ai_workshop/__init__.py /opt/ai-workshop/src/ai_workshop/__init__.py
RUN chmod -R a+rX /opt/ai-workshop

ENV PYTHONPATH=/opt/ai-workshop/src \
    PYTHONDONTWRITEBYTECODE=1 \
    CARGO_HOME=/cargo-cache \
    RUSTUP_HOME=/usr/local/rustup
USER 10001:10001
WORKDIR /workspace/projects
ENTRYPOINT ["python3", "-m", "ai_workshop.analysis.cargo_prefetch"]
