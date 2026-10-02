from __future__ import annotations

from pathlib import Path, PurePosixPath
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ServerStorage:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.projects_root = self.root / "projects"
        self.runs_root = self.root / "runs"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str) -> Path:
        project_id = self._identifier(project_id, "project")
        target = (self.projects_root / project_id).resolve()
        self._require_within(target, self.projects_root, "project path escapes storage")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def run_root(self, run_id: str) -> Path:
        run_id = self._identifier(run_id, "run")
        target = (self.runs_root / run_id).resolve()
        self._require_within(target, self.runs_root, "run path escapes storage")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def resolve_run_path(self, run_id: str, relative: str) -> Path:
        if not relative or "\\" in relative:
            raise ValueError("run path must be a relative POSIX path")
        parsed = PurePosixPath(relative)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("run path must be relative and cannot escape storage")

        root = self.run_root(run_id).resolve()
        candidate = root.joinpath(*parsed.parts).resolve(strict=False)
        self._require_within(candidate, root, "run path escapes storage")
        return candidate

    @staticmethod
    def _identifier(value: str, kind: str) -> str:
        if not value or _IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"invalid {kind} id")
        return value

    @staticmethod
    def _require_within(path: Path, root: Path, message: str) -> None:
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(message) from exc
