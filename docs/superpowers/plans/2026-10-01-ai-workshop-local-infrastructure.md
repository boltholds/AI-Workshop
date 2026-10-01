# AI Workshop Local Infrastructure & Service Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let AI Workshop run and control arbitrary isolated local application infrastructure from declarative service profiles, without mounting the host Docker socket into agent containers; Supabase and Titan are optional example adapters/profiles.

**Architecture:** Docker lifecycle commands are owned directly by the host-side MCP/control gateway through a `ComposeController` that accepts only prevalidated service/profile IDs and emits fixed Docker Compose argv. There is no Docker control API exposed to containers and no host Docker socket mount. Generic project/service definitions are configuration-driven. Product-specific integrations such as self-hosted Supabase or Titan live as optional adapters/profiles on top of the generic service model.

**Tech Stack:** Python 3.12, Pydantic v2, Docker Compose v2 CLI, pytest, official Supabase self-hosted Docker release.

**Spec:** `docs/superpowers/specs/2026-10-01-ai-workshop-design.md`

## Global Constraints

- No container may mount the host Docker socket.
- The MCP/control gateway binds to `127.0.0.1` by default; any external connector/tunnel is configured separately.
- Service management is limited to configured compose projects/services and fixed controller operations.
- Workshop-specific credentials are stored outside Git.
- Production credentials are not required for the normal local flow.
- Individual services can be restarted/rebuilt without destroying browser state or unrelated services.
- Persistent state is declared per service/profile; no database vendor is mandatory.

## Review Focus

- A caller must not be able to pass an arbitrary compose file path or service name to the Compose controller; Task 1 adds `test_rejects_unregistered_service`.
- A caller-supplied Docker/Compose flag or shell fragment must never reach the process runner; Task 1 adds `test_rejects_caller_cli_fragments`.
- A project service with a host path outside configured projects must be rejected; Task 2 adds `test_service_build_context_must_be_registered_project`.
- Supabase vendor refresh must remain pinned and reproducible rather than silently tracking `master`; Task 3 adds `test_supabase_vendor_requires_pinned_ref`.
- Restarting Titan must not recreate the browser or database volumes; Task 4 adds `test_titan_restart_is_service_scoped`.

---

### Task 1: Host-side Compose controller

**Files:**
- Create: `src/ai_workshop/controller/registry.py`
- Create: `src/ai_workshop/controller/runner.py`
- Create: `src/ai_workshop/models/services.py`
- Test: `tests/unit/controller/test_registry.py`
- Test: `tests/unit/controller/test_runner.py`

**Interfaces:**
- Consumes: local service registry config.
- Produces: `ComposeController.list_services()`, `status(service_id)`, `logs(service_id, tail)`, `restart(service_id)`, `rebuild(service_id)`, and `up(service_id)`.

- [ ] **Step 1: Write failing registry/controller tests**

Cover registered project/service resolution, `test_rejects_unregistered_service`, rejection of caller-provided compose file overrides, bounded log line count, timeout mapping, and `test_rejects_caller_cli_fragments`.

- [ ] **Step 2: Implement immutable service registry**

Load service IDs to prevalidated compose project, working directory, compose file list, and allowed operation set. Public methods accept service IDs and typed options only, never raw Docker CLI fragments.

- [ ] **Step 3: Implement Docker Compose runner**

Generate fixed argv arrays such as `docker compose ... restart <registered-service>`; use subprocess argv directly and never execute caller-supplied shell strings.

- [ ] **Step 4: Run Task 1 tests**

Run: `uv run pytest tests/unit/controller -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_workshop/controller src/ai_workshop/models tests/unit/controller
git commit -m "feat: add bounded host compose controller"
```

### Task 2: Project service configuration and Compose generation

**Files:**
- Create: `src/ai_workshop/services/config.py`
- Create: `src/ai_workshop/services/render.py`
- Create: `config/services.example.yaml`
- Test: `tests/unit/services/test_config.py`
- Test: `tests/unit/services/test_render.py`

**Interfaces:**
- Consumes: project IDs and paths from the core plan.
- Produces: `ServiceDefinition`, `ServiceRegistryConfig`, and `render_service_override(...) -> Path`.

- [ ] **Step 1: Write failing service-config tests**

Cover build-context project references, optional Dockerfile/command/env file, ports, healthcheck, dependencies, and `test_service_build_context_must_be_registered_project`.

- [ ] **Step 2: Implement typed service configuration**

A service references a configured project ID plus a relative build context. Resolve build context with the same project boundary policy used by workspace operations.

- [ ] **Step 3: Write failing render tests**

Assert deterministic Compose output, a shared external Workshop network, named persistent volumes, and no host Docker socket.

- [ ] **Step 4: Implement service Compose renderer**

Generate `.workshop/compose.services.yaml` and a controller registry from the same validated input so execution and configuration cannot diverge.

- [ ] **Step 5: Run Task 2 tests**

Run: `uv run pytest tests/unit/services -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_workshop/services config/services.example.yaml tests/unit/services
git commit -m "feat: add configurable workshop services"
```

### Task 3: Optional infrastructure adapters and Supabase reference adapter

**Files:**
- Create: `src/ai_workshop/supabase/vendor.py`
- Create: `infrastructure/supabase/workshop.override.yaml`
- Create: `infrastructure/supabase/README.md`
- Create: `config/supabase.version`
- Test: `tests/unit/supabase/test_vendor.py`
- Test: `tests/integration/supabase/test_compose_config.py`

**Interfaces:**
- Consumes: generic service/profile model, Docker Compose, and the external Workshop network.
- Produces: an adapter contract for vendored/external stacks plus `vendor_supabase(ref: str, destination: Path) -> VendorManifest` as the first reference implementation.

- [ ] **Step 1: Write failing vendor tests**

Assert a ref is mandatory, `test_supabase_vendor_requires_pinned_ref`, manifest stores source URL/ref/content checksum, and repeat fetch of the same ref is idempotent.

- [ ] **Step 2: Implement pinned Supabase vendor command**

Set `config/supabase.version` to `self-hosted/v0.8.2`, the current official self-hosted release verified while writing this plan. Fetch only that ref into `.workshop/vendor/supabase`; never silently switch to `master`.

- [ ] **Step 3: Write failing Compose validation test**

Run `docker compose config` against the vendored official bundle plus `workshop.override.yaml`; assert the API gateway joins the external Workshop network and persistent database/storage paths stay outside Git.

- [ ] **Step 4: Implement Workshop Supabase override and local secret generation hook**

Keep generated secrets under `.workshop/secrets/supabase.env`; add that path to `.gitignore`. Do not commit generated keys.

- [ ] **Step 5: Run Task 3 tests**

Run: `uv run pytest tests/unit/supabase tests/integration/supabase -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_workshop/supabase infrastructure/supabase config/supabase.version .gitignore tests
git commit -m "feat: add pinned local supabase stack"
```

### Task 4: Generic project-service control through MCP

**Files:**
- Create: `src/ai_workshop/gateway/service_tools.py`
- Modify: `src/ai_workshop/gateway/server.py`
- Modify: `config/services.example.yaml`
- Test: `tests/integration/test_service_mcp.py`
- Test: `tests/e2e/test_service_control.py`

**Interfaces:**
- Consumes: in-process `ComposeController` from Task 1 and service registry from Task 2.
- Produces: MCP tools `services_list`, `services_status`, `services_logs`, `services_restart`, `services_rebuild`.

- [ ] **Step 1: Write failing MCP service tests**

Assert only registered services are visible/actionable, logs are bounded, and no tool parameter can inject compose files, Docker flags, or shell fragments.

- [ ] **Step 2: Implement service MCP tools**

Call the in-process `ComposeController` from the host-side gateway and map controller failures to structured MCP errors.

- [ ] **Step 3: Add generic profile examples plus optional Titan example**

Document at least one vendor-neutral multi-service profile and, separately, an optional Titan example using a dedicated `TITAN_API_TOKEN`. Keep all actual token values out of Git.

- [ ] **Step 4: Write `test_titan_restart_is_service_scoped`**

Use fixture services to assert the generated controller call is exactly a Titan restart and does not include browser/database recreation.

- [ ] **Step 5: Run Task 4 tests**

Run: `uv run pytest tests/integration/test_service_mcp.py tests/e2e/test_service_control.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ai_workshop/gateway config/services.example.yaml tests
git commit -m "feat: expose local service control through mcp"
```

### Task 5: Local infrastructure smoke test and documentation

**Files:**
- Create: `tests/e2e/test_local_infrastructure.py`
- Create: `docs/local-infrastructure.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: verified local stack boot flow and operator instructions.

- [ ] **Step 1: Write the E2E infrastructure test**

Start a fixture project service plus Postgres through the host gateway's Compose controller, verify health, restart only the fixture service, read logs, then stop the fixture stack without removing named data volumes.

- [ ] **Step 2: Add optional Supabase smoke marker**

When `AI_WORKSHOP_E2E_SUPABASE=1`, start the pinned Supabase stack and wait for the API gateway health endpoint; otherwise skip to keep the normal suite lightweight.

- [ ] **Step 3: Run E2E tests**

Run: `uv run pytest tests/e2e/test_local_infrastructure.py -v`  
Expected: PASS with Supabase test skipped unless enabled.

- [ ] **Step 4: Document host gateway control and local secrets**

Include Windows/macOS/Linux examples, loopback-only gateway model, Titan token setup, Supabase vendor/update procedure, and how to restart/rebuild one service.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_local_infrastructure.py docs/local-infrastructure.md README.md
git commit -m "docs: add local infrastructure workflow"
```
