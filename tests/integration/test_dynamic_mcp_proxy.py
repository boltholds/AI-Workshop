from __future__ import annotations

from ai_workshop.gateway.mcp_runtime_tools import register_mcp_runtime_tools
from ai_workshop.mcp_runtime.models import (
    McpDiscoveredCapabilities,
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpToolDescriptor,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.proxy import McpProxyService
from ai_workshop.mcp_runtime.registry import McpRegistryStore


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        name = kwargs.get("name")

        def decorate(fn):
            self.tools[name or fn.__name__] = fn
            return fn
        return decorate


class FakeResolver:
    def current_principal_id(self):
        return "alice"


class FakeClient:
    def call_tool(self, name, arguments):
        return {"tool": name, "arguments": dict(arguments)}

    def read_resource(self, uri):
        return {"uri": uri, "text": "ok"}

    def get_prompt(self, name, arguments):
        return {"name": name, "arguments": dict(arguments)}


class FakeClients:
    def __init__(self):
        self.client = FakeClient()

    def client_for(self, server_id):
        return self.client


def _registration(server_id: str):
    return McpRegistration(
        server_id=server_id,
        display_name=server_id,
        transport=McpTransportKind.HTTP,
        scope=McpRegistrationScope.PROJECT,
        scope_id="demo",
        owner_principal_id="alice",
        state=McpServerState.RUNNING,
    )


def test_stable_proxy_schema_does_not_change_when_server_is_registered(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    proxy = McpProxyService(registry, FakeClients())
    server = FakeServer()
    register_mcp_runtime_tools(server, proxy, FakeResolver())

    stable_names = set(server.tools)

    registry.register(_registration("docs"))
    registry.update_capabilities(
        "docs",
        McpDiscoveredCapabilities(
            server_id="docs",
            revision=1,
            tools=(McpToolDescriptor(name="search"),),
        ),
    )

    assert set(server.tools) == stable_names
    assert stable_names == {
        "mcp.servers_list",
        "mcp.server_get",
        "mcp.tools_list",
        "mcp.tool_call",
        "mcp.resources_list",
        "mcp.resource_read",
        "mcp.prompts_list",
        "mcp.prompt_get",
    }
    assert server.tools["mcp.tools_list"]("docs")[0]["name"] == "search"


def test_new_downstream_tool_is_callable_without_upstream_restart(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(_registration("docs"))
    registry.update_capabilities(
        "docs",
        McpDiscoveredCapabilities(
            server_id="docs",
            revision=1,
            tools=(McpToolDescriptor(name="search"),),
        ),
    )
    proxy = McpProxyService(registry, FakeClients())
    server = FakeServer()
    register_mcp_runtime_tools(server, proxy, FakeResolver())

    result = server.tools["mcp.tool_call"](
        "docs",
        "search",
        {"query": "PLC"},
    )

    assert result == {
        "tool": "search",
        "arguments": {"query": "PLC"},
    }
