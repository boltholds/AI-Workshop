# REA as a WAI MCP subserver

REA 6.4.0 is installed by `rea/Dockerfile` using a committed npm lockfile. A separate non-root `rea-mcp` container keeps one stdio MCP process alive. An authenticated Streamable HTTP bridge over a shared Unix socket connects it to WAI's existing registry/proxy. No new public port is needed.

The existing gateway gains `mcp.servers_list`, `mcp.server_get`, `mcp.tools_list`, `mcp.tool_call`, and the corresponding resource/prompt methods. For example:

```json
{"server_id":"rea"}
```

Pass this to `mcp.tools_list` to obtain REA tool names, descriptions and input schemas. Use `mcp.tool_call` with `server_id`, `tool_name`, and `arguments` exactly as specified by that tool schema. Do not guess native function tool parameters.

## Install on the existing Ubuntu WAI host

Use the AI-Workshop checkout containing this change. This first-install helper requires the existing gateway + analysis-worker deployment and Docker access; it refuses to replace an existing REA deployment. It compares the resolved prior Compose settings with the live gateway (environment, command, mounts, ports and networks), generates a private REA token if absent, builds the two images, waits for REA readiness, and replaces only the gateway. On a gateway/smoke failure it restores a frozen, verified prior Compose snapshot and image, then removes only the newly created REA container. Persistent volumes are retained.

```bash
sudo bash scripts/deploy-ubuntu-rea-mcp.sh --preflight
sudo bash scripts/deploy-ubuntu-rea-mcp.sh --apply
```

The default research mount is `/var/lib/ai-workshop/storage/projects/parasolid-research`. For a custom storage root set `AI_WORKSHOP_REA_PROJECT_PATH` explicitly in `deploy/server/.env` before deployment. The mount is read-only and appears inside REA as `/workspace/target`. It must already exist. Ghidra is mounted from `AI_WORKSHOP_GHIDRA_ROOT` (default `/opt/ai-workshop/ghidra`); WAI's existing installer pins Ghidra 12.1.4. REA data and configuration persist in `rea-data` at `/data`. The configured engine is Ghidra, with JDK 21 in the image.

Compose updates after this rollout must include all overlays:

```bash
docker compose --env-file deploy/server/.env \
  -f deploy/server/compose.yaml \
  -f deploy/server/compose.analysis.yaml \
  -f deploy/server/compose.rea.yaml ps
python3 scripts/mcp-rea-smoke.py --url http://127.0.0.1:8765/mcp
```

The REA smoke check allows 120 seconds per HTTP response (`--timeout` overrides it).
If an earlier rollout timed out and rollback failed, check the running services and
run the smoke check again before attempting another installation. The first-install
helper deliberately refuses to replace an existing REA deployment. Rollback now
pins the previous image under a local `ai-workshop-gateway-rollback` tag and forbids
pulling; a failed rollback preserves REA and its recovery metadata. Treat that
metadata and captured failure logs as private. Do not remove the existing rootless
runtime in response to Compose's orphan-container warning.

For a custom `AI_WORKSHOP_MCP_PORT`, pass that port to the manual smoke check; the installer resolves it automatically.

Refresh the connected WAI tool catalog if the new `mcp.*` tools are not visible after restart. The upstream tool surface then remains stable as REA tools are discovered.

## Scope and limitations

This is an opt-in extension of the existing single-operator private gateway. It does not supply multi-user authentication. The sidecar uses `network_mode: none` and a dedicated Unix socket volume, has no published port, no Docker socket, no WAI credential/state mount, and only the selected research project's read-only mount. The token stays in the bridge process, outside the REA child environment. REA cannot connect back to the WAI gateway or access the Internet. The gateway mounts only the sidecar socket volume read-only.

Requests share one REA session and stateful calls are serialized. Do not run independent investigations concurrently against the same subserver. Individual calls have a 600-second timeout; no retry is made after a possibly executed call. This change does not implement background analysis jobs, automatic restart of a crashed child, dynamic list-change notifications, Wine or native Windows debugging. The health endpoint detects a dead child; inspect/restart the sidecar to recover. Docker `restart: unless-stopped` does not restart an unhealthy but still running container.

MCP discovery proves the REA connection, not Ghidra analysis readiness. Verify provider status and a small selected binary separately before a large DLL analysis. Initial acceptance uses the actual REA process without loading proprietary binaries.
