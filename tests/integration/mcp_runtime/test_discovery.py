from __future__ import annotations

from ai_workshop.mcp_runtime.discovery import McpDiscoveryService
from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.registry import McpRegistryStore


class Client:
    def __init__(self):
        self.tools = [{"name": "one"}]

    def list_tools(self):
        return list(self.tools)

    def list_resources(self):
        return []

    def list_prompts(self):
        return []


class Clients:
    def __init__(self, client):
        self.client = client

    def client_for(self, server_id):
        return self.client


def registration():
    return McpRegistration(
        server_id="demo",
        display_name="Demo",
        transport=McpTransportKind.HTTP,
        scope=McpRegistrationScope.PROJECT,
        scope_id="project",
        owner_principal_id="alice",
        state=McpServerState.RUNNING,
    )


def test_initial_discovery_populates_registry(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(registration())
    service = McpDiscoveryService(registry, Clients(Client()))

    record = service.refresh("demo")

    assert record.capabilities.revision == 1
    assert [tool.name for tool in record.capabilities.tools] == ["one"]


def test_list_changed_refreshes_capabilities(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(registration())
    client = Client()
    service = McpDiscoveryService(registry, Clients(client))
    service.refresh("demo")

    client.tools = [{"name": "one"}, {"name": "two"}]
    record = service.on_list_changed("demo")

    assert record.capabilities.revision == 2
    assert [tool.name for tool in record.capabilities.tools] == ["one", "two"]


def test_reconnect_rediscovery_updates_revision(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(registration())
    service = McpDiscoveryService(registry, Clients(Client()))
    service.refresh("demo")

    record = service.on_reconnect("demo")

    assert record.capabilities.revision == 2
