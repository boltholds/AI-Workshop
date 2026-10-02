# AI Workshop Forge Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider-neutral forge operations for GitHub, GitLab, and Forgejo/Gitea-compatible servers, plus an optional embedded Forgejo Server Mode profile.

**Architecture:** Core forge domain code depends on a typed `ForgeProvider` Protocol. Provider credentials come from CredentialProvider; Git history/transport remains in the Git subsystem.

**Tech Stack:** Python 3.12, httpx, GitHub/GitLab/Forgejo REST APIs, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- Forge API and Git operations remain separate modules.
- No provider raw response becomes a domain model.
- Provider tokens are never returned or logged.
- Repository deletion and destructive branch-protection changes are explicitly gated.
- Embedded Forgejo is optional.

## Review Focus

- Provider pagination must not silently truncate repository/PR lists; Task 2 adds `test_provider_list_follows_pagination`.
- Rate-limit/provider outages must normalize without leaking raw response bodies; Task 2 adds `test_provider_error_is_normalized_and_redacted`.
- Two forge profiles for the same provider must stay isolated by credential/base URL; Task 1 adds `test_profiles_are_identity_scoped`.
- Embedded Forgejo disable/remove must not delete its repositories unless separately confirmed; Task 5 adds `test_disable_forgejo_preserves_data`.
- PR merge must verify repository/project binding before mutation; Task 4 adds `test_merge_rejects_repository_binding_mismatch`.

---

### Task 1: Forge domain and profile registry

**Files:**
- Create: `src/ai_workshop/forge/models.py`
- Create: `src/ai_workshop/forge/protocol.py`
- Create: `src/ai_workshop/forge/registry.py`
- Test: `tests/unit/forge/test_registry.py`

- [ ] Write failing profile/provider/binding tests including `test_profiles_are_identity_scoped`.
- [ ] Verify RED.
- [ ] Implement `ForgeProvider` Protocol and named profile registry.
- [ ] Verify GREEN.
- [ ] Commit `feat: define forge provider contracts`.

### Task 2: Shared HTTP provider client behavior

**Files:**
- Create: `src/ai_workshop/forge/http.py`
- Test: `tests/unit/forge/test_http.py`

- [ ] Write pagination, timeout, retry-bound, normalization, and redaction tests including the two Review Focus cases.
- [ ] Verify RED.
- [ ] Implement bounded HTTP client utilities.
- [ ] Verify GREEN.
- [ ] Commit `feat: add bounded forge http client`.

### Task 3: GitHub, GitLab, Forgejo adapters

**Files:**
- Create: `src/ai_workshop/forge/github.py`
- Create: `src/ai_workshop/forge/gitlab.py`
- Create: `src/ai_workshop/forge/forgejo.py`
- Test: `tests/contract/forge/test_providers.py`

**Interfaces:**
- Each adapter implements `ForgeProvider` repo/PR/issue/release/protection/webhook capabilities with explicit capability reporting.

- [ ] Write provider contract tests against fixture HTTP servers.
- [ ] Verify RED.
- [ ] Implement the three adapters.
- [ ] Verify GREEN.
- [ ] Commit `feat: add github gitlab and forgejo providers`.

### Task 4: Authorized ForgeService and MCP surface

**Files:**
- Create: `src/ai_workshop/forge/service.py`
- Create: `src/ai_workshop/gateway/forge_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Test: `tests/integration/test_forge_mcp.py`

- [ ] Write failing authorization/repository-binding/destructive-confirmation tests including `test_merge_rejects_repository_binding_mismatch`.
- [ ] Verify RED.
- [ ] Implement provider-neutral service and MCP tools.
- [ ] Verify GREEN.
- [ ] Commit `feat: expose provider neutral forge operations`.

### Task 5: Optional embedded Forgejo profile

**Files:**
- Create: `infrastructure/forgejo/compose.yaml`
- Create: `config/forgejo.example.yaml`
- Modify: server service-profile registration
- Test: `tests/e2e/test_embedded_forgejo.py`

- [ ] Write failing lifecycle/persistence tests including `test_disable_forgejo_preserves_data`.
- [ ] Verify RED.
- [ ] Implement optional Forgejo service profile and ingress registration.
- [ ] Verify repository + PR API E2E.
- [ ] Commit `feat: add optional embedded forgejo`.

### Task 6: Forge documentation and full regression

**Files:**
- Create: `docs/server/forges.md`
- Modify: `README.md`

- [ ] Document profile/credential binding and local Forgejo use.
- [ ] Run all forge/server/full tests.
- [ ] Commit `docs: document server forge integrations`.
