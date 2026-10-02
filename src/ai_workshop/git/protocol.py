from __future__ import annotations

from typing import Protocol

from ai_workshop.git.models import GitCommitResult, GitLogEntry, GitStatus
from ai_workshop.projects.models import GitManagedProject


class GitService(Protocol):
    def clone(
        self,
        project_id: str,
        remote_url: str,
        *,
        credential_id: str | None = None,
    ) -> GitManagedProject: ...

    def status(self, project_id: str) -> GitStatus: ...

    def diff(self, project_id: str, *, staged: bool = False) -> str: ...

    def fetch(
        self,
        project_id: str,
        *,
        remote: str = "origin",
        credential_id: str | None = None,
    ) -> None: ...

    def pull(
        self,
        project_id: str,
        *,
        remote: str = "origin",
        branch: str,
        credential_id: str | None = None,
    ) -> None: ...

    def add(self, project_id: str, paths: list[str]) -> None: ...

    def commit(self, project_id: str, message: str) -> GitCommitResult: ...

    def log(self, project_id: str, *, limit: int = 20) -> list[GitLogEntry]: ...

    def branch_list(self, project_id: str) -> list[str]: ...

    def branch_create(self, project_id: str, branch: str) -> None: ...

    def switch(self, project_id: str, branch: str) -> None: ...

    def checkout(self, project_id: str, ref: str) -> None: ...

    def remote_list(self, project_id: str) -> dict[str, str]: ...

    def remote_set(self, project_id: str, name: str, url: str) -> None: ...

    def stash(self, project_id: str, *, message: str = "AI Workshop stash") -> None: ...

    def tag(self, project_id: str, tag: str) -> None: ...

    def push(
        self,
        project_id: str,
        *,
        remote: str = "origin",
        branch: str,
        credential_id: str | None = None,
    ) -> None: ...

    def merge(self, project_id: str, ref: str) -> None: ...

    def rebase(self, project_id: str, ref: str) -> None: ...

    def rebase_continue(self, project_id: str) -> None: ...

    def rebase_abort(self, project_id: str) -> None: ...

    def cherry_pick(self, project_id: str, ref: str) -> None: ...
