# AI Workshop Server Recovery & Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Workshop recovery to cover Server Mode repositories, retained run workspaces, identity/configuration, MCP registry metadata, and optional infrastructure state without introducing a global destructive reset.

**Architecture:** Existing preview + short-lived confirmation-token semantics remain the destructive-action boundary. Server recovery is adapter-driven: each state domain describes snapshot/restore/backup behavior through typed protocols, while project repositories retain Git-aware recovery.

**Tech Stack:** Python 3.12, existing recovery services, tar/manifest hashing, provider adapters, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- No implicit `wipe all projects` or global destructive reset.
- Restore never targets paths outside Workshop-owned state or explicitly registered external project roots.
- Every destructive restore/reset has preview + bound confirmation token.
- Failed restore preserves its source artifact.
- Secret material is excluded from ordinary backup artifacts unless handled by a dedicated encrypted secret-backend export.
- Recovery modules depend on typed state-domain protocols, not concrete provider stores.

## Review Focus

- Restoring identity/config state must not roll back unrelated project repositories; Task 3 adds `test_identity_restore_does_not_touch_projects`.
- Retained AgentRun worktree restore must reject a run/project identity mismatch; Task 2 adds `test_run_workspace_restore_rejects_project_mismatch`.
- MCP registry restore must not auto-start previously running untrusted servers; Task 4 adds `test_mcp_registry_restore_returns_servers_stopped`.
- Forgejo backup failure must retain both the last good backup and failed-attempt diagnostics; Task 5 adds `test_forgejo_failed_backup_keeps_last_good_snapshot`.
- Server reset scopes must never include credential/CA private state by default; Task 6 adds `test_reset_scopes_exclude_secret_and_ca_state`.

---

### Task 1: Server recovery domain registry

**Files:**
- Create: `src/ai_workshop/recovery/server_domains.py`
- Test: `tests/unit/recovery/test_server_domains.py`

**Interfaces:**
- Produces: `ServerRecoveryDomain` Protocol with `preview_snapshot`, `snapshot`, `preview_restore`, `restore`.
- Produces: `ServerRecoveryRegistry.require(domain_id)`, `list()`.

- [ ] Write failing domain registration/collision/unknown-domain tests.
- [ ] Verify RED.
- [ ] Implement typed recovery domain registry.
- [ ] Verify GREEN.
- [ ] Commit `feat: add server recovery domain registry`.

### Task 2: Canonical project and retained-run recovery

**Files:**
- Create: `src/ai_workshop/recovery/server_projects.py`
- Test: `tests/integration/recovery/test_server_projects.py`

**Interfaces:**
- Consumes: ProjectService, ServerStorage, existing Git snapshot/restore primitives.
- Produces project and retained-run recovery adapters.

- [ ] Write failing canonical-repo/retained-worktree round trips including `test_run_workspace_restore_rejects_project_mismatch`.
- [ ] Verify RED.
- [ ] Implement adapters with project/run identity binding.
- [ ] Verify GREEN.
- [ ] Commit `feat: extend recovery to server project workspaces`.

### Task 3: Identity and configuration backup

**Files:**
- Create: `src/ai_workshop/recovery/server_identity.py`
- Test: `tests/integration/recovery/test_server_identity.py`

**Interfaces:**
- Consumes: PrincipalService/AgentService and server configuration store.
- Produces versioned manifest backup/restore excluding secret material.

- [ ] Write failing version/checksum/scope tests including `test_identity_restore_does_not_touch_projects`.
- [ ] Verify RED.
- [ ] Implement identity/config backup adapter.
- [ ] Verify GREEN.
- [ ] Commit `feat: back up server identity and configuration`.

### Task 4: MCP registry metadata recovery

**Files:**
- Create: `src/ai_workshop/recovery/server_mcp.py`
- Test: `tests/integration/recovery/test_server_mcp.py`

**Interfaces:**
- Consumes: McpRegistry export/import metadata contract.
- Restores registrations/capabilities but not live process/container state.

- [ ] Write failing registry round-trip test including `test_mcp_registry_restore_returns_servers_stopped`.
- [ ] Verify RED.
- [ ] Implement metadata-only recovery adapter.
- [ ] Verify GREEN.
- [ ] Commit `feat: add mcp registry recovery`.

### Task 5: Optional Forgejo and persistent-state backups

**Files:**
- Create: `src/ai_workshop/recovery/adapters/forgejo.py`
- Modify: generic state-adapter registry
- Test: `tests/integration/recovery/test_forgejo_state.py`

- [ ] Write failing snapshot/restore/failure-retention tests including `test_forgejo_failed_backup_keeps_last_good_snapshot`.
- [ ] Verify RED.
- [ ] Implement Forgejo adapter using its supported database/repository backup boundary.
- [ ] Verify GREEN.
- [ ] Commit `feat: add optional forgejo recovery adapter`.

### Task 6: Server reset scopes and recovery MCP

**Files:**
- Modify: `src/ai_workshop/recovery/reset.py`
- Modify: `src/ai_workshop/gateway/recovery_tools.py`
- Test: `tests/integration/test_server_recovery_mcp.py`

- [ ] Write failing explicit-scope tests including `test_reset_scopes_exclude_secret_and_ca_state`.
- [ ] Verify RED.
- [ ] Add server-owned cache/artifacts/run-runtime scopes without any project-global/secret/CA reset shortcut.
- [ ] Expose typed domain snapshot/restore/backup tools through confirmation flow.
- [ ] Verify GREEN and full recovery suite.
- [ ] Commit `feat: expose server recovery operations`.

### Task 7: Operator backup/restore acceptance

**Files:**
- Test: `tests/e2e/test_server_backup_restore.py`

- [ ] Build an E2E state fixture containing project, identity, retained run, MCP registrations, browser artifacts, and optional Forgejo data.
- [ ] Snapshot selected domains.
- [ ] Mutate each selected domain plus an unrelated protected domain.
- [ ] Restore with explicit confirmations.
- [ ] Assert selected state is recovered and protected/unselected state is unchanged.
- [ ] Commit `test: prove scoped server backup and recovery`.
