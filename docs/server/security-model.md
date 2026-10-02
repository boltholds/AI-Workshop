# Server Mode security model

Server Mode treats the outer deployment as the trust boundary around a rootless nested runtime.

The host Docker socket is never mounted. AgentRun, project-service, browser, Forgejo and MCP workloads cannot access the nested runtime control socket. Nested workloads cannot request host PID/network namespaces, privileged mode, arbitrary devices, or mounts outside assigned Workshop storage.

External exposure is limited to explicit ingress routes. Authentication is passkey-first with optional OIDC and scoped service tokens. LAN/offline deployments use the local CA and do not require public OIDC, ACME or a public forge.

Agent permissions, downstream MCP permissions, project policy and deployment policy are intersected before downstream tool calls. Run-scoped MCP servers are cleaned with their owning run, including reconciliation of failed runs.

Recovery is explicitly scoped. Project, identity/config, retained run, MCP registry and optional state adapters restore independently. Secret stores and CA private state are excluded from ordinary reset/backup scopes.
