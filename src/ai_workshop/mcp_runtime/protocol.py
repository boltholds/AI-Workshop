from __future__ import annotations

from typing import Protocol

from ai_workshop.mcp_runtime.models import (
    McpDiscoveredCapabilities,
    McpRegistration,
    McpServerRecord,
    McpServerState,
)


class McpRegistry(Protocol):
    def register(self, registration: McpRegistration) -> McpServerRecord: ...
    def get(self, server_id: str) -> McpServerRecord: ...
    def list(self) -> list[McpServerRecord]: ...
    def set_state(self, server_id: str, state: McpServerState) -> McpServerRecord: ...
    def update_capabilities(
        self,
        server_id: str,
        capabilities: McpDiscoveredCapabilities,
    ) -> McpServerRecord: ...
    def remove(self, server_id: str, *, actor_principal_id: str) -> None: ...
    def remove_scope(self, scope: str, scope_id: str) -> tuple[str, ...]: ...
