"""Opt-in test against the real pinned REA executable (no binary is opened)."""
import json
import os
from pathlib import Path

import pytest
from mcp import StdioServerParameters

from ai_workshop.gateway.server import build_server
from ai_workshop.mcp_runtime.models import McpRegistration, McpRegistrationScope, McpTransportKind
from ai_workshop.mcp_runtime.registry import McpRegistryStore
from ai_workshop.rea.bridge import create_app
from ai_workshop.rea.client import ReaMcpClient
from ai_workshop.rea.gateway import ReaProxy, ServerOperator
from tests.unit.rea.test_bridge import running_app


@pytest.mark.skipif(not os.environ.get('WAI_TEST_REA_EXECUTABLE'), reason='requires installed REA 6.4.0')
def test_real_rea_through_wai_gateway(tmp_path):
    home = tmp_path / 'rea-home'
    home.mkdir()
    params = StdioServerParameters(command=os.environ['WAI_TEST_REA_EXECUTABLE'], args=['mcp'], env={'HOME': str(home), 'REA_LOG_LEVEL': 'error'})
    with running_app(create_app(params, token='test-only')) as sidecar:
        registry = McpRegistryStore(tmp_path / 'mcp.json')
        registry.register(McpRegistration(server_id='rea', display_name='REA', transport=McpTransportKind.HTTP, scope=McpRegistrationScope.GLOBAL, scope_id='global', owner_principal_id='server-operator'))
        proxy = ReaProxy(registry, ReaMcpClient(sidecar + '/mcp', token='test-only'))
        gateway = build_server(None, token=None, mcp_proxy_service=proxy, principal_resolver=ServerOperator())
        with running_app(gateway.streamable_http_app(json_response=True, stateless_http=True)) as upstream:
            client = ReaMcpClient(upstream + '/mcp', token='unused-local-gateway')
            listed = client.call_tool('mcp.tools_list', {'server_id': 'rea'})
            assert not listed.get('isError')
            tools = [json.loads(block['text']) for block in listed['content']]
            assert len(tools) == 170
            assert all('inputSchema' in t for t in tools)
            assert 'open_binary' in {t['name'] for t in tools}
            result = client.call_tool('mcp.tool_call', {'server_id': 'rea', 'tool_name': 'list_documents', 'arguments': {}})
            assert not result.get('isError')  # Proxy itself succeeded.
            downstream = json.loads(result['content'][0]['text'])
            assert downstream['isError']  # REA reports that no target is open.
            assert json.loads(downstream['content'][0]['text'])['error']['code'] == 'target_unavailable'
            state = client.call_tool('mcp.tool_call', {'server_id': 'rea', 'tool_name': 'binary_session', 'arguments': {}})
            assert not state.get('isError')
            print('REA 6.4.0: 170 schemas discovered through WAI; tool calls and error envelope verified')
