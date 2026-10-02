from __future__ import annotations

from ai_workshop.mcp_runtime.discovery import McpDiscoveryService
from ai_workshop.mcp_runtime.lifecycle import RunScopedMcpCleaner
from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.proxy import McpProxyService
from ai_workshop.mcp_runtime.registry import McpRegistryStore


class TinyMcp:
    def __init__(self):
        self.closed = False

    def list_tools(self):
        return [{"name": "echo"}]

    def list_resources(self):
        return []

    def list_prompts(self):
        return []

    def call_tool(self, name, arguments):
        assert name == "echo"
        return {"text": arguments["text"]}

    def read_resource(self, uri):
        raise KeyError(uri)

    def get_prompt(self, name, arguments):
        raise KeyError(name)

    def close(self):
        self.closed = True


class Clients:
    def __init__(self, handle):
        self.handle = handle

    def client_for(self, server_id):
        return self.handle


class Transports:
    def __init__(self, handle):
        self.handle = handle
        self.stopped = []

    def stop(self, server_id):
        self.stopped.append(server_id)
        self.handle.close()


def test_agent_created_run_scoped_mcp_is_immediately_callable_and_cleaned(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(
        McpRegistration(
            server_id="run-42-tools",
            display_name="Run tools",
            transport=McpTransportKind.CONTAINER,
            scope=McpRegistrationScope.RUN,
            scope_id="run-42",
            owner_principal_id="agent-titan",
            state=McpServerState.RUNNING,
        )
    )

    handle = TinyMcp()
    clients = Clients(handle)
    discovery = McpDiscoveryService(registry, clients)
    proxy = McpProxyService(registry, clients)

    discovery.refresh("run-42-tools")
    result = proxy.tool_call(
        "agent-titan",
        "run-42-tools",
        "echo",
        {"text": "hello"},
    )

    assert result == {"text": "hello"}

    transports = Transports(handle)
    RunScopedMcpCleaner(registry, transports).cleanup_run("run-42")

    assert transports.stopped == ["run-42-tools"]
    assert handle.closed is True
    assert registry.list() == []


def test_run_cleanup_removes_orphaned_mcp_runtime(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(
        McpRegistration(
            server_id="orphaned-mcp",
            display_name="Orphan",
            transport=McpTransportKind.CONTAINER,
            scope=McpRegistrationScope.RUN,
            scope_id="run-dead",
            owner_principal_id="agent-titan",
            state=McpServerState.FAILED,
        )
    )
    handle = TinyMcp()
    transports = Transports(handle)

    RunScopedMcpCleaner(registry, transports).cleanup_run("run-dead")

    assert "orphaned-mcp" in transports.stopped
    assert registry.list() == []
