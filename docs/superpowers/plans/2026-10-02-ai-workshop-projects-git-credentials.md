# AI Workshop Server Projects, Git & Credentials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent Git-managed projects, optional external project mounts, typed Git operations, and named SSH/HTTPS credential profiles for Server Mode.

**Architecture:** Canonical repositories live in ServerStorage. Git actions go through a typed `GitRepositoryService` with fixed argv, while secret material is provided by a separate `CredentialProvider` boundary and never copied into project worktrees.

**Tech Stack:** Python 3.12, Git CLI, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- Git-managed projects are the Server Mode default.
- External mounts remain explicit and bounded.
- Never mount or copy host `~/.ssh`.
- Secret values must not appear in command argv, ordinary MCP responses, project files, or audit payloads.
- High-risk Git operations are dedicated methods, not generic flags.
- All project-facing services expose typed Protocol contracts.

## Review Focus

- Clone destination traversal must not escape project storage; Task 1 adds `test_clone_destination_cannot_escape_project_store`.
- A credential helper failure must not leak a token/private key into stderr returned to callers; Task 2 adds `test_git_error_redacts_credentials`.
- Pull on a dirty/conflicting repository must preserve user changes; Task 3 adds `test_pull_conflict_preserves_worktree`.
- Force push must not be reachable through ordinary `push`; Task 4 adds `test_normal_push_has_no_force_option`.
- Removing project registration must not delete checkout data; Task 1 adds `test_remove_registration_keeps_checkout`.

---

### Task 1: Persistent project registry

**Files:**
- Create: `src/ai_workshop/projects/models.py`
- Create: `src/ai_workshop/projects/protocol.py`
- Create: `src/ai_workshop/projects/store.py`
- Test: `tests/unit/projects/test_store.py`

**Interfaces:**
- Produces: `ProjectService` Protocol.
- Produces: `ProjectRecord`, `GitManagedProject`, `ExternalProject`.
- Produces: `ProjectStore.register_git(...)`, `register_external(...)`, `list()`, `get()`, `remove_registration()`, `delete_checkout()`.

- [ ] **Step 1: Write failing registry/storage tests**

Cover stable IDs, duplicate IDs, external mount containment policy, `test_clone_destination_cannot_escape_project_store`, and `test_remove_registration_keeps_checkout`.

- [ ] **Step 2: Verify RED**

Run project-store tests.

- [ ] **Step 3: Implement project models and persistent registry**

Use ServerStorage from the runtime plan for canonical paths.

- [ ] **Step 4: Verify GREEN**

Run project-store tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: add persistent server project registry"`

### Task 2: Credential profiles

**Files:**
- Create: `src/ai_workshop/credentials/models.py`
- Create: `src/ai_workshop/credentials/protocol.py`
- Create: `src/ai_workshop/credentials/store.py`
- Create: `src/ai_workshop/credentials/git_env.py`
- Test: `tests/unit/credentials/test_git_credentials.py`

**Interfaces:**
- Produces: `CredentialProvider` Protocol.
- Produces: `SshCredentialProfile`, `HttpsTokenCredentialProfile`.
- Produces: `GitCredentialContext.environment() -> dict[str, str]` and cleanup lifecycle.

- [ ] **Step 1: Write failing credential-isolation tests**

Assert SSH keys/tokens are referenced by profile ID, material is outside project storage, command argv contains no secret, and `test_git_error_redacts_credentials`.

- [ ] **Step 2: Verify RED**

Run credential tests.

- [ ] **Step 3: Implement credential provider and ephemeral Git credential context**

SSH uses a controlled `GIT_SSH_COMMAND`/temporary private path owned by the service; HTTPS uses a non-interactive credential helper/context rather than embedding token in remote URL.

- [ ] **Step 4: Verify GREEN**

Run credential tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: add named git credential profiles"`

### Task 3: Safe read/update Git operations

**Files:**
- Create: `src/ai_workshop/git/protocol.py`
- Create: `src/ai_workshop/git/service.py`
- Create: `src/ai_workshop/git/models.py`
- Test: `tests/integration/git/test_repository_service.py`

**Interfaces:**
- Produces: `GitRepositoryService` with `clone/status/diff/fetch/pull/add/commit/log/branch_list/branch_create/switch/checkout/remote_list/remote_set/stash/tag`.

- [ ] **Step 1: Write failing local-remote integration tests**

Use disposable bare remotes. Cover clone, dirty status, commit, fetch/pull, branch switch, remote management, and `test_pull_conflict_preserves_worktree`.

- [ ] **Step 2: Verify RED**

Run Git integration tests.

- [ ] **Step 3: Implement fixed-argv Git service**

Every repository path comes from ProjectService; every credential comes from CredentialProvider.

- [ ] **Step 4: Verify GREEN**

Run Git integration tests.

- [ ] **Step 5: Commit**

`git commit -am "feat: add typed git repository operations"`

### Task 4: History-changing Git operations and confirmations

**Files:**
- Modify: `src/ai_workshop/git/protocol.py`
- Modify: `src/ai_workshop/git/service.py`
- Create: `src/ai_workshop/git/destructive.py`
- Test: `tests/integration/git/test_history_operations.py`

**Interfaces:**
- Adds: `merge`, `rebase`, `rebase_continue`, `rebase_abort`, `cherry_pick`.
- Produces separate gated methods: `force_push`, `hard_reset`, `delete_branch`, `delete_tag`.

- [ ] **Step 1: Write failing merge/rebase/conflict tests**

Include `test_normal_push_has_no_force_option`; prove conflicts remain inspectable and abort restores pre-operation state.

- [ ] **Step 2: Verify RED**

Run history-operation tests.

- [ ] **Step 3: Implement normal history operations**

Do not expose destructive methods through generic kwargs/options.

- [ ] **Step 4: Add confirmation-token wrappers for destructive operations**

Reuse the existing preview/confirmation design pattern.

- [ ] **Step 5: Verify GREEN and commit**

Run Git suites, then commit `feat: add gated git history operations`.

### Task 5: Project/Git MCP surface

**Files:**
- Create: `src/ai_workshop/gateway/project_tools.py`
- Create: `src/ai_workshop/gateway/git_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Test: `tests/integration/test_server_git_mcp.py`

**Interfaces:**
- Exposes typed `projects.*` and `git.*` tools without raw argv/path/credential parameters.

- [ ] **Step 1: Write failing tool-schema tests**

Assert tool schemas expose IDs and typed fields only.

- [ ] **Step 2: Verify RED**

Run MCP tests.

- [ ] **Step 3: Implement registrations**

Normalize errors and redact secrets.

- [ ] **Step 4: Verify GREEN and full regression suite**

- [ ] **Step 5: Commit**

`git commit -am "feat: expose server projects and git through MCP"`
