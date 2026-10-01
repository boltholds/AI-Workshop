# AI-Workshop

AI Workshop is an isolated local development environment that gives an AI agent controlled access to source code, browser automation, databases, services, and development tools.

## Core quick start

1. Copy `config/projects.example.yaml` to `config/projects.local.yaml` and point `host` entries at the real project folders on your machine.
2. Generate the bind-mount override:

   ```bash
   ai-workshop compose render \
     --projects config/projects.local.yaml \
     --output .workshop/compose.projects.yaml
   ```

3. On native Linux, export your host UID/GID so bind-mounted project files stay writable by the non-root agent process:

   ```bash
   export AI_WORKSHOP_UID="$(id -u)"
   export AI_WORKSHOP_GID="$(id -g)"
   ```

   Docker Desktop users can normally keep the defaults.

4. Start the containerized workspace:

   ```bash
   docker compose -f compose.yaml -f .workshop/compose.projects.yaml up -d agent-workspace
   ```

5. Create a local workspace token (for example with a password manager or `openssl rand -hex 32`) and set `AI_WORKSHOP_WORKSPACE_TOKEN`.
6. Start the MCP gateway on the host:

   ```bash
   AI_WORKSHOP_WORKSPACE_TOKEN="<same-token>" \
     ai-workshop gateway --workspace-url http://127.0.0.1:8766
   ```

The MCP endpoint is served on host loopback at port `8765`. The workspace control API is also exposed only on loopback at port `8766` and requires the shared Workshop bearer token for every `/v1/*` call.

## Trust boundary

Only explicitly configured project folders are bind-mounted into `agent-workspace`. The base configuration does not mount the host filesystem root, home directory, `.ssh`, browser profile, credential stores, or Docker socket.

The MCP gateway runs on the host and forwards project operations to the loopback-only workspace API. Docker lifecycle control is added through bounded host-side operations in the infrastructure phase rather than by mounting `/var/run/docker.sock` into a container.


## Recovery workflow

For mutation-heavy work, the intended loop is:

```text
doctor
  → project/state snapshot
  → reproduce
  → edit
  → test/build
  → browser diagnostics when useful
  → Git diff
  → keep or explicit preview + confirmed restore
```

Project restore is confirmation-token gated and preserves pre-existing staged, unstaged, and untracked Git state. Persistent service state is handled through optional adapters rather than assuming a specific database.

See `docs/workflows/debug-ui.md` for the full project-agnostic workflow.


## One-command local bootstrap

Windows:

~~~powershell
.\scripts\bootstrap.ps1 -Project C:\Code\MyProject
~~~

macOS/Linux:

~~~bash
bash scripts/bootstrap.sh --project /path/to/MyProject
~~~

The bootstrap preserves existing local secrets/configuration, starts the workspace and browser, starts the host-side MCP gateway, and finishes with ai-workshop doctor.

To connect the private localhost MCP endpoint to ChatGPT without publishing it to the internet, use Secure MCP Tunnel. See docs/chatgpt-setup.md.
