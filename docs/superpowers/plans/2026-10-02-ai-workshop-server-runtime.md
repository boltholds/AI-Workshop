# AI Workshop Server Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an autonomous Server Mode runtime with a Workshop-owned rootless Docker engine, persistent server-owned storage, and a bounded in-deployment controller without exposing the host Docker socket.

**Architecture:** Desktop Mode remains unchanged. Server Mode adds a dedicated control-plane service connected to a rootless Docker daemon through a private socket volume; only typed controller operations can create/manage nested workloads. Canonical project/run storage is Workshop-owned persistent storage mounted into the controller and rootless engine at the same stable path.

**Tech Stack:** Python 3.12, Docker Compose, rootless Docker-in-Docker, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- Never mount the host Docker socket into Workshop services.
- AgentRun/project/MCP containers never receive the rootless engine control socket.
- Runtime callers never provide arbitrary raw Docker CLI fragments.
- Desktop Mode behavior and tests remain green.
- Runtime/domain boundaries are exposed through typed Python `Protocol` interfaces.
- Server-owned storage is the only default bind source for nested workloads.

## Review Focus

- A malicious workspace path must not escape the server-owned storage root; Task 3 adds `test_runtime_mount_rejects_storage_escape`.
- A nested container must never receive the runtime socket; Task 4 adds `test_nested_spec_rejects_runtime_socket_mount`.
- A caller must not smuggle Docker flags through image/name/environment fields; Task 2 adds `test_runtime_models_reject_cli_fragment_identifiers`.
- Restarting the control plane must not destroy rootless runtime/project state; Task 6 adds `test_server_mode_restart_preserves_state`.
- Desktop Mode Compose must remain free of rootless runtime dependencies; Task 6 adds `test_desktop_compose_does_not_include_server_runtime`.

---

### Task 1: Server Mode configuration and runtime contracts

**Files:**
- Create: `src/ai_workshop/server/__init__.py`
- Create: `src/ai_workshop/server/models.py`
- Create: `src/ai_workshop/server/runtime.py`
- Create: `src/ai_workshop/server/config.py`
- Test: `tests/unit/server/test_config.py`
- Test: `tests/unit/server/test_runtime_contract.py`

**Interfaces:**
- Produces: `RuntimeController` Protocol.
- Produces: `RuntimeWorkloadSpec`, `RuntimeWorkloadStatus`, `RuntimeEndpoint`, `ServerModeConfig`.

- [ ] **Step 1: Write failing configuration and protocol tests**

Add tests proving:
- server storage root must be absolute;
- runtime socket path is internal configuration, not caller input;
- workload/image/service identifiers reject leading dashes and path separators;
- the Protocol includes `create`, `start`, `stop`, `remove`, `status`, `logs`, and `publish_private_endpoint`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/unit/server/test_config.py tests/unit/server/test_runtime_contract.py -v`  
Expected: FAIL because the server runtime package does not exist.

- [ ] **Step 3: Implement typed server models/config/contracts**

Implement:
- `class RuntimeController(Protocol)`
- `ServerModeConfig.load(path: Path) -> ServerModeConfig`
- immutable workload/status/endpoint models with explicit validated fields.

- [ ] **Step 4: Run the tests and verify GREEN**

Run the Task 1 tests.  
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: define server runtime contracts"`

### Task 2: Rootless Docker controller adapter

**Files:**
- Create: `src/ai_workshop/server/rootless.py`
- Test: `tests/unit/server/test_rootless_controller.py`

**Interfaces:**
- Consumes: `RuntimeController` contract and runtime models from Task 1.
- Produces: `RootlessDockerController`.

- [ ] **Step 1: Write failing fixed-command tests**

Cover:
- create/start/stop/remove/status/logs construct fixed Docker argv;
- no API accepts caller-supplied Docker flags;
- identifiers such as `--privileged` are rejected;
- environment values stay values and cannot add argv;
- controller points Docker CLI at the private rootless socket only.

Include `test_runtime_models_reject_cli_fragment_identifiers`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/server/test_rootless_controller.py -v`  
Expected: FAIL because `RootlessDockerController` is missing.

- [ ] **Step 3: Implement `RootlessDockerController`**

Use an injected executor and fixed argv generation. Do not shell-join commands.

- [ ] **Step 4: Verify GREEN**

Run Task 2 tests.  
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: add bounded rootless runtime controller"`

### Task 3: Server-owned storage boundary

**Files:**
- Create: `src/ai_workshop/server/storage.py`
- Test: `tests/unit/server/test_storage.py`

**Interfaces:**
- Produces: `ServerStorage.project_root(project_id: str) -> Path`
- Produces: `ServerStorage.run_root(run_id: str) -> Path`
- Produces: `ServerStorage.resolve_run_path(run_id: str, relative: str) -> Path`.

- [ ] **Step 1: Write failing containment tests**

Cover normal paths, traversal, absolute paths, symlink escape, invalid IDs, and `test_runtime_mount_rejects_storage_escape`.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/server/test_storage.py -v`.

- [ ] **Step 3: Implement `ServerStorage`**

Resolve all nested workload bind sources through this class.

- [ ] **Step 4: Verify GREEN**

Run Task 3 tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: add server-owned storage boundary"`

### Task 4: Nested workload policy

**Files:**
- Create: `src/ai_workshop/server/policy.py`
- Modify: `src/ai_workshop/server/rootless.py`
- Test: `tests/unit/server/test_runtime_policy.py`

**Interfaces:**
- Produces: `RuntimePolicy.validate(spec: RuntimeWorkloadSpec) -> None`.

- [ ] **Step 1: Write failing workload-policy tests**

Assert rejection of:
- privileged mode;
- host PID/network namespace;
- runtime socket mounts;
- paths outside ServerStorage;
- unrestricted device mappings;
- duplicate/private control-plane ports.

Include `test_nested_spec_rejects_runtime_socket_mount`.

- [ ] **Step 2: Verify RED**

Run Task 4 tests.

- [ ] **Step 3: Implement policy enforcement before controller execution**

The controller must call `RuntimePolicy.validate` before any create/start operation.

- [ ] **Step 4: Verify GREEN**

Run Task 4 tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: enforce nested workload runtime policy"`

### Task 5: Private runtime endpoint relay

**Files:**
- Create: `src/ai_workshop/server/endpoints.py`
- Modify: `src/ai_workshop/server/rootless.py`
- Test: `tests/unit/server/test_endpoints.py`

**Interfaces:**
- Produces: `PrivateEndpointRegistry.allocate(workload_id: str, container_port: int) -> RuntimeEndpoint`
- Produces: `PrivateEndpointRegistry.release(workload_id: str) -> None`.

- [ ] **Step 1: Write failing endpoint tests**

Assert endpoints bind only to the configured private runtime interface, are unique, are not caller-selected, and are released with the workload.

- [ ] **Step 2: Verify RED**

Run Task 5 tests.

- [ ] **Step 3: Implement endpoint allocation and controller integration**

No LAN/public bind is allowed at this layer.

- [ ] **Step 4: Verify GREEN**

Run Task 5 tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: add private runtime endpoint relay"`

### Task 6: Server deployment profile and smoke test

**Files:**
- Create: `compose.server.yaml`
- Create: `server/Dockerfile`
- Create: `config/server.example.yaml`
- Modify: `src/ai_workshop/cli.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/e2e/test_server_runtime.py`

**Interfaces:**
- Produces: CLI `ai-workshop server doctor`.
- Produces: autonomous control-plane + rootless-runtime deployment profile.

- [ ] **Step 1: Write failing deployment assertions**

Add tests asserting:
- server profile has a rootless runtime service and persistent runtime/project volumes;
- only control-plane receives the private runtime socket;
- no service mounts `/var/run/docker.sock`;
- `test_desktop_compose_does_not_include_server_runtime`.

- [ ] **Step 2: Add the CI smoke scenario**

The scenario starts Server Mode, creates a nested disposable workload through the controller, reads its status/logs, removes it, restarts the outer control-plane service, and proves persistent state remains. Include `test_server_mode_restart_preserves_state`.

- [ ] **Step 3: Implement the server Dockerfile/Compose/CLI wiring**

Pin the rootless runtime image by immutable digest in the implementation PR.

- [ ] **Step 4: Run the complete runtime test set**

Run: `uv run pytest tests/unit/server tests/e2e/test_server_runtime.py -v` plus the existing full suite.

- [ ] **Step 5: Commit**

`git commit -am "feat: add autonomous server runtime profile"`
