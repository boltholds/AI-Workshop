# Ubuntu Server Mode: guarded analysis-worker rollout

Use this procedure after merging the Ubuntu deployment helper PR. It deliberately
**does not migrate** the older rootless-runtime container or recreate
server-control, ingress or browser. This reduces risk to existing run state.

The analysis overlay is opt-in and cannot be enabled accidentally. The existing
gateway remains live while the new worker is being built and health-checked.
The gateway will be briefly restarted only after worker readiness is confirmed.

## 1. Current host checks

Run all commands on the actual WAI Ubuntu VPS, not on a development machine.
The normal deployment is at /opt/ai-workshop and uses Docker Compose v2.

    cd /opt/ai-workshop
    git status --short
    git fetch origin
    git pull --ff-only origin main
    docker compose -f deploy/server/compose.yaml ps
    systemctl status ai-workshop-tunnel --no-pager || true

If Git refuses to pull, inspect local changes first rather than resetting them.
If the rootless-runtime container appears as an orphan, **leave it running**.
Never run down -v, docker volume prune, or up --remove-orphans during this rollout.

## 2. Make the MCP tunnel boot-persistent

    bash scripts/install-tunnel-systemd.sh

The helper preserves an existing /etc/ai-workshop/tunnel.env or securely prompts
for an OpenAI tunnel runtime API key, creates a root-owned EnvironmentFile, and
enables an ai-workshop-tunnel systemd service. It does not print the key.

If a foreground tunnel still occupies port 8080, end that foreground process
using Ctrl+C; then start the enabled unit:

    systemctl start ai-workshop-tunnel
    systemctl is-enabled ai-workshop-tunnel
    systemctl is-active ai-workshop-tunnel
    journalctl -u ai-workshop-tunnel -n 30 --no-pager

After a reboot, systemd will start the tunnel automatically. A healthy tunnel
still requires a reachable gateway and a valid key.

## 3. Install a pinned official Ghidra release

The new analysis worker uses a **full JDK 21**, as required by Ghidra 12.1.4.
The installer downloads the official release archive and verifies its published
SHA-256 checksum before extraction. It does not overwrite existing installations.

    bash scripts/install-ghidra-pinned.sh

This step requires curl, unzip, sha256sum and free disk space for a roughly
570 MB compressed Ghidra archive and its extracted contents. The host does not
need Java; Java is provided inside the worker container.

The installed headless analyzer path is:

    /opt/ai-workshop/ghidra/support/analyzeHeadless

## 4. Preflight and deploy just two services

First run the read-only preflight:

    bash scripts/deploy-ubuntu-analysis-worker.sh --preflight

It verifies an existing running gateway, confirms that the new storage bind
mount matches the existing gateway, and validates the Compose overlay.

Then deploy:

    bash scripts/deploy-ubuntu-analysis-worker.sh --apply

The apply operation:

1. Saves the existing gateway image ID, Compose models and container metadata
   under a private directory in /var/backups/ai-workshop.
2. Backs up the existing named gateway state volume.
3. Creates a new worker token only if one is missing, preserving the other
   .env values.
4. Builds the new gateway and analysis-worker images.
5. Starts the isolated analysis worker and waits for a healthy status.
6. Recreates only the gateway, preserving the other WAI service containers.
7. Calls tools/list through the local MCP endpoint and requires all six analysis
   tools to be present.
8. Attempts to restore the original gateway image automatically if startup or
   discovery validation fails.

The volume backup is a best-effort online snapshot; it is **not** a complete,
transactionally consistent backup of every persistent domain. For a major
runtime migration, take a full offline backup separately.

Do not update server-control or remove the legacy rootless runtime as part
of this initial worker rollout. Those require a dedicated compatibility
migration, as documented in docs/server/deployment.md.

## 5. Verify and start analysis

    docker compose -f deploy/server/compose.yaml \
      -f deploy/server/compose.analysis.yaml ps
    python3 scripts/mcp-analysis-smoke.py

The new worker and gateway should be healthy. Update the developer-mode
ChatGPT app's tool discovery if its tool list still shows an older schema.

Register RustSolid and an independent private research checkout as WAI projects.
Keep any third-party binaries out of public Git history unless authorized.
Then use shell_exec to inspect PE headers, binary_analyze to queue an authorized
Ghidra analysis, analysis_get_results to read its metadata, and cargo_test for
trusted Rust projects with offline dependencies available.

The gateway's shell_exec is deliberately **not** an unrestricted Ubuntu shell:
only a small allowlist of read-only binary inspection utilities is exposed.
