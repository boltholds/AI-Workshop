import asyncio
from contextlib import contextmanager
from pathlib import Path
import socket
import sys
import threading
import time

import httpx
import pytest
import uvicorn


@contextmanager
def running_app(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started, 'bridge startup failed'
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive(), 'bridge did not shut down'


def test_real_stdio_http_bridge_preserves_session_schemas_and_errors(tmp_path):
    from ai_workshop.rea.bridge import create_app
    from ai_workshop.rea.client import ReaMcpClient
    from mcp import StdioServerParameters
    command = StdioServerParameters(command=sys.executable, args=[str(Path('tests/fixtures/rea/fake_server.py').resolve())])
    app = create_app(command, token='test-only-token')
    with running_app(app) as url:
        assert httpx.post(url + '/mcp', json={}, trust_env=False).status_code == 401
        assert httpx.get(url + '/health', headers={'Authorization': 'Bearer wrong'}, trust_env=False).status_code == 401
        assert httpx.get(url + '/health', headers={'Authorization': 'Bearer test-only-token'}, trust_env=False).status_code == 200
        client = ReaMcpClient(url + '/mcp', token='test-only-token')
        tools = client.list_tools()
        assert next(t for t in tools if t['name'] == 'count')['inputSchema']['required'] == ['label']
        one = client.call_tool('count', {'label': 'one'})
        two = client.call_tool('count', {'label': 'two'})
        assert one['structuredContent']['count'] == 1
        assert two['structuredContent']['count'] == 2
        assert client.call_tool('fail', {})['isError'] is True
        assert client.list_resources() == []
        assert client.list_prompts() == []


def test_bridge_refuses_empty_token():
    from ai_workshop.rea.bridge import create_app
    from mcp import StdioServerParameters
    with pytest.raises(ValueError, match='token'):
        create_app(StdioServerParameters(command='rea', args=['mcp']), token='')


def test_pagination_and_missing_optional_capabilities():
    from ai_workshop.rea.bridge import create_app
    from ai_workshop.rea.client import ReaMcpClient
    from mcp import StdioServerParameters
    command = StdioServerParameters(command=sys.executable, args=[str(Path('tests/fixtures/rea/paged_server.py').resolve())])
    with running_app(create_app(command, token='test-only')) as url:
        client = ReaMcpClient(url + '/mcp', token='test-only')
        assert [t['name'] for t in client.list_tools()] == ['first', 'second']
        assert client.list_resources() == []
        assert client.list_prompts() == []


def test_loader_does_not_forward_bridge_token_to_child(monkeypatch):
    from ai_workshop.rea import bridge
    monkeypatch.setenv('AI_WORKSHOP_REA_TOKEN', 'private-bridge-token')
    monkeypatch.setenv('UNRELATED_SECRET', 'private-unrelated-secret')
    monkeypatch.setenv('GHIDRA_INSTALL_DIR', '/opt/ghidra')
    captured = {}
    def capture(command, *, token):
        captured.update(command=command, token=token)
    monkeypatch.setattr(bridge, 'create_app', capture)
    bridge.load_app()
    assert captured['token'] == 'private-bridge-token'
    assert captured['command'].env['GHIDRA_INSTALL_DIR'] == '/opt/ghidra'
    assert 'AI_WORKSHOP_REA_TOKEN' not in captured['command'].env
    assert 'UNRELATED_SECRET' not in captured['command'].env
    assert captured['command'].args == ['mcp']


@contextmanager
def running_unix_app(app, socket_path):
    try:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except PermissionError:
        pytest.skip('execution environment denies AF_UNIX; covered by container CI')
    else:
        probe.close()
    server = uvicorn.Server(uvicorn.Config(app, uds=str(socket_path), log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started
        yield
    finally:
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive()


def test_unix_socket_transport_does_not_need_sidecar_network(tmp_path):
    from ai_workshop.rea.bridge import create_app
    from ai_workshop.rea.client import ReaMcpClient
    from mcp import StdioServerParameters
    command = StdioServerParameters(command=sys.executable, args=[str(Path('tests/fixtures/rea/fake_server.py').resolve())])
    socket_path = tmp_path / 'rea.sock'
    with running_unix_app(create_app(command, token='unix-only'), socket_path):
        client = ReaMcpClient('http://rea-mcp:8796/mcp', token='unix-only', uds=str(socket_path))
        assert {t['name'] for t in client.list_tools()} == {'count', 'fail'}
        assert client.call_tool('count', {'label': 'uds'})['structuredContent']['label'] == 'uds'


def test_compose_disables_sidecar_network_and_shares_only_its_socket():
    import yaml
    config = yaml.safe_load(Path('deploy/server/compose.rea.yaml').read_text())
    sidecar = config['services']['rea-mcp']
    assert sidecar['network_mode'] == 'none'
    assert 'networks' not in sidecar
    assert 'networks' not in config['services']['gateway']
    assert config['services']['gateway']['volumes'] == ['rea-socket:/run/rea:ro']
