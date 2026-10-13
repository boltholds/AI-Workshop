from pathlib import Path
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
