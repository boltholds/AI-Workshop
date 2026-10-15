# The worker never receives WAI state/credentials or the Docker socket.
FROM rust:1.99-bookworm AS rust-toolchain
FROM eclipse-temurin:21-jdk-noble

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv binutils file ca-certificates build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY --from=rust-toolchain /usr/local/cargo/bin /usr/local/cargo/bin
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir 'fastapi>=0.115,<1' 'uvicorn>=0.35,<1' 'pydantic>=2,<3' \
    && mkdir -p /analysis /workspace/projects /opt/ai-workshop/ghidra_scripts /cargo-cache /cargo-lockfiles /cargo-build \
    && chown 10001:10001 /analysis /cargo-cache /cargo-lockfiles /cargo-build
COPY src/ai_workshop/analysis /opt/ai-workshop/src/ai_workshop/analysis
COPY src/ai_workshop/__init__.py /opt/ai-workshop/src/ai_workshop/__init__.py
COPY analysis/ghidra_scripts /opt/ai-workshop/ghidra_scripts
# Docker COPY preserves source permissions. A hardened root checkout may be 0600/0700;
# grant read/traverse permissions to the unprivileged worker without changing ownership
# or allowing it to modify these application files at runtime.
RUN chmod -R a+rX /opt/ai-workshop
ENV PATH="/opt/venv/bin:/usr/local/cargo/bin:${PATH}" \
    RUSTUP_HOME=/usr/local/rustup \
    PYTHONPATH=/opt/ai-workshop/src \
    PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /workspace/projects
CMD ["python", "-m", "uvicorn", "ai_workshop.analysis.app:load_app", "--factory", "--host", "0.0.0.0", "--port", "8795"]
