from __future__ import annotations

from ai_workshop.config import WorkshopConfig
from ai_workshop.models.filesystem import FileEntry, SearchMatch
from ai_workshop.workspace.paths import PathPolicy


class FilesystemService:
    def __init__(self, paths: PathPolicy, config: WorkshopConfig) -> None:
        self._paths = paths
        self._config = config

    def _require_writable(self, project_id: str) -> None:
        try:
            project = self._config.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"unknown project: {project_id}") from exc
        if project.mode != "rw":
            raise PermissionError(f"project {project_id!r} is read-only")

    def list(self, project_id: str, relative_path: str = ".") -> list[FileEntry]:
        root = self._paths.project_root(project_id)
        directory = self._paths.resolve(project_id, relative_path)
        if not directory.is_dir():
            raise NotADirectoryError(relative_path)
        result: list[FileEntry] = []
        for child in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
            safe_child = self._paths.resolve(project_id, child.relative_to(root).as_posix())
            stat = safe_child.stat()
            result.append(FileEntry(
                name=child.name,
                path=safe_child.relative_to(root).as_posix(),
                is_dir=safe_child.is_dir(),
                size=None if safe_child.is_dir() else stat.st_size,
            ))
        return result

    def read(self, project_id: str, relative_path: str, *, max_bytes: int = 1_048_576) -> str:
        path = self._paths.resolve(project_id, relative_path)
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise ValueError(f"file exceeds maximum read size of {max_bytes} bytes")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("file is not valid UTF-8 text") from exc

    def write(self, project_id: str, relative_path: str, content: str) -> None:
        self._require_writable(project_id)
        path = self._paths.resolve(project_id, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def patch(self, project_id: str, relative_path: str, expected: str, replacement: str, *, occurrence: int | None = None) -> None:
        self._require_writable(project_id)
        content = self.read(project_id, relative_path)
        count = content.count(expected)
        if count == 0:
            raise ValueError("expected text was not found")
        if occurrence is None:
            if count != 1:
                raise ValueError(f"expected text appears {count} times")
            updated = content.replace(expected, replacement, 1)
        else:
            if occurrence < 1 or occurrence > count:
                raise ValueError(f"occurrence must be between 1 and {count}")
            start = -1
            search_from = 0
            for _ in range(occurrence):
                start = content.find(expected, search_from)
                search_from = start + len(expected)
            updated = content[:start] + replacement + content[start + len(expected):]
        self.write(project_id, relative_path, updated)

    def search(self, project_id: str, query: str, *, relative_path: str = ".", max_matches: int = 500) -> list[SearchMatch]:
        root = self._paths.project_root(project_id)
        start = self._paths.resolve(project_id, relative_path)
        if not start.exists():
            return []
        candidates = [start] if start.is_file() else sorted(start.rglob("*"))
        matches: list[SearchMatch] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                safe = self._paths.resolve(project_id, candidate.relative_to(root).as_posix())
                text = safe.read_text(encoding="utf-8")
            except (UnicodeDecodeError, ValueError, OSError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    matches.append(SearchMatch(path=safe.relative_to(root).as_posix(), line=line_no, text=line))
                    if len(matches) >= max_matches:
                        return matches
        return matches
