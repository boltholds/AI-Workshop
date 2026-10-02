# AI Workshop Server Ingress, Authentication & TLS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one authenticated HTTPS ingress for Server Mode, automatic local-CA certificates, optional ACME, passkey-first local authentication, and optional OIDC federation.

**Architecture:** Internal control/browser/runtime services stay private. An `IngressService` consumes a declarative route registry and targets only controller-issued private runtime endpoints. Authentication produces principal sessions/tokens consumed by the authorization layer from the identity plan.

**Tech Stack:** Python 3.12, reverse proxy configuration generation, WebAuthn/passkeys, OIDC, X.509 local CA, pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

## Global Constraints

- No arbitrary host/port forwarding.
- Only RuntimeEndpoint values issued by Server Controller may back dynamic project routes.
- HTTPS is the normal external path.
- Local CA private material never enters AgentRun/MCP/project containers.
- First-user bootstrap is one-time and cannot be replayed.
- OIDC is optional; local passkey auth remains available.

## Review Focus

- A route target must not accept loopback/metadata/arbitrary LAN addresses; Task 1 adds `test_route_target_must_be_controller_endpoint`.
- A hostname collision must fail deterministically rather than shadow another project; Task 1 adds `test_duplicate_hostname_rejected`.
- WebAuthn challenge replay must fail; Task 4 adds `test_passkey_challenge_is_single_use`.
- Export API must never return the local CA private key; Task 3 adds `test_ca_export_returns_public_certificate_only`.
- OIDC subject/provider collisions must remain distinct identities; Task 5 adds `test_oidc_identity_key_includes_issuer_and_subject`.

---

### Task 1: Ingress route registry

**Files:**
- Create: `src/ai_workshop/ingress/models.py`
- Create: `src/ai_workshop/ingress/protocol.py`
- Create: `src/ai_workshop/ingress/registry.py`
- Test: `tests/unit/ingress/test_registry.py`

**Interfaces:**
- Produces: `IngressService.publish/unpublish/list/get`.
- Consumes: `RuntimeEndpoint` only.

- [ ] Write failing hostname/endpoint/collision tests including the two Review Focus cases.
- [ ] Verify RED.
- [ ] Implement route registry and validation.
- [ ] Verify GREEN.
- [ ] Commit `feat: add server ingress route registry`.

### Task 2: Reverse proxy adapter

**Files:**
- Create: `src/ai_workshop/ingress/proxy.py`
- Create: `server/ingress/`
- Test: `tests/integration/ingress/test_proxy.py`

**Interfaces:**
- Produces: `ProxyAdapter.apply(routes, certificates) -> None`.

- [ ] Write failing integration test with two private fixture services and dynamic publish/unpublish.
- [ ] Verify RED.
- [ ] Implement deterministic config/render/reload path without arbitrary directives.
- [ ] Verify GREEN.
- [ ] Commit `feat: add managed server ingress proxy`.

### Task 3: Local CA and certificate service

**Files:**
- Create: `src/ai_workshop/certificates/models.py`
- Create: `src/ai_workshop/certificates/protocol.py`
- Create: `src/ai_workshop/certificates/local_ca.py`
- Test: `tests/unit/certificates/test_local_ca.py`

**Interfaces:**
- Produces: `CertificateService.issue(hostname)`, `renew_due()`, `export_trust_certificate()`.

- [ ] Write failing issue/renew/export tests including `test_ca_export_returns_public_certificate_only`.
- [ ] Verify RED.
- [ ] Implement protected CA state and leaf issuance.
- [ ] Verify GREEN.
- [ ] Commit `feat: add workshop local certificate authority`.

### Task 4: Local passkey authentication

**Files:**
- Create: `src/ai_workshop/authn/models.py`
- Create: `src/ai_workshop/authn/webauthn.py`
- Create: `src/ai_workshop/authn/sessions.py`
- Test: `tests/integration/authn/test_passkeys.py`

**Interfaces:**
- Produces registration/login challenge flows and authenticated Principal ID.
- Produces recovery-code enrollment/use.

- [ ] Write failing admin-bootstrap/passkey/recovery-code tests including `test_passkey_challenge_is_single_use`.
- [ ] Verify RED.
- [ ] Implement first-admin bootstrap and WebAuthn session flow.
- [ ] Verify GREEN.
- [ ] Commit `feat: add passkey-first workshop authentication`.

### Task 5: Optional OIDC federation

**Files:**
- Create: `src/ai_workshop/authn/oidc.py`
- Test: `tests/integration/authn/test_oidc.py`

**Interfaces:**
- Produces: `OidcAuthenticator.authenticate(callback) -> PrincipalIdentity`.

- [ ] Write failing issuer/state/nonce/subject tests including `test_oidc_identity_key_includes_issuer_and_subject`.
- [ ] Verify RED.
- [ ] Implement optional configured OIDC providers.
- [ ] Verify GREEN.
- [ ] Commit `feat: add optional oidc authentication`.

### Task 6: Scoped API/service tokens and authenticated ingress

**Files:**
- Create: `src/ai_workshop/authn/tokens.py`
- Modify: ingress/control-plane wiring
- Test: `tests/e2e/test_server_ingress_auth.py`

- [ ] Write failing token scope/revocation and unauthenticated-route tests.
- [ ] Verify RED.
- [ ] Implement authenticated routing for Workshop API/MCP/admin surfaces.
- [ ] Verify local HTTPS with generated CA trust in E2E.
- [ ] Commit `feat: secure server ingress with workshop identity`.

### Task 7: ACME provider contract

**Files:**
- Create: `src/ai_workshop/certificates/acme.py`
- Test: `tests/unit/certificates/test_acme.py`

- [ ] Write failing provider-selection and renewal-state tests.
- [ ] Verify RED.
- [ ] Implement ACME as an optional CertificateService adapter.
- [ ] Verify GREEN and full regression suite.
- [ ] Commit `feat: add optional acme certificates`.
