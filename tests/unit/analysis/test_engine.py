import pytest
from fastapi.testclient import TestClient

from ai_workshop.analysis.app import create_analysis_app
from ai_workshop.analysis.engine import AnalysisEngine


@pytest.fixture
def engine(tmp_path):
    projects = tmp_path / 'projects'
    root = projects / 'demo'
    root.mkdir(parents=True)
    results = tmp_path / 'results'
    results.mkdir()
    (root / 'pe.dll').write_bytes(b'MZ' + b'\0' * 32)
    (root / 'src.rs').write_text('fn main() {}')
    return AnalysisEngine(
        projects_root=projects, results_root=results,
        ghidra_home=tmp_path / 'missing-ghidra',
        script_path=tmp_path / 'missing-scripts',
    )


def test_shell_exec_denies_host_command_and_argument_escape(engine):
    for argv in (["bash", "-c", "id"], ["python3", "-c", "print(1)"],
                 ["file", "/etc/passwd"], ["strings", "../nope"],
                 ["objdump", "--disassemble-all", "pe.dll"]):
        with pytest.raises(ValueError):
            engine.shell_exec('demo', argv)


def test_shell_exec_runs_allowlisted_inspection(engine):
    result = engine.shell_exec('demo', ['sha256sum', 'pe.dll'])
    assert result['exit_code'] == 0
    assert len(result['stdout'].split()[0]) == 64


def test_invalid_manifest_and_missing_ghidra(engine):
    with pytest.raises(ValueError):
        engine.cargo_test('demo', '../Cargo.toml')
    with pytest.raises(ValueError):
        engine.binary_analyze('demo', 'pe.dll')


def test_results_are_scoped_to_project(engine):
    with pytest.raises(ValueError):
        engine.analysis_get_results('demo', '../../bad')
    with pytest.raises(ValueError):
        engine.analysis_get_results('unknown', 'a' * 32)


def test_analysis_worker_authentication(engine):
    app = create_analysis_app(engine, token='secret')
    client = TestClient(app)
    assert client.get('/v1/binary/results/demo/' + 'f' * 32).status_code == 401
    auth = {'Authorization': 'Bearer secret'}
    assert client.post('/v1/shell/exec', headers=auth, json={
        'project_id': 'demo', 'argv': ['sha256sum', 'pe.dll']
    }).status_code == 200
    assert client.post('/v1/shell/exec', headers=auth, json={
        'project_id': 'demo', 'argv': ['bash', '-c', 'id']
    }).status_code == 400
