# AI Workshop — Architecture Design

Date: 2026-10-01
Status: Approved design baseline

## 1. Purpose

AI Workshop is a local, isolated development environment that gives an AI agent controlled access to source code, browser automation, databases, services, and development tools.

The primary goal is to let the agent complete an end-to-end engineering loop against real project folders on the host machine: inspect code, modify files, run tests, start services, reproduce issues in a browser, inspect runtime state, capture diagnostics, and review Git diffs.

The initial target is PLC Web and Titan, but the architecture must remain project-agnostic.

## 2. Core Architecture

AI Workshop uses Docker Compose with multiple isolated services.

The central service is `agent-workspace`. Project directories from the host are mounted into this container as explicit read-write bind mounts. Changes made inside the container are therefore reflected immediately in the real host project directories.

The environment is composed of containerized runtime services plus a narrow host-side control plane:

- `agent-workspace` — shell, filesystem, Git, Python, Node.js, build tools, test tools, and agent capabilities.
- `browser` — persistent Chromium/Playwright environment for interactive and automated browser work.
- `plc-web-frontend` — local PLC Web frontend runtime when enabled.
- `plc-web-backend` — local PLC Web backend runtime when enabled.
- `titan` — isolated Titan runtime with its own development token and configuration.
- `postgres` / Supabase services — local database and application infrastructure.
- `mcp-gateway` — a host-side Streamable HTTP MCP/control process exposed to ChatGPT. It does not directly execute project code; it forwards workspace/browser operations to loopback-only container APIs and owns bounded Docker Compose lifecycle commands.

Container services communicate through a private Docker network. Only the private workspace/browser control APIs are published to host loopback for the gateway; they are not bound to the LAN. This keeps the host Docker socket out of every container while still allowing cross-platform service control.

## 3. Host Workspace Mounts

AI Workshop does not vendor application source code into its own repository.

Projects are configured as bind mounts, for example:

```yaml
projects:
  plc-web:
    host: "C:/Users/example/Code/PLC-Web"
    container: "/workspace/plc-web"
    mode: "rw"

  titan:
    host: "C:/Users/example/Code/Titan"
    container: "/workspace/titan"
    mode: "rw"
```

The host path is user-configurable. The container path is stable and predictable.

The design supports multiple mounted repositories at the same time.

## 4. Agent Workspace

The agent workspace is allowed broad freedom inside the Workshop boundary.

Expected tools include:

- Git
- Python
- uv / Poetry / pip
- Node.js
- npm / pnpm
- pytest
- linters and formatters
- ripgrep
- fd
- jq
- curl
- wget
- compiler/build toolchain
- common Linux shell utilities

The workspace may install project dependencies and run local development commands.

The agent may create, modify, move, and delete files inside explicitly mounted project directories.

## 5. MCP Capability Surface

The public capability model is grouped by purpose rather than by internal implementation.

Initial capability groups:

- `filesystem.*` — read, write, patch, list, search, stat.
- `shell.*` — execute commands and inspect processes.
- `git.*` — status, diff, branch, commit metadata, restore-oriented helpers.
- `browser.*` — navigate, interact, inspect, screenshot, record, and capture diagnostics.
- `services.*` — inspect, restart, rebuild, and read logs for Workshop services.
- `database.*` — query and inspect the isolated local database.
- `workspace.*` — environment state, project mounts, snapshots, and reset-oriented operations.

High-level workflows may be added on top of these primitives, but the primitives remain available for debugging.

## 6. Browser Environment

The browser uses Chromium controlled through Playwright/CDP.

The browser profile is persistent across container restarts, allowing the user to log in once to development services and keep the session.

The profile belongs to AI Workshop and is not the host user's normal browser profile.

Expected browser capabilities:

- navigation
- clicking, typing, scrolling
- DOM inspection
- console inspection
- network inspection
- viewport control
- ordinary screenshot
- full-page screenshot
- video capture
- targeted visual diagnostics

## 7. Browser Diagnostic Modes

AI Workshop supports several visual diagnostic modes.

### 7.1 Static capture

- viewport screenshot
- full-page screenshot
- selected element screenshot
- selected coordinate-region screenshot

### 7.2 Video capture

Video recording starts only on explicit agent request.

The original recording is retained as a diagnostic artifact.

### 7.3 Temporal Composite

A temporal composite converts motion over time into one diagnostic image.

The purpose is to let the agent understand dynamic UI behavior from a single image when video playback is inconvenient or unavailable.

The system supports:

- whole-page mode
- DOM element mode selected by CSS selector
- coordinate-region mode selected by `x`, `y`, `width`, and `height`

The composite uses a motion trail: a moving object may appear in multiple successive positions so its path is visible in one image.

Two render variants are supported:

1. `neutral` — preserves the original visual appearance as much as possible while accumulating motion.
2. `time-gradient` — encodes temporal order with a configurable time gradient.

The caller may request either variant or both from the same recording.

A time legend is optional. It may be embedded in the rendered image or omitted for clean visual/color analysis.

### 7.4 Adaptive frame selection

Temporal composites use adaptive sampling.

The original video is recorded normally. Composite generation then compares frames and retains frames only when a meaningful visual change is detected.

The default threshold mode is `auto`.

The caller may override sensitivity when necessary, for example for subtle animations or noisy canvas rendering.

The implementation should also enforce a configurable maximum sampling rate so fast animation cannot create excessive near-duplicate layers.

### 7.5 Intermediate frames

Selected intermediate frames are temporary by default and are removed after artifact generation.

The caller may explicitly set `keep_frames=true` to preserve them for debugging.

## 8. Diagnostic Artifacts

A browser diagnostic capture may produce:

```text
session/
├── recording.webm
├── composite-neutral.png
├── composite-time-gradient.png
└── metadata.json
```

Only requested artifacts are emitted.

`metadata.json` records enough structured data for later machine analysis, including:

- source URL
- viewport
- capture region / selector
- recording duration
- frame timestamps
- change scores
- changed-region bounding boxes
- selected versus rejected adaptive samples
- composite variant
- threshold configuration
- legend configuration

The PNG is intended for visual reasoning. JSON is intended for structured diagnostics and future automation.

## 9. Persistence

Persistent Docker volumes are used for state that should survive service recreation.

Expected persistent volumes include:

- browser profile
- Postgres data
- Supabase storage
- agent caches
- package-manager caches

Application source code remains on the host through bind mounts.

## 10. Local Infrastructure

Workshop may run isolated copies of the full development stack.

For PLC Web this can include:

- frontend
- backend
- local Postgres
- local Supabase stack
- Titan
- supporting infrastructure

Titan receives a dedicated Workshop token and development configuration.

Production credentials are not required for the normal Workshop flow.

The architecture must permit the agent to rebuild or restart individual services without destroying browser state or unrelated services.

## 11. Secrets

Secrets are never committed to the AI Workshop repository.

They are supplied through local environment files, Docker secrets, or another explicit local secret mechanism.

The environment should prefer narrow, Workshop-specific credentials over production credentials.

A persistent browser profile may contain authenticated development sessions; it is treated as private local state and never checked into Git.

## 12. Isolation and Trust Boundary

The AI agent is considered broadly trusted inside the Workshop sandbox, but the Workshop itself is not given unrestricted host access.

The design intentionally avoids mounting:

- the host filesystem root
- the complete user home directory
- host `.ssh`
- the host browser profile
- general credential stores
- `/var/run/docker.sock`

Mounting the host Docker socket would effectively defeat the container boundary and is therefore excluded from the default architecture.

Service-management access is provided by the host-side MCP/control gateway using fixed, allowlisted Docker Compose operations. The gateway is bound to host loopback by default and container control APIs are also loopback-only. The model never receives a raw Docker socket or an unrestricted host shell.

## 13. Snapshot and Recovery

Potentially destructive development work should be recoverable.

The initial recovery model combines:

- Git status/diff before mutation-heavy work
- repository-native Git recovery
- database snapshots/dumps for local data
- persistent data reset helpers

Planned Workshop-level operations include:

- snapshot
- restore
- reset to a known local state

These operations must never silently overwrite host repositories without an explicit restore action.

## 14. Failure Handling

The MCP boundary returns structured failures rather than raw internal stack traces by default.

Diagnostic detail may still be available through explicit logs and debugging tools.

Long-running browser recordings and commands must be cancellable.

If a service is unavailable, the gateway should report which dependency failed rather than presenting an ambiguous generic failure.

Artifact generation failures must not delete the original video recording if video capture itself succeeded.

## 15. Testing Strategy

The implementation should be tested at several layers:

- unit tests for filesystem/path validation and command wrappers
- unit tests for temporal-composite frame selection and metadata generation
- integration tests for bind-mounted workspace modification
- integration tests for persistent browser profile behavior
- integration tests for service discovery/restart/log access
- browser tests for screenshot, video, selector-region, and coordinate-region capture
- end-to-end test: modify a sample project, run it, inspect it in Chromium, capture diagnostics, and verify Git diff

Temporal-composite tests should use deterministic synthetic frame sequences so motion paths and selected samples can be asserted reliably.

## 16. Initial Repository Structure

```text
AI-Workshop/
├── compose.yaml
├── .env.example
├── README.md
├── agent/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── config/
├── gateway/
│   ├── mcp/
│   └── control/
├── browser/
│   ├── Dockerfile
│   └── playwright/
├── infrastructure/
│   ├── postgres/
│   ├── supabase/
│   └── titan/
├── config/
│   ├── projects.example.yaml
│   └── services.example.yaml
├── scripts/
│   ├── up
│   ├── down
│   ├── reset
│   ├── snapshot
│   └── doctor
└── docs/
    └── superpowers/
        └── specs/
```

The exact internal package layout may evolve during implementation as long as these architectural boundaries remain intact.

## 17. Non-Goals for the First Implementation

The first implementation does not require:

- Kubernetes or k3s
- unrestricted control of the host Docker daemon
- production credentials
- automatic capture of video/composites for every browser action
- advanced semantic classification of motion such as automatic `drag`, `layout_shift`, or `animation` labels
- arbitrary host filesystem access

These can be evaluated later if concrete use cases justify them.

## 18. Success Criteria

The architecture is considered successful when the following workflow is possible from one connected AI session:

1. inspect a bind-mounted project;
2. edit its real host files;
3. run tests and builds;
4. start or restart the relevant local services;
5. open the application in persistent Chromium;
6. reproduce a UI problem;
7. capture screenshot and/or video diagnostics;
8. generate temporal composite PNG + structured JSON on request;
9. inspect Git diff;
10. leave all production systems and unrelated host files untouched.
