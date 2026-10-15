import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_workshop.analysis import cargo_prefetch
from ai_workshop.analysis.cargo_cache import (
    dependency_fingerprint,
    read_prepared_lock,
    snapshot_project,
)
from ai_workshop.analysis.engine import AnalysisEngine


def fixture_project(tmp_path):
    projects = tmp_path / 'projects'
    project = projects / 'demo'
    (project / 'src').mkdir(parents=True)
    (project / 'Cargo.toml').write_text('[package]\nname="demo"\nversion="0.1.0"\n')
    (project / 'src/lib.rs').write_text('pub fn main() {}\n')
    return projects, project


def install_metadata(tmp_path, project, *, lock=b'cargo-lock'):
    fingerprint = dependency_fingerprint(project, 'Cargo.toml')
    locks = tmp_path / 'locks'
    prepared = locks / 'demo' / fingerprint
    prepared.mkdir(parents=True)
    (prepared / 'Cargo.lock').write_bytes(lock)
    (prepared / 'metadata.json').write_text(json.dumps({
        'manifest': 'Cargo.toml',
        'fingerprint': fingerprint,
        'lock_path': 'Cargo.lock',
        'sha256': hashlib.sha256(lock).hexdigest(),
    }))
    return locks


def test_fingerprint_changes_for_manifests_not_source(tmp_path):
    _, project = fixture_project(tmp_path)
    before = dependency_fingerprint(project, 'Cargo.toml')
    (project / 'src/lib.rs').write_text('changed implementation')
    assert dependency_fingerprint(project, 'Cargo.toml') == before
    (project / 'Cargo.toml').write_text('[package]\nname="demo2"\n')
    assert dependency_fingerprint(project, 'Cargo.toml') != before


def test_snapshot_does_not_copy_private_state(tmp_path):
    _, project = fixture_project(tmp_path)
    (project / '.git').mkdir()
    (project / '.git/config').write_text('private git config')
    (project / '.env').write_text('secret')
    destination = tmp_path / 'scratch'
    snapshot_project(project, destination)
    assert (destination / 'src/lib.rs').is_file()
    assert not (destination / '.git').exists()
    assert not (destination / '.env').exists()


def test_snapshot_rejects_symlink_outside_project(tmp_path):
    _, project = fixture_project(tmp_path)
    outside = tmp_path / 'secret'
    outside.write_text('private')
    (project / 'escape').symlink_to(outside)
    with pytest.raises(ValueError, match='symlinks'):
        snapshot_project(project, tmp_path / 'scratch')


def test_cargo_test_uses_prepared_lock_and_offline_private_cache(tmp_path, monkeypatch):
    projects, project = fixture_project(tmp_path)
    locks = install_metadata(tmp_path, project)
    cache = tmp_path / 'cache'
    (cache / 'registry').mkdir(parents=True)
    (cache / 'registry/test-cached').write_text('registry content')
    results = tmp_path / 'results'
    results.mkdir()
    engine = AnalysisEngine(
        projects_root=projects, results_root=results,
        cargo_cache_root=cache, cargo_locks_root=locks,
    )
    invoked = []

    def fake_run(argv, *, cwd, timeout_seconds, environment=None):
        assert argv[:4] == ['cargo', 'test', '--offline', '--locked']
        assert '--target-dir' in argv
        assert environment is not None
        copied_manifest = Path(argv[argv.index('--manifest-path') + 1])
        assert copied_manifest.parent == cwd
        assert (cwd / 'Cargo.lock').read_bytes() == b'cargo-lock'
        assert (cwd / 'src/lib.rs').read_text() == 'pub fn main() {}\n'
        assert (Path(environment['CARGO_HOME']) / 'registry/test-cached').is_file()
        assert copied_manifest != project / 'Cargo.toml'
        invoked.append(True)
        return {'exit_code': 0, 'stdout': 'tests OK', 'timed_out': False, 'truncated': False}

    monkeypatch.setattr(engine, '_run', fake_run)
    assert engine.cargo_test('demo')['exit_code'] == 0
    assert invoked == [True]
    assert not (project / 'Cargo.lock').exists()


def test_cargo_test_reports_missing_prefetch_without_execution(tmp_path, monkeypatch):
    projects, project = fixture_project(tmp_path)
    cache = tmp_path / 'cache'
    cache.mkdir()
    locks = tmp_path / 'locks'
    locks.mkdir()
    results = tmp_path / 'results'
    results.mkdir()
    engine = AnalysisEngine(
        projects_root=projects, results_root=results,
        cargo_cache_root=cache, cargo_locks_root=locks,
    )
    monkeypatch.setattr(engine, '_run', lambda *args, **kwargs: pytest.fail('cargo ran'))
    response = engine.cargo_test('demo')
    assert response['exit_code'] == 101
    assert 'cargo-prefetch' in response['stdout']
    assert not (project / 'Cargo.lock').exists()


def test_prepared_lock_checksum_is_verified(tmp_path):
    _, project = fixture_project(tmp_path)
    locks = install_metadata(tmp_path, project)
    fingerprint = dependency_fingerprint(project, 'Cargo.toml')
    (locks / 'demo' / fingerprint / 'Cargo.lock').write_text('tampered')
    with pytest.raises(ValueError, match='checksum'):
        read_prepared_lock(locks, 'demo', fingerprint, 'Cargo.toml')


def test_prefetch_generates_lock_and_fetches_without_modifying_project(tmp_path, monkeypatch):
    projects, project = fixture_project(tmp_path)
    cache = tmp_path / 'cache'
    cache.mkdir()
    locks = tmp_path / 'locks'
    locks.mkdir()
    calls = []

    def fake_cargo(argv, *, cwd, cargo_home, capture=False):
        calls.append(argv[0])
        assert cargo_home == cache
        assert cwd != project
        manifest = Path(argv[argv.index('--manifest-path') + 1])
        assert manifest.parent == cwd
        if argv[0] == 'generate-lockfile':
            (cwd / 'Cargo.lock').write_bytes(b'locked')
        if argv[0] == 'metadata':
            return SimpleNamespace(stdout=json.dumps({'workspace_root': str(cwd)}))
        if argv[0] == 'fetch':
            assert '--locked' in argv
            (cargo_home / 'registry').mkdir(exist_ok=True)
            (cargo_home / 'registry/downloaded').write_text('ok')
        return SimpleNamespace(stdout='')

    monkeypatch.setattr(cargo_prefetch, '_cargo', fake_cargo)
    output = cargo_prefetch.prefetch(
        'demo', 'Cargo.toml',
        projects_root=projects, cache_root=cache, locks_root=locks,
    )
    assert calls == ['metadata', 'generate-lockfile', 'fetch']
    assert (output / 'Cargo.lock').read_bytes() == b'locked'
    assert (output / 'metadata.json').exists()
    assert not (project / 'Cargo.lock').exists()


@pytest.mark.parametrize('bad', ['../Cargo.toml', '/tmp/Cargo.toml', '.git/Cargo.toml'])
def test_manifest_path_never_escapes_project(tmp_path, bad):
    _, project = fixture_project(tmp_path)
    with pytest.raises(ValueError):
        dependency_fingerprint(project, bad)
