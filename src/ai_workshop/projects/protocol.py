from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ai_workshop.projects.models import (
    ExternalProject,
    GitManagedProject,
    ProjectRecord,
)


class ProjectService(Protocol):
    def register_git(
        self,
        project_id: str,
        *,
        remote_url: str,
    ) -> GitManagedProject: ...

    def register_external(
        self,
        project_id: str,
        path: Path,
    ) -> ExternalProject: ...

    def get(self, project_id: str) -> ProjectRecord: ...

    def list(self) -> list[ProjectRecord]: ...

    def remove_registration(self, project_id: str) -> None: ...

    def delete_checkout(self, project_id: str) -> None: ...
