# AI Workshop Server Mode Deployment & Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package all Server Mode subsystems into one autonomous deployment and prove the complete workflow with deterministic end-to-end acceptance tests.

**Architecture:** Compose packages control plane, ingress, browser, rootless runtime, persistent storage, and optional profiles. The acceptance suite uses only public Server Mode APIs/MCP plus controlled bootstrap hooks; it must not depend on host-side Workshop processes.

**Tech Stack:** Docker Compose, Python 3.12, pytest, Playwright/Chromium, local fixture Git/forge services.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- One deployment command starts required Server Mode components.
- No host-side gateway/control process is required after deployment.
- No host Docker socket is mounted.
- Public exposure goes through authenticated TLS ingress.
- Optional Forgejo and external OIDC remain optional.
- Desktop Mode CI remains green.

## Review Focus

- Fresh bootstrap after partial prior failure must be idempotent; Task 2 adds `test_server_bootstrap_recovers_from_partial_initialization`.
- Restarting the outer deployment must preserve projects, identities, browser profile, and rootless state; Task 3 adds `test_restart_preserves_all_persistent_domains`.
- A failed nested service must not make auth/control plane unavailable; Task 3 adds `test_project_service_failure_is_isolated`.
- A full E2E must prove no unrelated outer-host file is modified; Task 4 adds `test_server_e2e_does_not_touch_unmounted_host_file`.
- Offline/LAN mode must not require a public forge/OIDC after images are present; Task 5 adds `test_offline_profile_has_no_required_public_dependencies`.

---

### Task 1: Server deployment manifest

**Files:**
- Create: `deploy/server/compose.yaml`
- Create: `deploy/server/.env.example`
- Create: `deploy/server/config/`
- Modify: `README.md`
- Test: `tests/unit/server/test_deployment_manifest.py`

- [ ] Write failing manifest security/dependency tests.
- [ ] Verify RED.
- [ ] Assemble required services from previous plans into one deployment.
- [ ] Verify GREEN.
- [ ] Commit `feat: package ai workshop server mode`.

### Task 2: Idempotent server bootstrap

**Files:**
- Create: `src/ai_workshop/server/bootstrap.py`
- Create: `scripts/server-bootstrap.sh`
- Create: `scripts/server-bootstrap.ps1`
- Test: `tests/integration/server/test_bootstrap.py`

- [ ] Write failing first-admin/local-CA/storage initialization tests including `test_server_bootstrap_recovers_from_partial_initialization`.
- [ ] Verify RED.
- [ ] Implement idempotent bootstrap with no secret rotation on rerun.
- [ ] Verify GREEN.
- [ ] Commit `feat: add idempotent server bootstrap`.

### Task 3: Restart/failure isolation acceptance

**Files:**
- Test: `tests/e2e/test_server_restart.py`

- [ ] Build fixtures for persistent project, identity, browser state, and nested service.
- [ ] Add `test_restart_preserves_all_persistent_domains`.
- [ ] Add `test_project_service_failure_is_isolated`.
- [ ] Run E2E and fix subsystem integration defects only through their owning interfaces.
- [ ] Commit `test: prove server restart and failure isolation`.

### Task 4: Full autonomous Server Mode E2E

**Files:**
- Create: `tests/e2e/test_full_server_mode.py`
- Create: `tests/fixtures/server_mode/`

- [ ] Write the complete failing acceptance scenario from Spec §28.
- [ ] Include two parallel AgentRuns with independent worktrees.
- [ ] Include dynamic MCP server creation/call without Workshop restart.
- [ ] Include Git push + forge PR + audit attribution.
- [ ] Include `test_server_e2e_does_not_touch_unmounted_host_file`.
- [ ] Run until fully green.
- [ ] Commit `test: prove autonomous ai workshop server mode`.

### Task 5: Offline/LAN profile

**Files:**
- Create: `deploy/server/offline.example.yaml`
- Test: `tests/unit/server/test_offline_profile.py`

- [ ] Write `test_offline_profile_has_no_required_public_dependencies`.
- [ ] Verify RED.
- [ ] Implement offline configuration with local CA and no mandatory public forge/OIDC.
- [ ] Verify GREEN.
- [ ] Commit `feat: add offline lan server profile`.

### Task 6: Operator documentation and final verification

**Files:**
- Create: `docs/server/deployment.md`
- Create: `docs/server/security-model.md`
- Create: `docs/server/backup-recovery.md`
- Modify: `README.md`

- [ ] Document deploy/bootstrap/upgrade/backup/recovery and trust boundaries.
- [ ] Run `uv run pytest -v`.
- [ ] Run every Server Mode Docker E2E workflow.
- [ ] Verify Desktop Mode CI is still green.
- [ ] Run a secret/path/socket scan over deployment manifests.
- [ ] Commit `docs: document autonomous server mode operations`.
