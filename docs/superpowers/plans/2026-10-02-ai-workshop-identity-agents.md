# AI Workshop Server Identity, Agents & Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add principal-based RBAC, persistent AgentIdentity, isolated AgentRun containers/worktrees, delegation limits, and auditable attribution.

**Architecture:** Authorization evaluates principals independently of authentication. Agent identity is persistent state; every execution creates a separate run with a computed immutable effective-permission set and its own workspace/runtime.

**Tech Stack:** Python 3.12, Pydantic, SQLite/PostgreSQL-compatible persistence abstraction, Git worktrees, Server Runtime contracts, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- Principals include User, Agent, ServiceAccount, and ExternalIdentity.
- Roles can be assigned to users and agents.
- Delegated permissions must be a subset of delegator effective permissions.
- Parallel AgentRuns never share one mutable runtime/worktree.
- Audit logs never contain secrets.
- Runtime containers receive only the run's explicit project workspace and resources.

## Review Focus

- Conflicting global/project grants must resolve to the narrower effective permission; Task 2 adds `test_project_membership_cannot_expand_global_denial`.
- Delegation must reject privilege escalation; Task 4 adds `test_agent_cannot_delegate_permission_it_does_not_hold`.
- Concurrent runs of one agent must receive distinct worktrees; Task 5 adds `test_parallel_runs_use_distinct_worktrees`.
- A stopped run must not leave a live container or run-scoped MCP/service resource; Task 6 adds `test_run_stop_cleans_scoped_resources`.
- Audit redaction must remove credential/token values from errors; Task 3 adds `test_audit_never_records_secret_values`.

---

### Task 1: Principal and role domain

**Files:**
- Create: `src/ai_workshop/identity/models.py`
- Create: `src/ai_workshop/identity/protocol.py`
- Create: `src/ai_workshop/identity/store.py`
- Test: `tests/unit/identity/test_principals.py`

**Interfaces:**
- Produces: `PrincipalService` Protocol.
- Produces principal variants and role/project-membership records.

- [ ] Write failing principal/role persistence tests.
- [ ] Verify RED.
- [ ] Implement typed principal/role store.
- [ ] Verify GREEN.
- [ ] Commit `feat: add principal and role domain`.

### Task 2: Authorization engine

**Files:**
- Create: `src/ai_workshop/authz/models.py`
- Create: `src/ai_workshop/authz/service.py`
- Test: `tests/unit/authz/test_effective_permissions.py`

**Interfaces:**
- Produces: `AuthorizationService.effective_permissions(principal_id, project_id) -> PermissionSet`.
- Produces: `require(principal_id, permission, project_id) -> None`.

- [ ] Write failing role/project/scope intersection tests, including `test_project_membership_cannot_expand_global_denial`.
- [ ] Verify RED.
- [ ] Implement deterministic permission evaluation.
- [ ] Verify GREEN.
- [ ] Commit `feat: add server authorization engine`.

### Task 3: Audit service

**Files:**
- Create: `src/ai_workshop/audit/models.py`
- Create: `src/ai_workshop/audit/protocol.py`
- Create: `src/ai_workshop/audit/store.py`
- Test: `tests/unit/audit/test_audit.py`

**Interfaces:**
- Produces: `AuditService.record(event: AuditEvent) -> None`.
- Produces query by actor/project/run/action/time range.

- [ ] Write failing attribution/redaction tests including `test_audit_never_records_secret_values`.
- [ ] Verify RED.
- [ ] Implement append-only normalized audit records.
- [ ] Verify GREEN.
- [ ] Commit `feat: add auditable principal actions`.

### Task 4: Persistent AgentIdentity and delegation

**Files:**
- Create: `src/ai_workshop/agents/models.py`
- Create: `src/ai_workshop/agents/service.py`
- Test: `tests/unit/agents/test_identities.py`
- Test: `tests/unit/agents/test_delegation.py`

**Interfaces:**
- Produces: `AgentService.create_persistent/create_ephemeral/get/archive`.
- Produces: `DelegationService.delegate(parent_run_id, child_agent_id, requested_permissions) -> DelegationGrant`.

- [ ] Write failing persistent/ephemeral identity tests.
- [ ] Write `test_agent_cannot_delegate_permission_it_does_not_hold`.
- [ ] Verify RED.
- [ ] Implement AgentIdentity and delegation subset enforcement.
- [ ] Verify GREEN.
- [ ] Commit `feat: add persistent agents and bounded delegation`.

### Task 5: Run workspace manager

**Files:**
- Create: `src/ai_workshop/runs/workspaces.py`
- Test: `tests/integration/runs/test_worktrees.py`

**Interfaces:**
- Produces: `RunWorkspaceManager.create(project_id, run_id, base_ref, writable) -> RunWorkspace`.
- Produces: `remove(run_id)`.

- [ ] Write failing Git worktree tests including `test_parallel_runs_use_distinct_worktrees`.
- [ ] Verify RED.
- [ ] Implement worktree lifecycle under ServerStorage run root.
- [ ] Verify GREEN.
- [ ] Commit `feat: isolate agent run workspaces`.

### Task 6: AgentRun orchestration

**Files:**
- Create: `src/ai_workshop/runs/models.py`
- Create: `src/ai_workshop/runs/protocol.py`
- Create: `src/ai_workshop/runs/service.py`
- Test: `tests/integration/runs/test_run_service.py`

**Interfaces:**
- Produces: `RunService.start/stop/status/list`.
- Consumes: AuthorizationService, RunWorkspaceManager, RuntimeController, AuditService.

- [ ] Write failing run lifecycle/resource-limit tests and `test_run_stop_cleans_scoped_resources`.
- [ ] Verify RED.
- [ ] Implement orchestration with immutable effective permissions captured at run start.
- [ ] Verify GREEN.
- [ ] Commit `feat: add isolated agent run lifecycle`.

### Task 7: Identity/agent/run MCP tools

**Files:**
- Create: `src/ai_workshop/gateway/agent_tools.py`
- Create: `src/ai_workshop/gateway/run_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Test: `tests/integration/test_agent_run_mcp.py`

- [ ] Write failing schema/authorization tests.
- [ ] Verify RED.
- [ ] Implement authorized MCP tools with actor context.
- [ ] Verify GREEN and full suite.
- [ ] Commit `feat: expose agents and isolated runs through MCP`.
