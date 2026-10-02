# AI Workshop Server Mode — Architecture Design

Date: 2026-10-02  
Status: Approved

## 1. Purpose

AI Workshop Server Mode turns AI Workshop from a workstation-oriented sandbox into a self-contained development server that can run continuously on a LAN server, homelab machine, NAS-capable host, or private VM.

The target deployment should require only a container runtime, persistent storage, and network access appropriate to the selected configuration. Normal operation must not require a host-side AI Workshop process, a host Docker socket mounted into agent containers, or source-code folders from a developer laptop.

Desktop Mode remains supported. Server Mode is an additional deployment model rather than a replacement.

## 2. Success Criteria

A fresh Server Mode deployment is successful when an administrator can:

1. start AI Workshop with a single deployment command;
2. authenticate through the Workshop ingress;
3. clone or attach a project;
4. create persistent or ephemeral agent identities;
5. launch isolated agent runs against independent Git workspaces;
6. edit, test, build, commit, pull, rebase, and push code;
7. create and manage remote forge repositories and pull requests;
8. start arbitrary project service stacks without access to the host Docker socket;
9. use persistent Chromium and browser diagnostics;
10. install and hot-plug additional MCP servers without restarting Workshop;
11. expose only explicitly published routes through one authenticated TLS ingress;
12. recover project and persistent service state using explicit snapshot/restore flows;
13. operate fully inside a private LAN without mandatory public-cloud dependencies.

## 3. Deployment Modes

AI Workshop supports two first-class modes.

### 3.1 Desktop Mode

Desktop Mode preserves the current architecture:

- project source normally comes from explicit host bind mounts;
- the MCP gateway and bounded Docker Compose controller run on the host;
- workspace and browser APIs remain host-loopback only;
- the host Docker socket is not mounted into Workshop containers.

### 3.2 Server Mode

Server Mode is autonomous:

- the public control plane runs inside the Workshop deployment;
- project repositories live in persistent Workshop-managed storage by default;
- project runtime services run through a Workshop-owned rootless Docker engine;
- no host-side gateway is required;
- no host Docker socket is mounted into Workshop;
- external project mounts remain optional.

The two modes should share domain models and public capability contracts wherever possible.

## 4. Server Mode Topology

The logical topology is:

```text
                         LAN / Secure MCP Tunnel
                                  |
                                  v
                         +-------------------+
                         | Workshop Ingress  |
                         | TLS + Auth        |
                         +---------+---------+
                                   |
                    +--------------+--------------+
                    |                             |
                    v                             v
             +-------------+              +--------------+
             | MCP Gateway |              | Web/API      |
             +------+------+              | Control Plane|
                    |                     +------+-------+
                    +-------------+--------------+
                                  |
                                  v
                         +-------------------+
                         | Server Controller |
                         +---+----+----+-----+
                             |    |    |
              +--------------+    |    +------------------+
              |                   |                       |
              v                   v                       v
       Project/Git Store      MCP Registry         Rootless Docker
              |                   |                  Engine
              |                   |                       |
              v                   v                       v
       Agent worktrees      MCP runtimes          AgentRun containers
                                                     Project services
                                                     Optional Forgejo
                                                     Other adapters

                         +-------------------+
                         | Browser Runtime   |
                         +-------------------+
```

Internal APIs and runtimes communicate through private networks. Only routes explicitly registered with the ingress become externally reachable.

## 5. Rootless Container Runtime

Server Mode uses a dedicated rootless Docker-compatible engine to run dynamic development workloads.

The engine is an implementation detail behind the Server Controller.

### 5.1 Trust boundary

The following are prohibited by default:

- mounting the host `/var/run/docker.sock`;
- giving AgentRun containers the rootless engine socket;
- exposing an unrestricted Docker API to MCP;
- allowing callers to provide arbitrary raw Docker CLI fragments.

Only the Server Controller owns lifecycle access to the rootless engine.

Agents and users interact through bounded typed operations such as:

- `runs.start`
- `runs.stop`
- `services.up`
- `services.restart`
- `services.rebuild`
- `services.logs`
- `mcp.server_start`
- `mcp.server_stop`

The controller validates image, mount, network, resource, and permission policies before creating containers.

### 5.2 Persistence and storage visibility

Rootless engine state is persistent across Workshop restarts.

Project source, Git metadata, agent identity state, browser state, audit logs, recovery artifacts, and credential metadata use separate storage domains so infrastructure resets cannot silently destroy repositories.

Server-owned project/run storage is mounted at a stable path into both the Server Controller and the rootless engine service. The controller creates canonical repositories and run worktrees there; the rootless daemon sees the same paths and may bind only the selected run workspace into the corresponding child container.

This shared storage is Workshop-owned persistent storage, not an arbitrary host path. AgentRun containers never receive the whole project store, only their explicitly assigned workspace and other explicitly declared volumes.

The rootless engine control socket is shared only with the Server Controller through a dedicated private socket volume. It is not mounted into AgentRun, MCP runtime, browser, ingress, Forgejo, or project-service containers.

## 6. Project Sources and Storage

Server Mode supports two project source modes.

### 6.1 Git-managed projects — default

Workshop clones repositories into persistent project storage and owns their local checkout lifecycle.

Representative operations:

- `projects.clone`
- `projects.create`
- `projects.open`
- `projects.list`
- `projects.archive`
- `projects.remove_registration`
- `projects.delete_checkout`

Deleting an actual checkout is a destructive operation and requires explicit confirmation.

### 6.2 External mounts

Administrators may register external storage such as:

- host bind mounts;
- NFS;
- SMB/CIFS;
- NAS-backed paths;
- pre-mounted server directories.

External mounts remain explicit and scoped. Workshop must not scan or mount arbitrary host paths.

### 6.3 Project identity

A project has a stable Workshop ID independent of its current Git remote URL or filesystem path.

A project may have:

- one primary repository;
- additional repositories/submodules;
- one or more forge bindings;
- service profiles;
- credential profiles;
- project memberships;
- project-scoped MCP servers.

## 7. Git Capability Layer

Git is a first-class typed capability rather than only a shell command.

The initial `git.*` surface includes:

- `git.clone`
- `git.status`
- `git.diff`
- `git.add`
- `git.commit`
- `git.fetch`
- `git.pull`
- `git.push`
- `git.branch_list`
- `git.branch_create`
- `git.switch`
- `git.checkout`
- `git.merge`
- `git.rebase`
- `git.rebase_continue`
- `git.rebase_abort`
- `git.cherry_pick`
- `git.stash`
- `git.tag`
- `git.log`
- `git.remote_list`
- `git.remote_set`
- `git.worktree_list`

The implementation uses fixed argv construction and does not expose a raw Git argument pass-through as the normal MCP surface.

High-risk operations are explicit capabilities, not flags hidden in generic operations. Examples include:

- force push;
- hard reset;
- branch deletion;
- tag deletion;
- history rewriting of a published branch.

These operations require dedicated permissions and confirmation policies.

## 8. Git Credentials

Workshop supports both SSH and HTTPS credentials.

SSH is the preferred default.

Credential material is stored separately from project storage and AgentRun workspaces.

Example logical profiles:

```text
credentials/
├── github-personal   -> SSH
├── github-work       -> SSH
├── gitlab-company    -> HTTPS token
└── forge-internal    -> SSH
```

Projects and forge profiles reference a credential profile by ID.

Workshop never requires mounting the host user's `~/.ssh`.

Private keys, tokens, and passphrases must not be returned through ordinary MCP read operations or written into project worktrees.

## 9. Forge Capability Layer

Forge hosting APIs are distinct from Git transport/history operations.

The provider-neutral `forge.*` layer initially supports:

- repository create/get/list/fork/archive;
- repository deletion as an explicitly destructive action;
- pull/merge request create/get/list/update/merge;
- issue create/get/list/update;
- release create/get/list;
- branch protection;
- repository metadata;
- webhook management where supported.

Provider adapters implement a common `ForgeProvider` contract.

Initial target providers:

- GitHub;
- GitLab;
- Forgejo/Gitea-compatible APIs.

A deployment may configure multiple named forge profiles simultaneously.

## 10. Optional Embedded Forgejo

Server Mode may enable an embedded Forgejo profile.

Forgejo is optional and is not a core runtime dependency.

When enabled it provides:

- local repository hosting;
- branches and tags;
- pull requests;
- issues;
- release APIs;
- web UI;
- a fully local forge when public internet access is unavailable or undesirable.

Forgejo should integrate with Workshop Identity through OIDC or another bounded federation mechanism when supported, avoiding a separate user lifecycle where practical.

## 11. Unified Ingress

Server Mode exposes one managed ingress rather than scattering dynamic ports across the server.

Representative routes:

```text
https://workshop.local
https://forge.workshop.local
https://app.workshop.local
https://api-app.workshop.local
```

The base domain is configurable and must not be hardcoded in domain logic.

The ingress route registry is declarative.

Example:

```yaml
routes:
  forge:
    host: forge.workshop.local
    target:
      service: forgejo
      port: 3000

  app:
    host: app.workshop.local
    target:
      service: my-app
      port: 8080
```

Service publication and removal update the route registry through controlled operations.

Internal-only services receive no external route.

Databases, rootless engine control sockets, workspace private APIs, browser control APIs, and internal MCP transports remain private by default.

### 11.1 Runtime-to-ingress bridge

Project services created by the nested rootless engine are not attached directly to the outer deployment network.

When an authorized service is published, the Server Controller allocates a private runtime endpoint on the rootless-engine service and binds the child service only to that endpoint. The ingress route targets this private endpoint through the Workshop server network.

The allocated endpoint:

- is not bound to the server LAN interface;
- is reachable only by authorized Workshop infrastructure such as ingress and diagnostics;
- is removed when the route/service is unpublished;
- is tracked as part of the service/route lifecycle;
- cannot be chosen as an arbitrary host port by an agent.

This gives the ingress access to explicitly published nested services without exposing the inner Docker network or creating a general port-forwarding primitive.

## 12. Workshop Identity

Server Mode introduces a unified identity boundary in front of administrative and agent-facing capabilities.

Authentication methods:

- passkeys/WebAuthn as the preferred interactive login;
- recovery codes;
- scoped API/service tokens;
- optional external OIDC providers.

The first local user may bootstrap the deployment as administrator through a one-time initialization flow.

Authentication material is independent from Git/forge credentials.

## 13. TLS and Local PKI

Server Mode supports autonomous HTTPS on a private LAN.

### 13.1 Local CA

Workshop may create a local certificate authority and automatically issue certificates for configured Workshop routes.

The CA private key is stored in a dedicated private state domain with encryption at rest when the configured secret backend supports it. The key is never exposed to AgentRun containers, MCP runtimes, project services, or ordinary filesystem APIs.

Administrators can export only the public trust certificate for installation on trusted client devices. Exporting or rotating CA private material is a separate administrative recovery operation and is not part of normal Workshop APIs.

### 13.2 External ACME

Deployments with a real DNS domain may use ACME-compatible certificate issuance instead of the local CA.

Both modes share the same ingress route model.

HTTP should redirect to HTTPS when HTTP is enabled at all.

## 14. Principals and Authorization

Authorization is based on principals rather than users alone.

```text
Principal
├── User
├── Agent
├── ServiceAccount
└── ExternalIdentity
```

Every auditable action has an actor principal.

Initial human-friendly roles may include:

- `admin`
- `developer`
- `viewer`

Roles are not limited to users. Agents and service accounts may receive the same role system or narrower custom roles.

Authorization combines:

1. global role grants;
2. project membership;
3. resource-specific scopes;
4. run-time delegated permissions.

## 15. Agent Identity Model

Persistent agents are first-class entities.

```text
AgentIdentity
├── id
├── name
├── owner_principal
├── roles
├── project_memberships
├── scopes
├── configuration
├── persistent_state_reference
└── audit_history
```

Workshop also supports ephemeral agent identities for one-off tasks.

Persistent identity is separate from execution runtime.

## 16. AgentRun Isolation

Each AgentRun receives its own isolated runtime container.

```text
AgentRun
├── run_id
├── agent_id
├── task
├── project_id
├── workspace_id
├── effective_permissions
├── runtime/container
├── resource_limits
├── lifecycle
├── artifacts
└── logs
```

Parallel agents do not share one mutable shell/runtime container.

### 16.1 Git workspaces

Parallel runs receive independent project workspaces, preferably Git worktrees or equivalent copy-on-write workspaces.

The canonical project repository remains persistent.

A run workspace may be:

- read-only;
- writable;
- based on a branch;
- based on a detached commit;
- disposable after completion;
- retained for review.

Merging results into another branch is an explicit Git operation.

### 16.2 Delegation

An agent may delegate a task to another agent only within its own effective authority.

The invariant is:

```text
delegated_permissions ⊆ delegator_effective_permissions
```

A child run can be more restricted than its parent but never more privileged.

## 17. Audit Model

Security-sensitive and mutating operations are auditable.

Example:

```text
actor: agent:titan
owner: user:gracie
run: run_184
project: plc-web
action: git.push
resource: origin/feat/foo
result: success
```

Audit records should include:

- actor principal;
- delegated-from principal/run when applicable;
- project/resource;
- operation;
- timestamp;
- outcome;
- approval/confirmation reference when required.

Secret values and sensitive command output must not be copied into audit records.

## 18. Hot-Pluggable MCP Runtime

Workshop exposes one stable upstream MCP Gateway while maintaining a dynamic registry of downstream MCP servers.

This allows MCP integrations to be installed, started, stopped, removed, discovered, and called without restarting the Workshop control plane.

### 18.1 Stable proxy surface

The stable public surface includes capabilities such as:

- `mcp.servers_list`
- `mcp.server_get`
- `mcp.server_add`
- `mcp.server_start`
- `mcp.server_stop`
- `mcp.server_remove`
- `mcp.tools_list`
- `mcp.tool_call`
- `mcp.resources_list`
- `mcp.resource_read`
- `mcp.prompts_list`
- `mcp.prompt_get`

New downstream servers do not require changing the upstream public tool schema when accessed through this stable proxy.

### 18.2 Supported downstream transports

The architecture supports:

- stdio;
- Streamable HTTP;
- Unix socket/internal socket transport where useful;
- containerized MCP runtimes.

Stdio MCP processes execute in isolated managed runtimes, not as unrestricted host processes.

Remote HTTP MCP endpoints require explicit network policy and must not create an unrestricted SSRF primitive.

### 18.3 Container MCP runtime

A project or agent may define an MCP server backed by a container image.

Example:

```yaml
mcp_servers:
  blender:
    transport: container
    image: example/blender-mcp@sha256:...
    permissions:
      - artifacts.write
      - project.assets.read

  local-script:
    transport: stdio
    command:
      - python
      - -m
      - my_mcp
```

Image policy may require an immutable digest, trusted registry, or explicit administrator approval depending on deployment policy.

### 18.4 Agent-created MCP servers

An AgentRun may:

1. create MCP server source code;
2. build/package it inside permitted build infrastructure;
3. register it with the MCP Runtime Registry;
4. start it;
5. discover its tools/resources/prompts;
6. call it immediately through the stable proxy.

Workshop itself does not restart for this flow.

### 18.5 Dynamic capability refresh

The registry tracks downstream MCP capability changes and refreshes cached tool/resource/prompt metadata.

When downstream MCP change notifications are available they should be used; otherwise the registry may refresh on reconnect or explicit discovery.

Internal Workshop agents receive updated registry state without restarting their AgentRun when policy allows.

## 19. MCP Promotion

A downstream MCP capability may optionally be promoted to the upstream top-level MCP surface.

Example logical operation:

```text
mcp.tool_promote(
  server="blender",
  tool="render",
  public_name="blender_render"
)
```

Promotion is separate from ordinary `mcp.tool_call`.

The stable proxy remains the compatibility path for clients that snapshot top-level tools.

Promotion requires a permission such as `mcp.promote` and must handle name collisions deterministically.

Client applications may require an explicit refresh before newly promoted top-level capabilities appear. Workshop must not depend on immediate client-side dynamic discovery for correctness.

## 20. MCP Security and Permission Intersection

An MCP server never escapes the authority of the principal/run that invokes it.

The effective permission set for a downstream call is bounded by all relevant scopes.

At minimum:

```text
effective_mcp_permissions
  ⊆ caller_effective_permissions
  ∩ mcp_server_permissions
  ∩ project_permissions
  ∩ deployment_policy
```

An agent with read-only project access cannot gain write access by installing or calling an MCP server.

Credential profiles are passed only when explicitly bound to that MCP server and allowed by policy.

MCP server installation/removal, global registration, image execution, credential attachment, and top-level promotion are separately permissioned operations.

## 21. MCP Registry Ownership

An MCP server registration has explicit ownership and scope.

```text
McpServer
├── id
├── owner_principal
├── scope
│   ├── run
│   ├── project
│   ├── user
│   └── global
├── project_id
├── transport
├── runtime_spec
├── credential_profile
├── declared_permissions
├── discovered_capabilities
├── health
└── lifecycle
```

Run-scoped MCP servers are automatically stopped and cleaned up with the AgentRun unless explicitly promoted to a longer-lived scope by an authorized principal.

## 22. Network Policy

Server Mode requires explicit outbound and inbound network policy.

Default principles:

- internal control APIs are private;
- project services are private until published;
- AgentRuns receive only required networks;
- MCP runtimes receive only required networks;
- HTTP MCP registration cannot target arbitrary host metadata/control endpoints;
- ingress is the normal path for LAN exposure;
- Secure MCP Tunnel is the preferred path for ChatGPT access without public inbound exposure.

A deployment may operate entirely without public internet after required images/dependencies are available locally.

## 23. Browser Runtime

The existing persistent Chromium/browser diagnostics architecture remains available in Server Mode.

Browser identity/profile state is Workshop-owned persistent state.

Browser control is not directly exposed through LAN ingress; it is accessed through authenticated Workshop capabilities.

Published project routes allow the browser to test the same ingress-visible application endpoints a human user would use.

## 24. Recovery

Existing project snapshot/restore semantics remain.

Server Mode extends recovery targets to include:

- canonical project repositories;
- run worktrees where retention is requested;
- Forgejo state when enabled;
- rootless runtime state where appropriate;
- generic persistent-state adapters;
- identity/configuration backups;
- MCP registry metadata.

Destructive recovery remains preview + confirmation-token gated.

Reset scopes must remain explicit. There is no global implicit "wipe all projects" operation.

## 25. Configuration Model

Server Mode configuration is declarative and split by concern.

Representative structure:

```text
config/
├── server.yaml
├── auth.yaml
├── ingress.yaml
├── projects.yaml
├── services.yaml
├── recovery.yaml
├── forges.yaml
├── credentials.yaml        # references only, no raw secrets in Git
└── mcp.yaml
```

Secrets live in a secret backend/private state mechanism rather than these committed files.

All core configuration models use typed variants. Generic untyped attribute bags are avoided in domain models.

## 26. API Boundaries

Each functional subsystem exposes a typed internal protocol/interface rather than concrete storage or implementation classes.

Expected module boundaries include:

- `IdentityService`
- `AuthorizationService`
- `ProjectService`
- `GitService`
- `ForgeService`
- `RunService`
- `ServiceController`
- `IngressService`
- `CertificateService`
- `CredentialService`
- `McpRegistry`
- `RecoveryService`
- `AuditService`

Neighboring modules depend on these contracts rather than internal database models or provider-specific implementations.

## 27. Error Handling

Public MCP/API surfaces return normalized structured errors.

Internal stack traces, credentials, engine errors containing secret data, and raw provider responses are not returned by default.

Representative error categories include:

- authentication required;
- permission denied;
- resource not found;
- policy rejected;
- project conflict;
- Git conflict/rebase required;
- forge provider unavailable;
- runtime unavailable;
- MCP server unhealthy;
- MCP capability changed;
- confirmation required;
- destructive action rejected.

## 28. Testing Strategy

Server Mode requires dedicated tests beyond Desktop Mode.

### Unit tests

- RBAC/effective-permission intersection;
- agent delegation subset invariant;
- Git fixed-argv operations;
- credential redaction;
- forge provider contracts;
- route policy;
- certificate state models;
- MCP registry lifecycle;
- MCP permission intersection;
- promotion/name-collision behavior.

### Integration tests

- rootless runtime lifecycle without host Docker socket;
- Git clone/commit/pull/rebase/push against disposable local remotes;
- isolated worktrees for concurrent AgentRuns;
- Forgejo repository/PR flow;
- passkey/OIDC boundary components where automatable;
- ingress route publication/removal;
- local CA certificate issuance;
- downstream stdio/HTTP/container MCP registration and hot-plug;
- downstream tool-list refresh.

### End-to-end acceptance

A deterministic Server Mode E2E must prove:

1. deploy Server Mode;
2. bootstrap admin;
3. create/register an agent;
4. clone a sample repository using a named credential profile;
5. start two parallel isolated AgentRuns;
6. edit and test independent worktrees;
7. start a project service through the rootless runtime;
8. publish it through ingress;
9. inspect it with Chromium;
10. create/start a new MCP server during a run;
11. call a newly discovered MCP tool without restarting Workshop;
12. commit and push a branch;
13. create a forge pull request;
14. verify audit attribution;
15. stop the run and clean run-scoped resources;
16. verify canonical project state and unrelated server state remain intact.

## 29. Migration and Compatibility

Desktop Mode remains functional throughout Server Mode development.

Existing public capability names should be reused where semantics match.

Server-only capabilities are additive.

The existing host-side gateway/controller remains the Desktop Mode control plane. Server Mode introduces an in-deployment controller with the same bounded lifecycle philosophy.

No migration may require mounting the host Docker socket into AgentRun, MCP runtime, browser, or workspace containers.

## 30. Non-Goals for Initial Server Mode

The initial Server Mode does not require:

- Kubernetes;
- cluster federation across multiple physical servers;
- arbitrary privileged containers;
- unrestricted raw Docker API access;
- enterprise SCIM provisioning;
- complex ABAC policy languages;
- automatic public DNS management for arbitrary DNS providers;
- mandatory Forgejo;
- mandatory public internet;
- mandatory external OIDC.

These can be added later behind stable subsystem contracts.

## 31. Recommended Implementation Order

The implementation should be staged so each layer remains usable and testable:

1. Server Controller + rootless runtime boundary.
2. Persistent project store + Git-managed projects.
3. Full typed `git.*` operations and credential profiles.
4. Principal/RBAC foundation.
5. AgentIdentity + isolated AgentRun/worktree lifecycle.
6. Unified ingress + TLS/local CA.
7. Forge provider abstraction + GitHub/GitLab adapters.
8. Optional embedded Forgejo.
9. Workshop Auth passkeys + optional OIDC federation.
10. Hot-pluggable MCP Runtime Registry + stable proxy.
11. MCP promotion and dynamic capability refresh.
12. Full Server Mode E2E and deployment/bootstrap packaging.

This order intentionally establishes isolation and authorization before exposing dynamic MCP/container extensibility.
