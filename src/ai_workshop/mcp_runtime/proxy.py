from __future__ import annotations

from typing import Mapping, Protocol

from ai_workshop.mcp_runtime.models import (
    McpPromptDescriptor,
    McpResourceDescriptor,
    McpServerRecord,
    McpServerState,
    McpToolDescriptor,
)
from ai_workshop.mcp_runtime.protocol import McpRegistry


class DownstreamMcpClient(Protocol):
    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> dict[str, object]: ...

    def read_resource(self, uri: str) -> dict[str, object]: ...

    def get_prompt(
        self,
        name: str,
        arguments: Mapping[str, str],
    ) -> dict[str, object]: ...


class DownstreamClientResolver(Protocol):
    def client_for(self, server_id: str) -> DownstreamMcpClient: ...


class McpProxyService:
    def __init__(
        self,
        registry: McpRegistry,
        clients: DownstreamClientResolver,
        permissions=None,
    ):
        self.registry = registry
        self.clients = clients
        self.permissions = permissions

    def servers_list(self, principal_id: str) -> list[McpServerRecord]:
        return self.registry.list()

    def server_get(self, principal_id: str, server_id: str) -> McpServerRecord:
        return self.registry.get(server_id)

    def tools_list(
        self,
        principal_id: str,
        server_id: str,
    ) -> tuple[McpToolDescriptor, ...]:
        return self.registry.get(server_id).capabilities.tools

    def tool_call(
        self,
        principal_id: str,
        server_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> dict[str, object]:
        record = self._running(server_id)
        tools = {item.name: item for item in record.capabilities.tools}
        tool = tools.get(tool_name)
        if tool is None:
            raise KeyError(f"unknown downstream MCP tool: {tool_name}")
        if self.permissions is not None:
            self.permissions.require(
                principal_id,
                record.registration,
                tool.required_permissions,
            )
        return self.clients.client_for(server_id).call_tool(tool_name, arguments)

    def resources_list(
        self,
        principal_id: str,
        server_id: str,
    ) -> tuple[McpResourceDescriptor, ...]:
        return self.registry.get(server_id).capabilities.resources

    def resource_read(
        self,
        principal_id: str,
        server_id: str,
        uri: str,
    ) -> dict[str, object]:
        self._running(server_id)
        return self.clients.client_for(server_id).read_resource(uri)

    def prompts_list(
        self,
        principal_id: str,
        server_id: str,
    ) -> tuple[McpPromptDescriptor, ...]:
        return self.registry.get(server_id).capabilities.prompts

    def prompt_get(
        self,
        principal_id: str,
        server_id: str,
        prompt_name: str,
        arguments: Mapping[str, str],
    ) -> dict[str, object]:
        self._running(server_id)
        return self.clients.client_for(server_id).get_prompt(
            prompt_name,
            arguments,
        )

    def _running(self, server_id: str) -> McpServerRecord:
        record = self.registry.get(server_id)
        if record.registration.state is not McpServerState.RUNNING:
            raise RuntimeError("MCP_SERVER_NOT_RUNNING")
        return record
