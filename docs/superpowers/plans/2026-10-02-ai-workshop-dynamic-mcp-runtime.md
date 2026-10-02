# AI Workshop Dynamic MCP Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hot-pluggable downstream MCP runtime registry so users/agents can register, start, discover, and call MCP servers without restarting Workshop, while keeping one stable upstream MCP surface.

**Architecture:** `McpRegistry` owns downstream registrations and discovered capabilities. Transport adapters implement stdio, Streamable HTTP, and container runtimes. Stable upstream proxy tools call downstream capabilities by server/tool ID; optional promotion changes top-level exposure but is never required for correctness.

**Tech Stack:** Python 3.12, MCP SDK 2.x, httpx, Server Runtime contracts, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- Stable proxy capabilities must work without upstream restart.
- Effective downstream permissions are the intersection of caller, server, project, and deployment policy.
- Stdio MCP servers never run as unrestricted host processes.
- HTTP MCP registration must prevent SSRF to protected/control endpoints.
- Container MCP servers do not receive the runtime socket.
- Run-scoped MCP registrations are cleaned with the run.

## Review Focus

- HTTP registration must reject metadata/control/private endpoints outside policy; Task 4 adds `test_http_transport_rejects_protected_endpoint`.
- A downstream tool-list change during a session must update registry discovery without restarting Workshop; Task 5 adds `test_list_changed_refreshes_capabilities`.
- A read-only caller must not gain write permission through a permissive MCP server; Task 3 adds `test_effective_mcp_permissions_use_intersection`.
- Tool name collisions during promotion must be deterministic and non-destructive; Task 6 adds `test_promote_collision_requires_explicit_name`.
- A crashed run-scoped MCP container must not survive run cleanup/reconciliation; Task 7 adds `test_run_cleanup_removes_orphaned_mcp_runtime`.

---

### Task 1: MCP registry domain

**Files:**
- Create: `src/ai_workshop/mcp_runtime/models.py`
- Create: `src/ai_workshop/mcp_runtime/protocol.py`
- Create: `src/ai_workshop/mcp_runtime/registry.py`
- Test: `tests/unit/mcp_runtime/test_registry.py`

**Interfaces:**
- Produces: `McpRegistry` Protocol.
- Produces registration scopes `run/project/user/global`.
- Produces server lifecycle and discovered tool/resource/prompt metadata.

- [ ] Write failing registration/ownership/scope/state tests.
- [ ] Verify RED.
- [ ] Implement registry/store.
- [ ] Verify GREEN.
- [ ] Commit `feat: add dynamic mcp registry domain`.

### Task 2: Stable upstream proxy service

**Files:**
- Create: `src/ai_workshop/mcp_runtime/proxy.py`
- Create: `src/ai_workshop/gateway/mcp_runtime_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Test: `tests/integration/test_dynamic_mcp_proxy.py`

**Interfaces:**
- Exposes stable `mcp.servers_list/server_get/tools_list/tool_call/resources_list/resource_read/prompts_list/prompt_get`.

- [ ] Write failing stable-schema tests proving newly registered servers require no upstream schema change.
- [ ] Verify RED.
- [ ] Implement proxy service/tool registration.
- [ ] Verify GREEN.
- [ ] Commit `feat: add stable downstream mcp proxy`.

### Task 3: MCP permission intersection

**Files:**
- Create: `src/ai_workshop/mcp_runtime/permissions.py`
- Modify: `src/ai_workshop/mcp_runtime/proxy.py`
- Test: `tests/unit/mcp_runtime/test_permissions.py`

- [ ] Write failing caller/server/project/deployment intersection tests including `test_effective_mcp_permissions_use_intersection`.
- [ ] Verify RED.
- [ ] Implement immutable effective permission calculation and enforcement.
- [ ] Verify GREEN.
- [ ] Commit `feat: bound downstream mcp permissions`.

### Task 4: Downstream transport adapters

**Files:**
- Create: `src/ai_workshop/mcp_runtime/transports/protocol.py`
- Create: `src/ai_workshop/mcp_runtime/transports/stdio.py`
- Create: `src/ai_workshop/mcp_runtime/transports/http.py`
- Create: `src/ai_workshop/mcp_runtime/transports/container.py`
- Test: `tests/integration/mcp_runtime/test_transports.py`

- [ ] Write failing stdio/HTTP/container lifecycle tests and `test_http_transport_rejects_protected_endpoint`.
- [ ] Verify RED.
- [ ] Implement stdio in managed runtime, HTTP with network policy, container via RuntimeController.
- [ ] Verify GREEN.
- [ ] Commit `feat: add managed downstream mcp transports`.

### Task 5: Dynamic discovery and change refresh

**Files:**
- Create: `src/ai_workshop/mcp_runtime/discovery.py`
- Test: `tests/integration/mcp_runtime/test_discovery.py`

- [ ] Write failing initial discovery/reconnect/change-notification tests including `test_list_changed_refreshes_capabilities`.
- [ ] Verify RED.
- [ ] Implement capability cache and refresh reconciliation.
- [ ] Verify GREEN.
- [ ] Commit `feat: refresh dynamic mcp capabilities`.

### Task 6: Optional promoted tools

**Files:**
- Create: `src/ai_workshop/mcp_runtime/promotion.py`
- Modify: upstream gateway integration
- Test: `tests/unit/mcp_runtime/test_promotion.py`

- [ ] Write failing permission/name-collision/unpromote tests including `test_promote_collision_requires_explicit_name`.
- [ ] Verify RED.
- [ ] Implement promotion registry with stable proxy as fallback.
- [ ] Verify GREEN.
- [ ] Commit `feat: add optional mcp tool promotion`.

### Task 7: Agent-created/run-scoped MCP lifecycle

**Files:**
- Modify: `src/ai_workshop/runs/service.py`
- Modify: `src/ai_workshop/mcp_runtime/registry.py`
- Test: `tests/e2e/test_agent_created_mcp.py`

- [ ] Write E2E: AgentRun creates a tiny MCP server, registers/starts it, discovers a new tool, calls it immediately, then stops the run.
- [ ] Add `test_run_cleanup_removes_orphaned_mcp_runtime`.
- [ ] Verify RED.
- [ ] Implement run-scoped ownership/reconciliation cleanup.
- [ ] Verify tool call succeeds without Workshop restart.
- [ ] Commit `test: prove hot pluggable agent mcp runtime`.
