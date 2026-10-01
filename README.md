# AI-Workshop

AI Workshop is an isolated local development environment that gives an AI agent controlled access to source code, browser automation, databases, services, and development tools.

## Core quick start

1. Copy `config/projects.example.yaml` to `config/projects.local.yaml` and point `host` entries at real project folders.
2. Render project bind mounts:

   ```bash
   ai-workshop compose render --projects config/projects.local.yaml --output .workshop/compose.projects.yaml
   ```

3. Start the containerized workspace and persistent browser:

   ```bash
   docker compose -f compose.yaml -f .workshop/compose.projects.yaml up -d agent-workspace browser
   ```

4. Start the host MCP gateway:

   ```bash
   ai-workshop gateway --workspace-url http://127.0.0.1:8766 --browser-url http://127.0.0.1:8767
   ```

The MCP gateway listens on `127.0.0.1:8765`. Workspace and browser control APIs are also loopback-only.

## Browser diagnostics

The browser profile persists in a named volume. Browser tools support viewport/full-page screenshots, selector or coordinate regions, explicit WebM recording, and temporal composites. A diagnostic capture can return neutral and time-gradient PNGs plus structured JSON metadata. Adaptive frame selection is change-driven; intermediate frames are deleted unless `keep_frames=true`.

## Trust boundary

Only explicitly configured project folders are bind-mounted into `agent-workspace`. The base configuration does not mount the host filesystem root, home directory, `.ssh`, normal browser profile, credential stores, or Docker socket.

Docker lifecycle control stays host-side rather than mounting `/var/run/docker.sock` into an agent container.
