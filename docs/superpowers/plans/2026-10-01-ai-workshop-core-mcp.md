# AI Workshop Core Workspace & MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minimal AI Workshop runtime that mounts real host projects, exposes safe filesystem/shell/Git operations, and publishes them through an MCP v2 Streamable HTTP gateway.

**Architecture:** A private `agent-workspace` FastAPI service owns direct access to mounted repositories. A separate `mcp-gateway` uses the official MCP Python SDK v2 and forwards typed tool calls to that private service over the Workshop Docker network. Host project mounts are generated from a local YAML file into a Compose override so the base repository stays project-agnostic.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, httpx, official `mcp>=2,<3` Python SDK, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-01-ai-workshop-design.md`

## Global Constraints

- Project source code remains on the host and is mounted through explicit read-write bind mounts.
- AI Workshop must not mount the host filesystem root, complete home directory, host `.ssh`, host browser profile, credential stores, or host Docker socket.
- The agent may create, modify, move, and delete files only inside explicitly configured mounted project directories.
- MCP-facing failures are structured and do not expose raw internal stack traces by default.
- Long-running commands must have a timeout and a cancellation path.
- The base repository must remain project-agnostic.

## Review Focus

- Path traversal such as `../other-project` must be rejected even if the target exists; Task 2 adds `test_rejects_parent_traversal`.
- Symlinks inside an allowed project that resolve outside the project root must be rejected; Task 2 adds `test_rejects_symlink_escape`.
- Shell commands must not run with an unconfigured or host-global working directory; Task 3 adds `test_shell_rejects_unknown_project`.
- A command timeout must terminate the process tree and return a structured timeout result; Task 3 adds `test_shell_timeout_terminates_child`.
- MCP transport failures must return stable tool errors without leaking Python tracebacks; Task 4 adds `test_gateway_sanitizes_workspace_failure`.

---

### Task 1: Python package, configuration model, and project mount renderer

**Files:**
- Create: `pyproject.toml`
- Create: `src/ai_workshop/__init__.py`
- Create: `src/ai_workshop/config.py`
- Create: `src/ai_workshop/compose/render.py`
- Create: `src/ai_workshop/cli.py`
- Create: `config/projects.example.yaml`
- Create: `.env.example`
- Modify: `.gitignore`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_compose_render.py`

**Interfaces:**
- Consumes: none.
- Produces: `WorkshopConfig.load(path: Path) -> WorkshopConfig`, `ProjectMount`, and `render_project_override(config: WorkshopConfig, output: Path) -> Path`.

- [ ] **Step 1: Write failing configuration tests**

Add tests proving that project IDs are unique, host/container paths are required, modes are limited to `ro|rw`, and missing local config produces a clear validation error.

- [ ] **Step 2: Run the configuration tests**

Run: `uv run pytest tests/unit/test_config.py -v`  
Expected: FAIL because `WorkshopConfig` does not exist.

- [ ] **Step 3: Implement the configuration model**

Implement `ProjectMount(project_id: str, host: Path, container: PurePosixPath, mode: Literal["ro","rw"])` and `WorkshopConfig.load(path: Path) -> WorkshopConfig` in `src/ai_workshop/config.py`.

- [ ] **Step 4: Run the configuration tests**

Run: `uv run pytest tests/unit/test_config.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing Compose-render tests**

Assert that two configured projects produce a deterministic override containing matching bind mounts for both `agent-workspace` and no unrelated host paths.

- [ ] **Step 6: Run the Compose-render tests**

Run: `uv run pytest tests/unit/test_compose_render.py -v`  
Expected: FAIL because `render_project_override` does not exist.

- [ ] **Step 7: Implement the Compose override renderer and CLI command**

Implement `render_project_override(config, output)` and CLI command `ai-workshop compose render --projects <path> --output <path>`. Write generated files under `.workshop/`.

- [ ] **Step 8: Run Task 1 tests**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_compose_render.py -v`  
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src/ai_workshop config .env.example .gitignore tests/unit
git commit -m "feat: add workshop project configuration"
```

### Task 2: Project boundary and filesystem operations

**Files:**
- Create: `src/ai_workshop/workspace/paths.py`
- Create: `src/ai_workshop/workspace/filesystem.py`
- Create: `src/ai_workshop/models/filesystem.py`
- Test: `tests/unit/workspace/test_paths.py`
- Test: `tests/unit/workspace/test_filesystem.py`

**Interfaces:**
- Consumes: `WorkshopConfig` and `ProjectMount` from Task 1.
- Produces: `PathPolicy.resolve(project_id: str, relative_path: str) -> Path`, `FilesystemService.list/read/write/patch/search`.

- [ ] **Step 1: Write failing path-policy tests**

Cover valid nested paths, `test_rejects_parent_traversal`, absolute paths, unknown project IDs, and `test_rejects_symlink_escape`.

- [ ] **Step 2: Run the path-policy tests**

Run: `uv run pytest tests/unit/workspace/test_paths.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement `PathPolicy`**

Resolve against the configured project root, canonicalize with `Path.resolve()`, and require the canonical target to remain under the canonical project root before any operation.

- [ ] **Step 4: Run the path-policy tests**

Run: `uv run pytest tests/unit/workspace/test_paths.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing filesystem service tests**

Cover list, UTF-8 read/write, binary rejection for text endpoints, bounded read sizes, exact-string patch precondition, and recursive text search.

- [ ] **Step 6: Implement `FilesystemService`**

Use `PathPolicy` for every path. Define typed request/response models in `models/filesystem.py`; patch must fail if the expected old text is absent or appears more than once unless an explicit occurrence is supplied.

- [ ] **Step 7: Run Task 2 tests**

Run: `uv run pytest tests/unit/workspace/test_paths.py tests/unit/workspace/test_filesystem.py -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ai_workshop/workspace src/ai_workshop/models tests/unit/workspace
git commit -m "feat: add bounded workspace filesystem"
```

### Task 3: Shell and Git execution service

**Files:**
- Create: `src/ai_workshop/workspace/processes.py`
- Create: `src/ai_workshop/workspace/git.py`
- Create: `src/ai_workshop/models/process.py`
- Test: `tests/unit/workspace/test_processes.py`
- Test: `tests/integration/test_git_service.py`

**Interfaces:**
- Consumes: `PathPolicy.resolve(...)` from Task 2.
- Produces: `ProcessService.exec(request: ExecRequest) -> ExecResult`, `ProcessService.cancel(run_id: UUID) -> bool`, `GitService.status(project_id) -> GitStatus`, `GitService.diff(project_id, staged: bool) -> str`.

- [ ] **Step 1: Write failing shell tests**

Cover stdout/stderr capture, exit code, environment allowlist additions, `test_shell_rejects_unknown_project`, timeout, `test_shell_timeout_terminates_child`, and explicit cancellation.

- [ ] **Step 2: Run shell tests**

Run: `uv run pytest tests/unit/workspace/test_processes.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement `ProcessService`**

Run commands without `shell=True` when argv is provided; support an explicit shell command form separately. Always set cwd to a path resolved under a configured project. Track subprocess groups by run ID so timeout/cancel terminates the entire group.

- [ ] **Step 4: Run shell tests**

Run: `uv run pytest tests/unit/workspace/test_processes.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing Git integration tests**

Create a temporary Git repository and assert status and staged/unstaged diffs are returned without mutating the repository.

- [ ] **Step 6: Implement `GitService`**

Use the process service with fixed Git argv and project-root cwd. Keep mutating Git operations out of this first plan.

- [ ] **Step 7: Run Task 3 tests**

Run: `uv run pytest tests/unit/workspace/test_processes.py tests/integration/test_git_service.py -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ai_workshop/workspace src/ai_workshop/models tests
git commit -m "feat: add shell and git workspace services"
```

### Task 4: Private workspace API and MCP v2 gateway

**Files:**
- Create: `src/ai_workshop/workspace/app.py`
- Create: `src/ai_workshop/gateway/server.py`
- Create: `src/ai_workshop/gateway/client.py`
- Create: `src/ai_workshop/gateway/errors.py`
- Test: `tests/integration/test_workspace_api.py`
- Test: `tests/integration/test_mcp_gateway.py`

**Interfaces:**
- Consumes: filesystem, process, and Git services from Tasks 2–3.
- Produces: private HTTP endpoints under `/v1/*`; MCP tools `workspace_projects`, `filesystem_list`, `filesystem_read`, `filesystem_write`, `filesystem_patch`, `filesystem_search`, `shell_exec`, `shell_cancel`, `git_status`, and `git_diff`.

- [ ] **Step 1: Write failing workspace API integration tests**

Assert `/health`, project listing, filesystem read/write, shell execution, and Git status work through FastAPI while raw exceptions are mapped to structured error objects.

- [ ] **Step 2: Implement the private workspace API**

Expose only the typed service methods required by the MCP layer. Bind to the private container interface; do not publish the workspace API to the host.

- [ ] **Step 3: Run workspace API tests**

Run: `uv run pytest tests/integration/test_workspace_api.py -v`  
Expected: PASS.

- [ ] **Step 4: Write failing MCP gateway tests**

Use the MCP SDK client against the server in-process. Assert tool discovery, a successful filesystem call, a shell call, and `test_gateway_sanitizes_workspace_failure`.

- [ ] **Step 5: Implement the MCP v2 gateway**

Use `MCPServer` from the official `mcp>=2,<3` SDK and Streamable HTTP transport. Tool handlers call `WorkspaceClient` through httpx and translate private API errors into stable MCP tool errors.

- [ ] **Step 6: Run Task 4 tests**

Run: `uv run pytest tests/integration/test_workspace_api.py tests/integration/test_mcp_gateway.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ai_workshop/workspace/app.py src/ai_workshop/gateway tests/integration
git commit -m "feat: expose workspace through mcp gateway"
```

### Task 5: Containerization and end-to-end core smoke test

**Files:**
- Create: `compose.yaml`
- Create: `agent/Dockerfile`
- Create: `agent/entrypoint.sh`
- Create: `gateway/Dockerfile`
- Create: `gateway/entrypoint.sh`
- Create: `tests/e2e/test_core_compose.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 mount override and Task 4 HTTP services.
- Produces: runnable `agent-workspace` and `mcp-gateway` services on the `ai-workshop` private network.

- [ ] **Step 1: Write the failing Compose smoke test**

The test must create a temporary host Git repository, render a project override, start only `agent-workspace` and `mcp-gateway`, write a file through MCP, run a command through MCP, and verify the file changed on the host.

- [ ] **Step 2: Implement the two container images and base Compose file**

Run containers as a non-root user, mount only generated project binds, expose only the MCP gateway port to the host, add healthchecks, and add named caches without mounting the host Docker socket.

- [ ] **Step 3: Run the E2E core test**

Run: `uv run pytest tests/e2e/test_core_compose.py -v`  
Expected: PASS.

- [ ] **Step 4: Update README with core quick start**

Document `config/projects.local.yaml`, override rendering, Compose startup, MCP endpoint, and the explicit host-access boundary.

- [ ] **Step 5: Run the complete core suite**

Run: `uv run pytest tests/unit tests/integration tests/e2e/test_core_compose.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add compose.yaml agent gateway README.md tests/e2e
git commit -m "feat: ship core ai workshop runtime"
```
