from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ai_workshop.forge.http import ForgeHttpClient
from ai_workshop.forge.models import (
    ForgeCapability, ForgeIssue, ForgeIssueState, ForgeProfile, ForgePullRequest,
    ForgePullRequestState, ForgeRelease, ForgeRepository, ForgeRepositoryRef,
)


class GitLabForgeProvider:
    def __init__(self, profile: ForgeProfile, token: str, *, client=None):
        self.profile = profile
        self.http = ForgeHttpClient(
            base_url=profile.normalized_base_url(),
            default_headers={"PRIVATE-TOKEN": token},
            client=client,
        )

    def capabilities(self) -> frozenset[ForgeCapability]:
        return frozenset(ForgeCapability)

    @staticmethod
    def _project_id(repository: ForgeRepositoryRef) -> str:
        return quote(f"{repository.owner}/{repository.name}", safe="")

    @staticmethod
    def _repo(raw: dict[str, Any]) -> ForgeRepository:
        namespace = raw.get("namespace") or {}
        owner = namespace.get("full_path") or namespace.get("path") or raw["path_with_namespace"].rsplit("/", 1)[0]
        return ForgeRepository(
            provider_repository_id=str(raw["id"]),
            ref=ForgeRepositoryRef(owner=owner, name=raw["path"]),
            web_url=raw["web_url"],
            default_branch=raw.get("default_branch") or "main",
            archived=bool(raw.get("archived", False)),
        )

    @staticmethod
    def _pr(repository: ForgeRepositoryRef, raw: dict[str, Any]) -> ForgePullRequest:
        raw_state = raw.get("state")
        state = ForgePullRequestState.MERGED if raw_state == "merged" else ForgePullRequestState.CLOSED if raw_state == "closed" else ForgePullRequestState.OPEN
        return ForgePullRequest(
            provider_pull_request_id=str(raw["id"]),
            number=int(raw["iid"]),
            repository=repository,
            title=raw["title"],
            source_branch=raw["source_branch"],
            target_branch=raw["target_branch"],
            state=state,
            web_url=raw["web_url"],
        )

    @staticmethod
    def _issue(repository: ForgeRepositoryRef, raw: dict[str, Any]) -> ForgeIssue:
        return ForgeIssue(
            provider_issue_id=str(raw["id"]),
            number=int(raw["iid"]),
            repository=repository,
            title=raw["title"],
            state=ForgeIssueState.CLOSED if raw.get("state") == "closed" else ForgeIssueState.OPEN,
            web_url=raw["web_url"],
        )

    @staticmethod
    def _release(repository: ForgeRepositoryRef, raw: dict[str, Any]) -> ForgeRelease:
        return ForgeRelease(
            provider_release_id=str(raw.get("_links", {}).get("self") or raw["tag_name"]),
            repository=repository,
            tag=raw["tag_name"],
            name=raw.get("name") or raw["tag_name"],
            web_url=raw.get("_links", {}).get("self") or raw.get("assets", {}).get("sources", [{}])[0].get("url") or "",
        )

    def repository_create(self, owner: str, name: str, *, private: bool) -> ForgeRepository:
        raw = self.http.post_json("/api/v4/projects", {"name": name, "path": name, "namespace_id": owner, "visibility": "private" if private else "public"})
        return self._repo(raw)

    def repository_get(self, repository: ForgeRepositoryRef) -> ForgeRepository:
        return self._repo(self.http.get_json(f"/api/v4/projects/{self._project_id(repository)}"))

    def repository_list(self) -> list[ForgeRepository]:
        return [self._repo(raw) for raw in self.http.get_paginated("/api/v4/projects", params={"membership": "true", "per_page": 100})]

    def repository_archive(self, repository: ForgeRepositoryRef) -> ForgeRepository:
        raw = self.http.post_json(f"/api/v4/projects/{self._project_id(repository)}/archive", {})
        return self._repo(raw)

    def repository_delete(self, repository: ForgeRepositoryRef) -> None:
        self.http.delete(f"/api/v4/projects/{self._project_id(repository)}")

    def pull_request_create(self, repository: ForgeRepositoryRef, *, title: str, source_branch: str, target_branch: str, body: str) -> ForgePullRequest:
        raw = self.http.post_json(
            f"/api/v4/projects/{self._project_id(repository)}/merge_requests",
            {"title": title, "source_branch": source_branch, "target_branch": target_branch, "description": body},
        )
        return self._pr(repository, raw)

    def pull_request_get(self, repository: ForgeRepositoryRef, number: int) -> ForgePullRequest:
        return self._pr(repository, self.http.get_json(f"/api/v4/projects/{self._project_id(repository)}/merge_requests/{number}"))

    def pull_request_list(self, repository: ForgeRepositoryRef) -> list[ForgePullRequest]:
        rows = self.http.get_paginated(f"/api/v4/projects/{self._project_id(repository)}/merge_requests", params={"state": "all", "per_page": 100})
        return [self._pr(repository, raw) for raw in rows]

    def pull_request_merge(self, repository: ForgeRepositoryRef, number: int) -> ForgePullRequest:
        raw = self.http.put_json(f"/api/v4/projects/{self._project_id(repository)}/merge_requests/{number}/merge", {})
        return self._pr(repository, raw)

    def issue_create(self, repository: ForgeRepositoryRef, *, title: str, body: str) -> ForgeIssue:
        raw = self.http.post_json(f"/api/v4/projects/{self._project_id(repository)}/issues", {"title": title, "description": body})
        return self._issue(repository, raw)

    def issue_list(self, repository: ForgeRepositoryRef) -> list[ForgeIssue]:
        rows = self.http.get_paginated(f"/api/v4/projects/{self._project_id(repository)}/issues", params={"scope": "all", "per_page": 100})
        return [self._issue(repository, raw) for raw in rows]

    def release_create(self, repository: ForgeRepositoryRef, *, tag: str, name: str, body: str) -> ForgeRelease:
        raw = self.http.post_json(f"/api/v4/projects/{self._project_id(repository)}/releases", {"tag_name": tag, "name": name, "description": body})
        return self._release(repository, raw)

    def release_list(self, repository: ForgeRepositoryRef) -> list[ForgeRelease]:
        rows = self.http.get_paginated(f"/api/v4/projects/{self._project_id(repository)}/releases", params={"per_page": 100})
        return [self._release(repository, raw) for raw in rows]

    def branch_protect(self, repository: ForgeRepositoryRef, branch: str) -> None:
        self.http.post_json(f"/api/v4/projects/{self._project_id(repository)}/protected_branches", {"name": branch})

    def webhook_create(self, repository: ForgeRepositoryRef, url: str, events: tuple[str, ...]) -> str:
        payload: dict[str, Any] = {"url": url}
        mapping = {"push": "push_events", "issues": "issues_events", "merge_requests": "merge_requests_events", "releases": "releases_events"}
        for event in events:
            key = mapping.get(event)
            if key:
                payload[key] = True
        raw = self.http.post_json(f"/api/v4/projects/{self._project_id(repository)}/hooks", payload)
        return str(raw["id"])

    def webhook_delete(self, repository: ForgeRepositoryRef, webhook_id: str) -> None:
        self.http.delete(f"/api/v4/projects/{self._project_id(repository)}/hooks/{webhook_id}")
