import asyncio

from ai_workshop.mcp_runtime.discovery import McpDiscoveryService
from ai_workshop.mcp_runtime.models import McpRegistration, McpRegistrationScope, McpTransportKind
from ai_workshop.mcp_runtime.registry import McpRegistryStore
from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.gateway import build_server_gateway_runtime


class Client:
    def list_tools(self):
        return [{'name': 'inspect', 'inputSchema': {'type': 'object', 'required': ['path'], 'properties': {'path': {'type': 'string'}}}, 'outputSchema': {'type': 'object'}, 'annotations': {'readOnlyHint': True}}]
    def list_resources(self): return []
    def list_prompts(self): return []
    def client_for(self, server_id): return self


def test_discovery_preserves_schemas_and_annotations(tmp_path):
    registry = McpRegistryStore(tmp_path / 'mcp.json')
    registry.register(McpRegistration(server_id='rea', display_name='REA', transport=McpTransportKind.HTTP, scope=McpRegistrationScope.GLOBAL, scope_id='global', owner_principal_id='server-operator'))
    record = McpDiscoveryService(registry, Client()).refresh('rea')
    tool = record.capabilities.tools[0].model_dump(mode='json', by_alias=True)
    assert tool['inputSchema']['required'] == ['path']
    assert tool['outputSchema'] == {'type': 'object'}
    assert tool['annotations']['readOnlyHint'] is True


def test_gateway_opt_in_exposes_proxy_without_contacting_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_WORKSHOP_REA_URL', 'http://rea-mcp:8796/mcp')
    monkeypatch.setenv('AI_WORKSHOP_REA_TOKEN', 'test-only')
    runtime = build_server_gateway_runtime(ServerModeConfig(storage_root=tmp_path / 'storage'), state_root=tmp_path / 'state')
    names = {t.name for t in asyncio.run(runtime.server.list_tools())}
    assert {'mcp.servers_list', 'mcp.tools_list', 'mcp.tool_call', 'git_status'} <= names


def test_gateway_rejects_partial_rea_config(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv('AI_WORKSHOP_REA_URL', 'http://rea-mcp:8796/mcp')
    monkeypatch.delenv('AI_WORKSHOP_REA_TOKEN', raising=False)
    with pytest.raises(ValueError, match='REA'):
        build_server_gateway_runtime(ServerModeConfig(storage_root=tmp_path / 'storage'), state_root=tmp_path / 'state')


def test_failed_discovery_recovers_on_next_request(tmp_path):
    from ai_workshop.rea.gateway import ReaProxy
    from ai_workshop.mcp_runtime.models import McpServerState
    class RecoveringClient(Client):
        unavailable = True
        def list_tools(self):
            if self.unavailable:
                raise ConnectionError('private error')
            return super().list_tools()
    registry = McpRegistryStore(tmp_path / 'mcp.json')
    registry.register(McpRegistration(server_id='rea', display_name='REA', transport=McpTransportKind.HTTP, scope=McpRegistrationScope.GLOBAL, scope_id='global', owner_principal_id='server-operator'))
    client = RecoveringClient()
    proxy = ReaProxy(registry, client)
    assert proxy.servers_list('server-operator')[0].registration.state is McpServerState.FAILED
    client.unavailable = False
    assert proxy.tools_list('server-operator', 'rea')[0].name == 'inspect'
    assert proxy.server_get('server-operator', 'rea').registration.state is McpServerState.RUNNING


def test_gateway_rejects_untrusted_rea_endpoint(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv('AI_WORKSHOP_REA_URL', 'http://169.254.169.254/mcp')
    monkeypatch.setenv('AI_WORKSHOP_REA_TOKEN', 'test-only')
    with pytest.raises(ValueError, match='REA URL'):
        build_server_gateway_runtime(ServerModeConfig(storage_root=tmp_path / 'storage'), state_root=tmp_path / 'state')
