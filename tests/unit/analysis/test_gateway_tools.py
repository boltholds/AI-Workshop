from types import SimpleNamespace

from ai_workshop.analysis.project_files import ProjectFileService
from ai_workshop.gateway.project_workspace_tools import register_project_workspace_tools


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class FakeProjects:
    def __init__(self, root):
        self.root = root

    def get(self, project_id):
        if project_id != 'demo':
            raise KeyError('missing')
        return SimpleNamespace(path=self.root)


class FakeAnalysis:
    def shell_exec(self, project_id, argv, timeout_seconds):
        return {'project_id': project_id, 'argv': argv, 'timeout': timeout_seconds}

    def cargo_test(self, project_id, manifest_path, timeout_seconds):
        return {'project_id': project_id, 'manifest': manifest_path}

    def binary_analyze(self, project_id, path):
        return {'path': path, 'status': 'queued'}

    def analysis_get_results(self, project_id, analysis_id):
        return {'analysis_id': analysis_id}


def test_project_workspace_tool_registration(tmp_path):
    server = FakeServer()
    register_project_workspace_tools(server, ProjectFileService(FakeProjects(tmp_path)), FakeAnalysis())
    assert set(server.tools) == {
        'filesystem_read', 'filesystem_write', 'shell_exec',
        'binary_analyze', 'analysis_get_results', 'cargo_test',
    }
    assert server.tools['filesystem_write']('demo', 'readme.txt', 'hello')['ok'] is True
    assert server.tools['filesystem_read']('demo', 'readme.txt') == 'hello'
    assert server.tools['shell_exec']('demo', ['file', 'readme.txt'])['argv'] == ['file', 'readme.txt']


def test_analysis_tools_are_opt_in(tmp_path):
    server = FakeServer()
    register_project_workspace_tools(server, ProjectFileService(FakeProjects(tmp_path)), None)
    assert set(server.tools) == {'filesystem_read', 'filesystem_write'}


def test_server_mode_does_not_enable_file_tools_implicitly(tmp_path, monkeypatch):
    import asyncio
    from ai_workshop.server.config import ServerModeConfig
    from ai_workshop.server.gateway import build_server_gateway_runtime

    monkeypatch.delenv('AI_WORKSHOP_ENABLE_PROJECT_FILES', raising=False)
    monkeypatch.delenv('AI_WORKSHOP_ANALYSIS_URL', raising=False)
    monkeypatch.delenv('AI_WORKSHOP_ANALYSIS_TOKEN', raising=False)
    runtime = build_server_gateway_runtime(
        ServerModeConfig(storage_root=tmp_path / 'storage'),
        state_root=tmp_path / 'state',
    )
    names = {tool.name for tool in asyncio.run(runtime.server.list_tools())}
    assert 'filesystem_write' not in names
    assert 'binary_analyze' not in names


def test_server_mode_enables_project_files_explicitly(tmp_path, monkeypatch):
    import asyncio
    from ai_workshop.server.config import ServerModeConfig
    from ai_workshop.server.gateway import build_server_gateway_runtime

    monkeypatch.setenv('AI_WORKSHOP_ENABLE_PROJECT_FILES', '1')
    monkeypatch.delenv('AI_WORKSHOP_ANALYSIS_URL', raising=False)
    monkeypatch.delenv('AI_WORKSHOP_ANALYSIS_TOKEN', raising=False)
    runtime = build_server_gateway_runtime(
        ServerModeConfig(storage_root=tmp_path / 'storage'),
        state_root=tmp_path / 'state',
    )
    names = {tool.name for tool in asyncio.run(runtime.server.list_tools())}
    assert 'filesystem_write' in names
    assert 'filesystem_read' in names
    assert 'binary_analyze' not in names
