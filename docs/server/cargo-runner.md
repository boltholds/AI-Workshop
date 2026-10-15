# Offline Cargo testing through AI Workbench

Cargo dependency preparation and test execution run in separate containers.

The one-shot cargo-prefetch service is **networked** and receives only read-only
project files plus writable named volumes cargo-cache and cargo-lockfiles. It
runs cargo metadata, cargo generate-lockfile (when necessary), then
cargo fetch --locked. It receives no WAI token, server state or Docker socket.

The analysis-worker remains on its internal network, mounts both Cargo volumes
read-only, and runs cargo test --offline --locked in a disposable snapshot.
The original project, Git index, and cache volumes remain unchanged.

## Deploy and prepare RustSolid

Use the AI Workshop checkout with this change. Include all installed overlays
(omit compose.rea.yaml only if REA has not been deployed).

~~~bash
cd /opt/ai-workshop
C=(
  docker compose --env-file deploy/server/.env
  -f deploy/server/compose.yaml
  -f deploy/server/compose.analysis.yaml
  -f deploy/server/compose.rea.yaml
)
"${C[@]}" config --quiet
"${C[@]}" --profile cargo build cargo-prefetch analysis-worker
"${C[@]}" --profile cargo run --rm --no-deps cargo-prefetch rustsolid
"${C[@]}" up -d --no-deps --no-build --wait --wait-timeout 120 analysis-worker
"${C[@]}" ps gateway analysis-worker rea-mcp
~~~

For a nested workspace manifest, pass --manifest-path crates/core/Cargo.toml
after the project id. Then call cargo_test through AI Workbench MCP.

The dependency cache key includes the chosen manifest, project Cargo.toml and
Cargo.lock files, and Cargo configuration. Changing source files alone does
not require another fetch. Missing/stale metadata produces a bounded error.
If a Cargo.lock is missing, the prefetch job generates it in scratch and
preserves a checksum-verified copy in its private volume. This is reproducible
within that prepared snapshot; cross-machine reproducibility benefits from
reviewing and committing Cargo.lock separately.

Security: only prefetch trusted Rust manifests, registries and dependencies.
The one-shot job has normal Docker egress (no registry-domain allowlist).
The worker has no Internet access. Scratch excludes .git, .ssh, .env, target
and other local state. Project symlinks are rejected. Ordinary /tmp remains restricted; Rust build scripts and test binaries use a
separate executable /cargo-build tmpfs, with nosuid and no network access.
Each allocation is limited to 2 GiB, so very large builds can exhaust space.

Do not use docker compose down -v: it deletes named volumes.

## Checks

~~~bash
uv run pytest -q tests/unit/analysis/test_cargo_cache.py \
  tests/unit/analysis/test_project_files.py \
  tests/unit/analysis/test_engine.py
"${C[@]}" logs --tail=60 analysis-worker
~~~

Preparing dependencies does not demonstrate that RustSolid tests pass. Run
cargo_test after deployment, and inspect its real compiler/test exit code.
