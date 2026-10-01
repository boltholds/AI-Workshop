# AI Workshop Recovery, Doctor & End-to-End Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit snapshot/restore/reset operations, environment diagnostics, and a full end-to-end test proving the agent can edit a real mounted project, run it, inspect it in Chromium, capture diagnostics, and leave unrelated host state untouched.

**Architecture:** Git-aware project snapshots capture the exact pre-agent worktree state without requiring a clean repository, while database snapshots use normal PostgreSQL dump/restore against the isolated Workshop database. Restore is an explicit operation with a preview and confirmation token. A `doctor` command checks the host/container control plane and produces actionable diagnostics before work begins.

**Tech Stack:** Python 3.12, Git CLI, PostgreSQL client tools, tarfile, FastAPI/MCP layers from earlier plans, pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-ai-workshop-design.md`

## Global Constraints

- Restore must never run silently; it requires an explicit restore request and confirmation token.
- Snapshot/restore may affect only configured project roots and Workshop-local database/state.
- Unrelated host files and production systems remain untouched.
- Reset of Workshop infrastructure must not implicitly reset host repositories.
- Snapshot metadata is stored in private Workshop state, not committed to Git.
- Raw internal stack traces are not returned through MCP by default.

## Review Focus

- A snapshot must preserve a repository that was already dirty before the agent started; Task 1 adds `test_snapshot_round_trip_preserves_preexisting_dirty_state`.
- Restore must refuse when the current repository identity differs from the snapshot; Task 2 adds `test_restore_rejects_different_repository`.
- New untracked files created after a snapshot must be removed only inside the restored project, never outside it; Task 2 adds `test_restore_cleans_only_project_root`.
- Database restore failure must leave the dump artifact available for manual recovery; Task 3 adds `test_failed_db_restore_keeps_dump`.
- Doctor must distinguish an unreachable MCP gateway from an unhealthy browser or controller; Task 4 adds `test_doctor_reports_component_specific_failure`.

---

### Task 1: Git-aware project snapshot capture

**Files:**
- Create: `src/ai_workshop/recovery/models.py`
- Create: `src/ai_workshop/recovery/git_snapshot.py`
- Create: `src/ai_workshop/recovery/store.py`
- Test: `tests/integration/recovery/test_git_snapshot.py`

**Interfaces:**
- Consumes: configured project roots and Git service.
- Produces: `GitSnapshotService.create(project_id: str) -> SnapshotManifest`.

- [ ] **Step 1: Write failing snapshot tests**

Create temporary repositories covering clean state, staged changes, unstaged changes, untracked files, binary untracked files, and `test_snapshot_round_trip_preserves_preexisting_dirty_state`.

- [ ] **Step 2: Implement snapshot manifest/store**

Store repository identity, branch, HEAD, staged binary patch, unstaged binary patch, untracked-file archive, and file hashes under `.workshop/snapshots/<snapshot-id>/<project-id>/`.

- [ ] **Step 3: Run snapshot tests**

Run: `uv run pytest tests/integration/recovery/test_git_snapshot.py -v`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/ai_workshop/recovery tests/integration/recovery
git commit -m "feat: capture git-aware workspace snapshots"
```

### Task 2: Explicit project restore with preview/confirmation

**Files:**
- Create: `src/ai_workshop/recovery/restore.py`
- Create: `src/ai_workshop/models/recovery.py`
- Test: `tests/integration/recovery/test_restore.py`

**Interfaces:**
- Consumes: `SnapshotManifest` from Task 1.
- Produces: `RestoreService.preview(snapshot_id) -> RestorePreview`, `RestoreService.prepare(snapshot_id) -> ConfirmationToken`, `RestoreService.restore(snapshot_id, token) -> RestoreResult`.

- [ ] **Step 1: Write failing restore tests**

Cover clean round trip, dirty round trip, branch/HEAD restoration, `test_restore_rejects_different_repository`, `test_restore_cleans_only_project_root`, missing/expired confirmation token, and files changed outside the project root.

- [ ] **Step 2: Implement preview and confirmation**

Preview reports files that will be reset/deleted/restored. Confirmation token is short-lived, bound to snapshot ID and preview digest, and stored only in Workshop state.

- [ ] **Step 3: Implement restore**

Restore only after token verification: checkout recorded branch/HEAD, clean only the configured project root, reapply recorded staged/unstaged patches, and unpack recorded untracked files with path traversal protection.

- [ ] **Step 4: Run Task 2 tests**

Run: `uv run pytest tests/integration/recovery/test_restore.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_workshop/recovery/restore.py src/ai_workshop/models/recovery.py tests/integration/recovery
git commit -m "feat: add explicit workspace restore"
```

### Task 3: PostgreSQL snapshot/restore and scoped Workshop reset

**Files:**
- Create: `src/ai_workshop/recovery/database.py`
- Create: `src/ai_workshop/recovery/reset.py`
- Test: `tests/integration/recovery/test_database.py`
- Test: `tests/unit/recovery/test_reset.py`

**Interfaces:**
- Consumes: local database connection config.
- Produces: `DatabaseSnapshotService.dump(name) -> ArtifactRef`, `DatabaseSnapshotService.restore(artifact, token) -> RestoreResult`, `ResetService.plan(scope) -> ResetPlan`, `ResetService.execute(plan, token) -> ResetResult`.

- [ ] **Step 1: Write failing database tests**

Use a disposable Postgres fixture. Assert dump/restore round trip, invalid dump failure, explicit confirmation, and `test_failed_db_restore_keeps_dump`.

- [ ] **Step 2: Implement PostgreSQL dump/restore**

Use `pg_dump` and `pg_restore`/psql through fixed argv and Workshop-local connection settings. Preserve dump files regardless of restore result.

- [ ] **Step 3: Write failing reset tests**

Assert scopes `cache`, `browser-artifacts`, `database`, and `infrastructure` never include host project directories. There is no implicit `projects` reset scope.

- [ ] **Step 4: Implement scoped reset**

Require the same preview/confirmation pattern as project restore for destructive database/infrastructure reset operations.

- [ ] **Step 5: Run Task 3 tests**

Run: `uv run pytest tests/integration/recovery/test_database.py tests/unit/recovery/test_reset.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_workshop/recovery tests
git commit -m "feat: add database recovery and scoped reset"
```

### Task 4: Doctor diagnostics and recovery MCP tools

**Files:**
- Create: `src/ai_workshop/doctor.py`
- Create: `src/ai_workshop/gateway/recovery_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Modify: `src/ai_workshop/cli.py`
- Test: `tests/unit/test_doctor.py`
- Test: `tests/integration/test_recovery_mcp.py`

**Interfaces:**
- Consumes: gateway, browser, controller, database, and configured project state.
- Produces: CLI `ai-workshop doctor`; MCP tools `workspace_snapshot_create`, `workspace_snapshot_preview_restore`, `workspace_snapshot_prepare_restore`, `workspace_snapshot_restore`, `database_snapshot_create`, and scoped reset tools.

- [ ] **Step 1: Write failing doctor tests**

Cover all healthy, missing project path, Docker unavailable, controller unavailable, gateway unavailable, browser unhealthy, database unhealthy, and `test_doctor_reports_component_specific_failure`.

- [ ] **Step 2: Implement doctor**

Return per-component status with remediation text. Exit non-zero only when required core components are unhealthy; optional services are reported separately.

- [ ] **Step 3: Write failing recovery MCP tests**

Assert snapshot creation, preview, confirmation-token flow, restore, and that destructive operations cannot be invoked with a Boolean shortcut such as `confirm=true`.

- [ ] **Step 4: Implement recovery MCP tools**

Expose structured manifests/previews/results while keeping snapshot storage paths and internal stack traces private unless explicit debugging tools request them.

- [ ] **Step 5: Run Task 4 tests**

Run: `uv run pytest tests/unit/test_doctor.py tests/integration/test_recovery_mcp.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_workshop/doctor.py src/ai_workshop/gateway src/ai_workshop/cli.py tests
git commit -m "feat: add workshop recovery controls and doctor"
```

### Task 5: Full end-to-end Workshop workflow

**Files:**
- Create: `tests/fixtures/sample_project/`
- Create: `tests/e2e/test_full_workshop.py`
- Create: `docs/workflows/debug-ui.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all previous plans.
- Produces: one executable acceptance test for the architecture success criteria.

- [ ] **Step 1: Create the deterministic sample project fixture**

The fixture must include a tiny HTTP application with a deliberate moving-element UI behavior, a unit test, and a Git repository initialization helper.

- [ ] **Step 2: Write the failing full E2E test**

Through MCP only: list mounted project, create a snapshot, edit a source file, run its tests, start/restart the fixture service, navigate Chromium, exercise the UI, capture screenshot/video/both temporal composites, inspect Git diff, restore the snapshot, and verify the original host fixture state is recovered.

- [ ] **Step 3: Add isolation assertions**

Create an adjacent host file outside the mounted project and assert its hash never changes during the E2E workflow. Assert no production-style external URL is contacted by the fixture scenario.

- [ ] **Step 4: Run the full E2E test**

Run: `uv run pytest tests/e2e/test_full_workshop.py -v`  
Expected: PASS.

- [ ] **Step 5: Write the first real workflow guide**

Document the intended operator flow: `doctor -> snapshot -> reproduce -> edit -> test -> browser diagnostics -> git diff -> keep or restore`.

- [ ] **Step 6: Run the entire repository suite**

Run: `uv run pytest -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures tests/e2e docs/workflows README.md
git commit -m "test: prove full ai workshop workflow"
```
