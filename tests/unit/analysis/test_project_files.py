import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from ai_workshop.analysis.project_files import ProjectFileService


class Projects:
    def __init__(self, path: Path):
        self.path = path

    def get(self, project_id: str):
        if project_id != 'demo':
            raise KeyError('unknown project')
        return SimpleNamespace(path=self.path)


def test_read_and_atomic_write(tmp_path):
    files = ProjectFileService(Projects(tmp_path))
    assert files.write('demo', 'src/lib.rs', 'pub fn answer() -> u32 { 42 }') == {'ok': True}
    assert files.read('demo', 'src/lib.rs') == 'pub fn answer() -> u32 { 42 }'


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permissions only')
@pytest.mark.parametrize('mode', [0o600, 0o644, 0o755, 0o444])
def test_atomic_write_preserves_existing_file_permissions(tmp_path, mode):
    target = tmp_path / 'Cargo.toml'
    target.write_text('old', encoding='utf-8')
    target.chmod(mode)

    files = ProjectFileService(Projects(tmp_path))
    assert files.write('demo', 'Cargo.toml', 'new') == {'ok': True}

    assert target.read_text(encoding='utf-8') == 'new'
    assert stat.S_IMODE(target.stat().st_mode) == mode
    assert list(tmp_path.glob('.wai-*')) == []


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permissions only')
def test_new_project_file_is_readable_by_analysis_worker(tmp_path):
    files = ProjectFileService(Projects(tmp_path))

    assert files.write('demo', 'src/new.rs', 'fn main() {}') == {'ok': True}

    target = tmp_path / 'src/new.rs'
    assert target.read_text(encoding='utf-8') == 'fn main() {}'
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert list(target.parent.glob('.wai-*')) == []


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permissions only')
def test_atomic_write_does_not_preserve_privileged_mode_bits(tmp_path):
    target = tmp_path / 'script.sh'
    target.write_text('old', encoding='utf-8')
    target.chmod(0o1755)

    files = ProjectFileService(Projects(tmp_path))
    files.write('demo', 'script.sh', 'new')

    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_traversal_and_symlink_escape_are_rejected(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'secret').write_text('do not leak')
    (project / 'escaped').symlink_to(elsewhere, target_is_directory=True)
    files = ProjectFileService(Projects(project))
    for path in ('../elsewhere/secret', '/etc/passwd', '.git/config', 'escaped/secret', r'..\elsewhere'):
        with pytest.raises(ValueError):
            files.read('demo', path)
        with pytest.raises(ValueError):
            files.write('demo', path, 'bad')
    assert (elsewhere / 'secret').read_text() == 'do not leak'


def test_reject_binary_and_oversized_content(tmp_path):
    (tmp_path / 'binary.dll').write_bytes(b'MZ\x00' * 3)
    files = ProjectFileService(Projects(tmp_path))
    with pytest.raises(ValueError):
        files.read('demo', 'binary.dll')
    with pytest.raises(ValueError):
        files.write('demo', 'over.txt', 'z' * (1_048_576 + 1))


def test_unknown_project_is_not_disclosed(tmp_path):
    files = ProjectFileService(Projects(tmp_path))
    with pytest.raises(KeyError):
        files.read('other', 'src/lib.rs')
