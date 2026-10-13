# REA MCP subserver

User goal: install REA and expose it as a downstream MCP server through the existing WAI connection.

Reuse the existing MCP registry, discovery and stable `mcp.*` proxy. Opt-in Server Mode configuration connects only to the fixed internal REA endpoint. The gateway starts even if REA is unavailable and retries discovery on subsequent requests. Tool input/output schemas and annotations must survive discovery. Existing Git and analysis tools remain unchanged.

REA 6.4.0 runs as a persistent stdio MCP child of a Streamable HTTP bridge in a separate non-root container. A dedicated Unix socket and bearer token protect the bridge; the sidecar has network_mode:none, so it cannot call the gateway; there is no published sidecar port. Only one explicitly selected research project is mounted read-only at `/workspace/target`. REA gets writable state at `/data`, the Ghidra installation read-only, JDK 21, and no WAI credentials, Docker socket or gateway state. The bridge token is not passed to the REA child. Calls are serialized because REA has a shared active analysis session. No automatic retry of tool calls with side effects.

This initial deployment is for the existing single-operator, loopback/tunnel gateway trust model; it does not establish multi-user identity. REA unavailable must not take down Git tools. Wire schema fidelity, error results, pagination, auth and real stdio/HTTP calls are acceptance checks. Native Ghidra analysis and Wine are separate milestones.

The current connector cannot build/restart host containers. Prepare a tested Git branch and an operator deployment command; do not claim the remote installation is live without a live smoke test.
