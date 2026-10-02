# AI Workshop Server Mode — Implementation Roadmap

**Spec:** `docs/superpowers/specs/2026-10-02-ai-workshop-server-mode-design.md`

The approved Server Mode design is intentionally implemented as independent reviewable plans rather than one monolithic branch.

## Execution Order

1. `2026-10-02-ai-workshop-server-runtime.md`
   - rootless runtime boundary
   - server-owned storage
   - workload/network policy
   - private runtime endpoint relay
   - autonomous runtime smoke profile

2. `2026-10-02-ai-workshop-projects-git-credentials.md`
   - persistent Git-managed projects
   - optional external mounts
   - SSH/HTTPS credential profiles
   - typed git operations and destructive-operation gates

3. `2026-10-02-ai-workshop-identity-agents.md`
   - principals/RBAC
   - audit
   - persistent AgentIdentity
   - bounded delegation
   - isolated AgentRun worktrees/containers

4. `2026-10-02-ai-workshop-ingress-auth-tls.md`
   - route registry
   - private runtime relay integration
   - local CA / optional ACME
   - passkeys/recovery codes
   - optional OIDC
   - scoped API/service tokens

5. `2026-10-02-ai-workshop-forge-integrations.md`
   - provider-neutral ForgeProvider
   - GitHub/GitLab/Forgejo adapters
   - optional embedded Forgejo

6. `2026-10-02-ai-workshop-dynamic-mcp-runtime.md`
   - downstream MCP registry
   - stable proxy surface
   - permission intersection
   - stdio/HTTP/container transports
   - dynamic discovery/list changes
   - optional promotion
   - AgentRun-scoped MCP lifecycle

7. `2026-10-02-ai-workshop-server-recovery-operations.md`
   - canonical repo/run recovery
   - identity/config backup
   - MCP registry recovery
   - optional Forgejo/persistent-state recovery
   - explicit Server Mode reset scopes

8. `2026-10-02-ai-workshop-server-mode-e2e-deployment.md`
   - final deployment packaging
   - idempotent bootstrap
   - restart/failure isolation
   - offline/LAN profile
   - full autonomous acceptance workflow

## Dependency Rules

- Later plans depend only on public typed contracts produced by earlier plans.
- No later plan may reach into concrete rootless-Docker, identity-store, provider, or MCP transport internals.
- Desktop Mode remains green after every plan.
- Each plan gets its own implementation branch/PR and full reviewer gate before the next dependent plan starts.
- Dynamic MCP work starts only after Runtime + Identity/AgentRun boundaries exist.
- Final deployment/E2E starts only after all functional plans are green.

## Final Acceptance

The program is complete only when the final E2E proves, from one autonomous Server Mode deployment:

```text
bootstrap admin
→ create agent
→ clone project
→ create parallel AgentRuns/worktrees
→ edit/test
→ run nested project service
→ publish through authenticated HTTPS ingress
→ inspect in Chromium
→ create/register a new MCP server
→ discover/call its tool without Workshop restart
→ commit/push
→ create forge PR
→ verify audit attribution
→ stop run and clean scoped resources
→ verify unrelated server state remains untouched
```
