from __future__ import annotations

from typing import Protocol

from ai_workshop.forge.models import (
    ForgeCapability,
    ForgeIssue,
    ForgeProfile,
    ForgePullRequest,
    ForgeRelease,
    ForgeRepository,
    ForgeRepositoryRef,
)


class ForgeProvider(Protocol):
    profile: ForgeProfile

    def capabilities(self) -> frozenset[ForgeCapability]: ...

    def repository_create(
        self,
        owner: str,
        name: str,
        *,
        private: bool,
    ) -> ForgeRepository: ...

    def repository_get(
        self,
        repository: ForgeRepositoryRef,
    ) -> ForgeRepository: ...

    def repository_list(self) -> list[ForgeRepository]: ...

    def repository_archive(
        self,
        repository: ForgeRepositoryRef,
    ) -> ForgeRepository: ...

    def repository_delete(
        self,
        repository: ForgeRepositoryRef,
    ) -> None: ...

    def pull_request_create(
        self,
        repository: ForgeRepositoryRef,
        *,
        title: str,
        source_branch: str,
        target_branch: str,
        body: str,
    ) -> ForgePullRequest: ...

    def pull_request_get(
        self,
        repository: ForgeRepositoryRef,
        number: int,
    ) -> ForgePullRequest: ...

    def pull_request_list(
        self,
        repository: ForgeRepositoryRef,
    ) -> list[ForgePullRequest]: ...

    def pull_request_merge(
        self,
        repository: ForgeRepositoryRef,
        number: int,
    ) -> ForgePullRequest: ...

    def issue_create(
        self,
        repository: ForgeRepositoryRef,
        *,
        title: str,
        body: str,
    ) -> ForgeIssue: ...

    def issue_list(
        self,
        repository: ForgeRepositoryRef,
    ) -> list[ForgeIssue]: ...

    def release_create(
        self,
        repository: ForgeRepositoryRef,
        *,
        tag: str,
        name: str,
        body: str,
    ) -> ForgeRelease: ...

    def release_list(
        self,
        repository: ForgeRepositoryRef,
    ) -> list[ForgeRelease]: ...

    def branch_protect(
        self,
        repository: ForgeRepositoryRef,
        branch: str,
    ) -> None: ...

    def webhook_create(
        self,
        repository: ForgeRepositoryRef,
        url: str,
        events: tuple[str, ...],
    ) -> str: ...

    def webhook_delete(
        self,
        repository: ForgeRepositoryRef,
        webhook_id: str,
    ) -> None: ...
