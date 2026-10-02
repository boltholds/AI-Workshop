from __future__ import annotations

from ai_workshop.mcp_runtime.models import (
    McpDiscoveredCapabilities,
    McpPromptDescriptor,
    McpResourceDescriptor,
    McpToolDescriptor,
)


class McpDiscoveryService:
    def __init__(self, registry, clients):
        self.registry = registry
        self.clients = clients

    def refresh(self, server_id: str):
        client = self.clients.client_for(server_id)
        current = self.registry.get(server_id).capabilities
        tools = tuple(
            McpToolDescriptor(
                name=item["name"],
                description=item.get("description", ""),
                required_permissions=frozenset(
                    item.get("required_permissions", ())
                ),
            )
            for item in client.list_tools()
        )
        resources = tuple(
            McpResourceDescriptor(
                uri=item["uri"],
                name=item.get("name") or item["uri"],
                description=item.get("description", ""),
            )
            for item in client.list_resources()
        )
        prompts = tuple(
            McpPromptDescriptor(
                name=item["name"],
                description=item.get("description", ""),
            )
            for item in client.list_prompts()
        )
        discovered = McpDiscoveredCapabilities(
            server_id=server_id,
            revision=current.revision + 1,
            tools=tools,
            resources=resources,
            prompts=prompts,
        )
        return self.registry.update_capabilities(server_id, discovered)

    def on_list_changed(self, server_id: str):
        return self.refresh(server_id)

    def on_reconnect(self, server_id: str):
        return self.refresh(server_id)
