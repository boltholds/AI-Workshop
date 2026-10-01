from __future__ import annotations

from pathlib import Path, PurePosixPath

from ai_workshop.config import WorkshopConfig


class PathPolicy:
    def __init__(self, config: WorkshopConfig, *, host_paths: bool = False):
        self._projects = {p.project_id: p for p in config.projects}
        self._host_paths = host_paths

    def project(self, project_id: str):
        project = self._projects.get(project_id)
        if project is None:
            raise KeyError(f"unknown project: {project_id}")
        return project

    def project_root(self, project_id: str) -> Path:
        project = self.project(project_id)
        root = Path(project.host) if self._host_paths else Path(str(project.container))
        return root.resolve()

    def require_writable(self, project_id: str) -> None:
        if self.project(project_id).mode != "rw":
            raise PermissionError(f"project {project_id} is read-only")

    def resolve(self, project_id: str, relative_path: str = ".") -> Path:
        rel = PurePosixPath(relative_path)
        if rel.is_absolute():
            raise ValueError("path must be relative to the project root")
        root = self.project_root(project_id)
        candidate = (root / Path(*rel.parts)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("path resolves outside project root") from exc
        return candidate
