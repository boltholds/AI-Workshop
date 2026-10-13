# REA MCP subserver implementation plan

Goal: REA callable through the existing WAI MCP connection.
Spec: ../specs/2026-10-13-rea-mcp-subserver.md

1. Add failing tests for schema-preserving discovery, opt-in gateway tools, unavailable-sidecar recovery and a real stdio-to-HTTP bridge with token authentication.
2. Implement the fixed-command REA bridge, SDK Streamable HTTP client and lazy registry connection; preserve the existing gateway's default behavior.
3. Pin REA in an isolated Docker image, add a Compose overlay and deployment/smoke instructions. Preserve analysis overlay and project mounts.
4. Run focused and existing MCP/server tests, then exercise installed REA 6.4.0 through the bridge and gateway. Review and publish a feature branch. Remote deployment requires host Docker execution, which is not exposed by the current connector.

Review focus: schema loss, optional MCP capabilities, sidecar outage, shared process lifetime, leaked tokens, unintended mounts, tool result/error fidelity.
