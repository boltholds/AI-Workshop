from __future__ import annotations

from ai_workshop.workspace.paths import PathPolicy


class FilesystemService:
    def __init__(self, policy: PathPolicy, *, max_read_bytes: int = 1_048_576):
        self.policy = policy
        self.max_read_bytes = max_read_bytes

    def list(self, project_id: str, path: str = ".") -> list[str]:
        target = self.policy.resolve(project_id, path)
        return sorted(item.name for item in target.iterdir())

    def read(self, project_id: str, path: str) -> str:
        target = self.policy.resolve(project_id, path)
        size = target.stat().st_size
        if size > self.max_read_bytes:
            raise ValueError(f"file exceeds read limit of {self.max_read_bytes} bytes")
        data = target.read_bytes()
        if b"\x00" in data:
            raise ValueError("binary file cannot be read as text")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("binary or non-UTF-8 file cannot be read as text") from exc

    def write(self, project_id: str, path: str, content: str) -> None:
        target = self.policy.resolve(project_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def patch(self, project_id: str, path: str, old: str, new: str, *, occurrence: int | None = None) -> None:
        content = self.read(project_id, path)
        count = content.count(old)
        if count == 0:
            raise ValueError("expected text not found")
        if occurrence is None:
            if count > 1:
                raise ValueError("expected text appears more than once")
            updated = content.replace(old, new, 1)
        else:
            if occurrence < 1 or occurrence > count:
                raise ValueError("occurrence is outside the available matches")
            start = -1
            cursor = 0
            for _ in range(occurrence):
                start = content.find(old, cursor)
                cursor = start + len(old)
            updated = content[:start] + new + content[start + len(old):]
        self.write(project_id, path, updated)

    def search(self, project_id: str, needle: str, path: str = ".") -> list[dict[str, object]]:
        root = self.policy.resolve(project_id, path)
        project_root = self.policy.project_root(project_id)
        results: list[dict[str, object]] = []
        for file in sorted(root.rglob("*")):
            if not file.is_file():
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if needle in line:
                    results.append({
                        "path": file.relative_to(project_root).as_posix(),
                        "line": line_no,
                        "text": line,
                    })
        return results
