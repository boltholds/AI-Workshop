# AI Workshop

AI Workshop is an isolated local development environment that gives an AI agent controlled access to source code, shell tools, Git, browser automation, databases, and local services.

## Core quick start

Requirements: Docker Compose v2 and Python 3.12+ with `uv`.

1. Copy `config/projects.example.yaml` to `config/projects.local.yaml` and replace host paths with the repositories you want to expose.
2. Keep every `container` path under `/workspace/...`; these are the paths used by the agent container.
3. Render the project mount override:

```bash
uv run ai-workshop compose render \
  --projects config/projects.local.yaml \
  --output .workshop/compose.projects.yaml
```

4. Start the isolated workspace container:

```bash
AI_WORKSHOP_PROJECTS_CONFIG=./config/projects.local.yaml \
  docker compose -f compose.yaml -f .workshop/compose.projects.yaml up -d agent-workspace
```

5. Start the host-side MCP gateway:

```bash
uv run ai-workshop gateway --workspace-url http://127.0.0.1:8766
```

The MCP endpoint is `http://127.0.0.1:8765/mcp` by default.

## Security boundary

Only repositories explicitly listed in `projects.local.yaml` are bind-mounted into `agent-workspace`. The base Compose file does not mount the host Docker socket, the host home directory, `.ssh`, or a host browser profile. The workspace HTTP API is published on loopback only. Docker service control is added through a separate bounded host-side control layer rather than by exposing `/var/run/docker.sock`.

See `docs/superpowers/specs/2026-10-01-ai-workshop-design.md` for the complete architecture.
