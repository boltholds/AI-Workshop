# Offline Cargo tests from AI Workshop MCP

WAI deliberately separates dependency fetching from compilation. The
`cargo-prefetch-api` sidecar has registry egress and **only** prepares Cargo
metadata, dependencies and a checksum-verified lockfile in named volumes.
The analysis worker has no egress, mounts those volumes read-only and runs
`cargo test --offline --locked` in a disposable project snapshot.

Neither service has a host Docker socket, WAI state, SSH keys or GitHub
credentials. The original Git checkout, index, source code and any existing
`Cargo.lock` stay untouched by prefetch and offline testing.

## Install the opt-in MCP prefetch service

This change introduces an opt-in `cargo_prefetch(project_id,
manifest_path="Cargo.toml")` MCP tool. It is available only when the
networked sidecar, offline worker and project-file tools are configured.

After reviewing and deploying this change to WAI on the server, create a
**dedicated** token in `deploy/server/.env` (do not send it through chat).
For example, on the WAI server:

```bash
cd /opt/ai-workshop
printf 'AI_WORKSHOP_CARGO_PREFETCH_TOKEN=%s\n' "$(openssl rand -hex 32)" \
  >> deploy/server/.env
```

Use the installed overlays. Omit `compose.rea.yaml` only when REA is absent.

```bash
C=(
  docker compose --env-file deploy/server/.env
  -f deploy/server/compose.yaml
  -f deploy/server/compose.analysis.yaml
  -f deploy/server/compose.rea.yaml
)
"${C[@]}" config --quiet
"${C[@]}" build gateway analysis-worker cargo-prefetch-api
"${C[@]}" up -d --no-deps --no-build --wait --wait-timeout 120 \
  cargo-prefetch-api analysis-worker gateway
"${C[@]}" ps gateway analysis-worker cargo-prefetch-api
```

`cargo-prefetch-api` and the gateway communicate on an internal-only
`cargo-control` Docker network. The sidecar also has outbound registry
access via `cargo-egress`, but **no published TCP port**. It authenticates
each request using a separate bearer token (constant-time comparison).
The service is unprivileged, read-only outside scratch and Cargo volumes,
has bounded memory/PIDs/CPU, and permits one preparation request at a time.

The gateway validates the registered project ID before forwarding and
exposes no registry credentials, arbitrary subprocess argv, Docker build,
shell or Docker socket controls through this MCP tool. The sidecar omits
sensitive paths, registry output and credentials from MCP responses.

## End-to-end from ChatGPT

Once deployed, register/clone a reviewed Rust project in WAI. For the
isolated pinned RustSolid project created in this conversation:

```text
cargo_prefetch(
    project_id="rustsolid-geometry-ci",
    manifest_path="Cargo.toml"
)
cargo_test(
    project_id="rustsolid-geometry-ci",
    manifest_path="Cargo.toml"
)
```

Run prefetch only when the manifest, dependency lockfile or Cargo config
changes. A fingerprint detects those changes; editing a source file does
not require another dependency fetch.

For nested manifests use `manifest_path="crates/core/Cargo.toml"`.
A missing or changed fingerprint fails closed in the offline worker.
A manifest/lockfile with untrusted remote dependencies must not be
prefetched; the sidecar has deliberate network access.

The previous one-shot manual prefetch command remains available for
emergency operator maintenance:

```bash
"${C[@]}" --profile cargo run --rm --no-deps cargo-prefetch rustsolid
```

It is not required for routine MCP-driven builds.

## Limitations and troubleshooting

`cargo_test` runs the repository's native test suite; it is **not** a
general Docker image builder. GHCR image builds remain in the separately
hardened GitHub Actions pipeline. The prefetch network does not allow
GitHub authentication or private repository cloning by itself; WAI Git
credentials must independently have read access to any private projects.

An explicit token mismatch results in `CARGO_PREFETCH_UNAUTHORIZED`.
Concurrent requests receive `CARGO_PREFETCH_BUSY`. Connection failures
produce `CARGO_PREFETCH_UNAVAILABLE` and networked Cargo errors produce
`CARGO_PREFETCH_FAILED` without sending raw stderr to the agent.
Inspect restricted operator logs if more details are required.

To run tests, see:

```bash
uv run pytest -q tests/unit/analysis/test_cargo_cache.py \
  tests/unit/analysis/test_cargo_prefetch_api.py \
  tests/unit/analysis/test_engine.py
"${C[@]}" logs --tail=60 cargo-prefetch-api analysis-worker
```

Never run `docker compose down -v` on a persistent WAI deployment: that
would delete named Cargo and other data volumes.
