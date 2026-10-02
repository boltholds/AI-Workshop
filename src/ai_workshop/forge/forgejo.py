from __future__ import annotations

from typing import Any

from ai_workshop.forge.http import ForgeHttpClient
from ai_workshop.forge.models import (
    ForgeCapability, ForgeIssue, ForgeIssueState, ForgeProfile, ForgePullRequest,
    ForgePullRequestState, ForgeRelease, ForgeRepository, ForgeRepositoryRef,
)


class ForgejoForgeProvider:
    def __init__(self, profile: ForgeProfile, token: str, *, client=None):
        self.profile = profile
        self.http = ForgeHttpClient(
            base_url=profile.normalized_base_url(),
            default_headers={"Authorization": f"token {token}", "Accept": "application/json"},
            client=client,
        )

    def capabilities(self) -> frozenset[ForgeCapability]:
        return frozenset(ForgeCapability)

    @staticmethod
    def _repo(raw: dict[str, Any]) -> ForgeRepository:
        return ForgeRepository(
            provider_repository_id=str(raw["id"]),
            ref=ForgeRepositoryRef(owner=raw["owner"]["login"], name=raw["name"]),
            web_url=raw["html_url"],
            default_branch=raw.get("default_branch") or "main",
            archived=bool(raw.get("archived", False)),
        )

    @staticmethod
    def _pr(repository: ForgeRepositoryRef, raw: dict[str, Any]) -> ForgePullRequest:
        state = ForgePullRequestState.MERGED if raw.get("merged") or raw.get("merged_at") else ForgePullRequestState.CLOSED if raw.get("state") == "closed" else ForgePullRequestState.OPEN
        return ForgePullRequest(
            provider_pull_request_id=str(raw["id"]),
            number=int(raw["number"]),
            repository=repository,
            title=raw["title"],
            source_branch=raw["head"]["ref"],
            target_branch=raw["base"]["ref"],
            state=state,
            web_url=raw["html_url"],
        )

    @staticmethod
    def _issue(repository: ForgeRepositoryRef, raw: dict[str, Any]) -> ForgeIssue:
        return ForgeIssue(
            provider_issue_id=str(raw["id"]),
            number=int(raw["number"]),
            repository=repository,
            title=raw["title"],
            state=ForgeIssueState.CLOSED if raw.get("state") == "closed" else ForgeIssueState.OPEN,
            web_url=raw["html_url"],
        )

    @staticmethod
    def _release(repository: ForgeRepositoryRef, raw: dict[str, Any]) -> ForgeRelease:
        return ForgeRelease(
            provider_release_id=str(raw["id"]),
            repository=repository,
            tag=raw["tag_name"],
            name=raw.get("name") or raw["tag_name"],
            web_url=raw.get("html_url") or raw.get("url") or "",
        )

    def repository_create(self, owner: str, name: str, *, private: bool) -> ForgeRepository:
        raw = self.http.post_json(f"/api/v1/orgs/{owner}/repos", {"name": name, "private": private})
        return self._repo(raw)

    def repository_get(self, repository: ForgeRepositoryRef) -> ForgeRepository:
        return self._repo(self.http.get_json(f"/api/v1/repos/{repository.owner}/{repository.name}"))

    def repository_list(self) -> list[ForgeRepository]:
        return [self._repo(raw) for raw in self.http.get_paginated("/api/v1/user/repos", params={"limit": 50})]

    def repository_archive(self, repository: ForgeRepositoryRef) -> ForgeRepository:
        raw = self.http.patch_json(f"/api/v1/repos/{repository.owner}/{repository.name}", {"archived": True})
        return self._repo(raw)

    def repository_delete(self, repository: ForgeRepositoryRef) -> None:
        self.http.delete(f"/api/v1/repos/{repository.owner}/{repository.name}")

    def pull_request_create(self, repository: ForgeRepositoryRef, *, title: str, source_branch: str, target_branch: str, body: str) -> ForgePullRequest:
        raw = self.http.post_json(
            f"/api/v1/repos/{repository.owner}/{repository.name}/pulls",
            {"title": title, "head": source_branch, "base": target_branch, "body": body},
        )
        return self._pr(repository, raw)

    def pull_request_get(self, repository: ForgeRepositoryRef, number: int) -> ForgePullRequest:
        return self._pr(repository, self.http.get_json(f"/api/v1/repos/{repository.owner}/{repository.name}/pulls/{number}"))

    def pull_request_list(self, repository: ForgeRepositoryRef) -> list[ForgePullRequest]:
        rows = self.http.get_paginated(f"/api/v1/repos/{repository.owner}/{repository.name}/pulls", params={"state": "all", "limit": 50})
        return [self._pr(repository, raw) for raw in rows]

    def pull_request_merge(self, repository: ForgeRepositoryRef, number: int) -> ForgePullRequest:
        self.http.post_json(f"/api/v1/repos/{repository.owner}/{repository.name}/pulls/{number}/merge", {"Do": "merge"})
        return self.pull_request_get(repository, number)

    def issue_create(self, repository: ForgeRepositoryRef, *, title: str, body: str) -> ForgeIssue:
        raw = self.http.post_json(f"/api/v1/repos/{repository.owner}/{repository.name}/issues", {"title": title, "body": body})
        return self._issue(repository, raw)

    def issue_list(self, repository: ForgeRepositoryRef) -> list[ForgeIssue]:
        rows = self.http.get_paginated(f"/api/v1/repos/{repository.owner}/{repository.name}/issues", params={"state": "all", "limit": 50})
        return [self._issue(repository, raw) for raw in rows if not raw.get("pull_request")]

    def release_create(self, repository: ForgeRepositoryRef, *, tag: str, name: str, body: str) -> ForgeRelease:
        raw = self.http.post_json(f"/api/v1/repos/{repository.owner}/{repository.name}/releases", {"tag_name": tag, "name": name, "body": body})
        return self._release(repository, raw)

    def release_list(self, repository: ForgeRepositoryRef) -> list[ForgeRelease]:
        rows = self.http.get_paginated(f"/api/v1/repos/{repository.owner}/{repository.name}/releases", params={"limit": 50})
        return [self._release(repository, raw) for raw in rows]

    def branch_protect(self, repository: ForgeRepositoryRef, branch: str) -> None:
        self.http.post_json(f"/api/v1/repos/{repository.owner}/{repository.name}/branch_protections", {"branch_name": branch, "enable_push": False, "enable_merge_whitelist": False})

    def webhook_create(self, repository: ForgeRepositoryRef, url: str, events: tuple[str, ...]) -> str:
        raw = self.http.post_json(
            f"/api/v1/repos/{repository.owner}/{repository.name}/hooks",
            {"type": "gitea", "active": True, "events": list(events), "config": {"url": url, "content_type": "json"}},
        )
        return str(raw["id"])

    def webhook_delete(self, repository: ForgeRepositoryRef, webhook_id: str) -> None:
        self.http.delete(f"/api/v1/repos/{repository.owner}/{repository.name}/hooks/{webhook_id}")
