from __future__ import annotations

import json
from pathlib import Path
import shutil
import threading

from ai_workshop.projects.models import (
    ExternalProject,
    GitManagedProject,
    ProjectKind,
    ProjectRecord,
)
from ai_workshop.server.storage import ServerStorage


class ProjectStore:
    def __init__(
        self,
        *,
        storage: ServerStorage,
        state_path: Path,
        external_roots: tuple[Path, ...] = (),
    ):
        self.storage = storage
        self.state_path = Path(state_path)
        self.external_roots = tuple(Path(root).expanduser().resolve() for root in external_roots)
        self._lock = threading.RLock()
        self._projects: dict[str, ProjectRecord] = {}
        self._load()

    def register_git(
        self,
        project_id: str,
        *,
        remote_url: str,
    ) -> GitManagedProject:
        with self._lock:
            self._require_available(project_id)
            path = self.storage.project_root(project_id)
            project = GitManagedProject(
                project_id=project_id,
                path=path,
                remote_url=remote_url,
            )
            self._projects[project_id] = project
            self._persist()
            return project

    def register_external(
        self,
        project_id: str,
        path: Path,
    ) -> ExternalProject:
        with self._lock:
            self._require_available(project_id)
            resolved = Path(path).expanduser().resolve()
            if not resolved.is_dir():
                raise ValueError("external project path must be an existing directory")
            self._require_external_root(resolved)
            project = ExternalProject(
                project_id=project_id,
                path=resolved,
            )
            self._projects[project_id] = project
            self._persist()
            return project

    def get(self, project_id: str) -> ProjectRecord:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                raise KeyError(f"unknown project: {project_id}")
            return project

    def list(self) -> list[ProjectRecord]:
        with self._lock:
            return [self._projects[key] for key in sorted(self._projects)]

    def remove_registration(self, project_id: str) -> None:
        with self._lock:
            if project_id not in self._projects:
                raise KeyError(f"unknown project: {project_id}")
            self._projects.pop(project_id)
            self._persist()

    def delete_checkout(self, project_id: str) -> None:
        with self._lock:
            project = self.get(project_id)
            if isinstance(project, ExternalProject):
                raise ValueError("external project checkout is not owned by Workshop")

            expected = self.storage.project_root(project.project_id)
            if project.path.resolve() != expected.resolve():
                raise ValueError("managed checkout path is not canonical project path")

            if project.path.is_symlink():
                project.path.unlink()
            elif project.path.exists():
                shutil.rmtree(project.path)
            self._projects.pop(project_id)
            self._persist()

    def _require_available(self, project_id: str) -> None:
        if project_id in self._projects:
            raise ValueError(f"project already registered: {project_id}")

    def _require_external_root(self, path: Path) -> None:
        for root in self.external_roots:
            try:
                path.relative_to(root)
                return
            except ValueError:
                continue
        raise ValueError("external project path is outside configured external root")

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported project registry version")
        raw_projects = payload.get("projects", [])
        if not isinstance(raw_projects, list):
            raise ValueError("project registry projects must be a list")

        loaded: dict[str, ProjectRecord] = {}
        for raw in raw_projects:
            kind = raw.get("kind") if isinstance(raw, dict) else None
            if kind == ProjectKind.GIT_MANAGED.value:
                project: ProjectRecord = GitManagedProject.model_validate(raw)
                expected = self.storage.project_root(project.project_id).resolve()
                if project.path.resolve() != expected:
                    raise ValueError("managed project path is not canonical project path")
            elif kind == ProjectKind.EXTERNAL.value:
                project = ExternalProject.model_validate(raw)
                resolved = project.path.resolve()
                if not resolved.is_dir():
                    raise ValueError("external project path must be an existing directory")
                self._require_external_root(resolved)
                if resolved != project.path:
                    project = project.model_copy(update={"path": resolved})
            else:
                raise ValueError("unknown project kind")

            if project.project_id in loaded:
                raise ValueError(f"duplicate project id: {project.project_id}")
            loaded[project.project_id] = project

        self._projects = loaded

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "projects": [
                self._projects[key].model_dump(mode="json")
                for key in sorted(self._projects)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
