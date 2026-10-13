from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import tempfile


MAX_TEXT_BYTES = 1_048_576
_BLOCKED_PARTS = {'.git', '.ssh', '.workshop-server', '.workshop', '.env.local'}


def resolve_relative(root: Path, path: str, *, allow_root: bool = False) -> Path:
    """Resolve a project-relative POSIX path, rejecting symlink escapes."""
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('path must be a nonempty project-relative POSIX path')
    raw = PurePosixPath(path)
    if raw.is_absolute() or '..' in raw.parts or any(p in _BLOCKED_PARTS for p in raw.parts):
        raise ValueError('path is outside the permitted project tree')
    if not allow_root and raw.parts in ((), ('.',)):
        raise ValueError('path must designate a file')
    root = root.resolve(strict=True)
    dest = root.joinpath(*raw.parts).resolve(strict=False)
    if not dest.is_relative_to(root):
        raise ValueError('path escapes project root')
    if any(part in _BLOCKED_PARTS for part in dest.relative_to(root).parts):
        raise ValueError('path is outside the permitted project tree')
    return dest


class ProjectFileService:
    """Text-only project IO in the existing Server Mode project boundary."""

    def __init__(self, projects):
        self.projects = projects

    def _root(self, project_id: str) -> Path:
        project = self.projects.get(project_id)
        root = Path(project.path).resolve(strict=True)
        if not root.is_dir():
            raise ValueError('project checkout unavailable')
        # Refuse root-level symlink escapes, even if the project was previously registered.
        if hasattr(self.projects, 'storage'):
            managed = self.projects.storage.projects_root.resolve(strict=True)
            if not root.is_relative_to(managed):
                raise ValueError('project checkout escapes managed storage')
        return root

    def read(self, project_id: str, path: str) -> str:
        target = resolve_relative(self._root(project_id), path)
        if not target.is_file():
            raise ValueError('file does not exist')
        if target.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError('file exceeds text read limit')
        content = target.read_bytes()
        if b'\x00' in content or len(content) > MAX_TEXT_BYTES:
            raise ValueError('binary file or oversized text is not supported')
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('file is not UTF-8 text') from exc

    def write(self, project_id: str, path: str, content: str) -> dict[str, bool]:
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_TEXT_BYTES:
            raise ValueError('text write exceeds size limit')
        root = self._root(project_id)
        target = resolve_relative(root, path)
        raw_target = root.joinpath(*PurePosixPath(path).parts)
        if raw_target.is_symlink():
            raise ValueError('cannot write to symlink')
        target.parent.mkdir(parents=True, exist_ok=True)
        target = resolve_relative(root, path)
        if target.is_dir():
            raise ValueError('cannot overwrite directory')
        fd, temp = tempfile.mkstemp(prefix='.wai-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return {'ok': True}
