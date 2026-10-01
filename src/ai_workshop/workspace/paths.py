from __future__ import annotations

from pathlib import Path, PurePath

from ai_workshop.config import WorkshopConfig


class PathPolicy:
    def __init__(self, config: WorkshopConfig) -> None:
        self._config = config

    def project_root(self, project_id: str) -> Path:
        try:
            project = self._config.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"unknown project: {project_id}") from exc
        return Path(project.container.as_posix()).resolve()

    def resolve(self, project_id: str, relative_path: str) -> Path:
        candidate_input = Path(relative_path)
        if candidate_input.is_absolute() or PurePath(relative_path).is_absolute():
            raise ValueError("path must be relative to the project root")
        root = self.project_root(project_id)
        candidate = (root / candidate_input).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("path escapes project root") from exc
        return candidate
