from __future__ import annotations

from enum import StrEnum
import hashlib
import json
import secrets
import time
from typing import Callable, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ai_workshop.forge.forgejo import ForgejoForgeProvider
from ai_workshop.forge.github import GitHubForgeProvider
from ai_workshop.forge.gitlab import GitLabForgeProvider
from ai_workshop.forge.models import (
    ForgeIssue, ForgeProfile, ForgeProviderKind, ForgePullRequest, ForgeRelease,
    ForgeRepository, ForgeRepositoryBinding, ForgeRepositoryRef,
)
from ai_workshop.forge.registry import ForgeRegistry


T = TypeVar("T")


class ForgeDestructiveOperation(StrEnum):
    REPOSITORY_DELETE = "repository-delete"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgeDestructivePreview(_FrozenModel):
    operation: ForgeDestructiveOperation
    project_id: str
    repository: ForgeRepositoryRef
    digest: str


class ForgeDestructiveConfirmation(_FrozenModel):
    token: str
    preview_digest: str
    expires_at: float


class ForgeService:
    def __init__(
        self,
        registry: ForgeRegistry,
        credentials,
        authorization,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.registry = registry
        self.credentials = credentials
        self.authorization = authorization
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ForgeDestructiveConfirmation] = {}

    def _binding(
        self,
        principal_id: str,
        project_id: str,
        permission: str,
    ) -> ForgeRepositoryBinding:
        self.authorization.require(principal_id, permission, project_id)
        return self.registry.project_binding(project_id)

    @staticmethod
    def _require_repository(
        binding: ForgeRepositoryBinding,
        repository: ForgeRepositoryRef,
    ) -> None:
        if repository != binding.repository_ref():
            raise PermissionError("forge repository does not match project binding")

    @staticmethod
    def _provider_type(profile: ForgeProfile):
        if profile.provider is ForgeProviderKind.GITHUB:
            return GitHubForgeProvider
        if profile.provider is ForgeProviderKind.GITLAB:
            return GitLabForgeProvider
        if profile.provider is ForgeProviderKind.FORGEJO:
            return ForgejoForgeProvider
        raise ValueError("unsupported forge provider")

    def _call(
        self,
        binding: ForgeRepositoryBinding,
        callback: Callable[[object], T],
    ) -> T:
        profile = self.registry.get_profile(binding.profile_id)
        with self.credentials.http_token_context(profile.credential_id) as credential:
            provider = self._provider_type(profile)(
                profile,
                credential.token,
            )
            try:
                return callback(provider)
            except Exception as exc:
                message = credential.redact(str(exc))
                if message != str(exc):
                    raise RuntimeError(message) from None
                raise
            finally:
                provider.http.close()

    def repository_get(self, principal_id: str, project_id: str) -> ForgeRepository:
        binding = self._binding(principal_id, project_id, "forge.read")
        return self._call(binding, lambda provider: provider.repository_get(binding.repository_ref()))

    def pull_request_list(self, principal_id: str, project_id: str) -> list[ForgePullRequest]:
        binding = self._binding(principal_id, project_id, "forge.read")
        return self._call(binding, lambda provider: provider.pull_request_list(binding.repository_ref()))

    def pull_request_create(
        self,
        principal_id: str,
        project_id: str,
        *,
        title: str,
        source_branch: str,
        target_branch: str,
        body: str = "",
    ) -> ForgePullRequest:
        binding = self._binding(principal_id, project_id, "forge.write")
        return self._call(
            binding,
            lambda provider: provider.pull_request_create(
                binding.repository_ref(),
                title=title,
                source_branch=source_branch,
                target_branch=target_branch,
                body=body,
            ),
        )

    def pull_request_merge(
        self,
        principal_id: str,
        project_id: str,
        repository: ForgeRepositoryRef,
        number: int,
    ) -> ForgePullRequest:
        binding = self._binding(principal_id, project_id, "forge.merge")
        self._require_repository(binding, repository)
        return self._call(binding, lambda provider: provider.pull_request_merge(repository, number))

    def issue_list(self, principal_id: str, project_id: str) -> list[ForgeIssue]:
        binding = self._binding(principal_id, project_id, "forge.read")
        return self._call(binding, lambda provider: provider.issue_list(binding.repository_ref()))

    def issue_create(
        self,
        principal_id: str,
        project_id: str,
        *,
        title: str,
        body: str = "",
    ) -> ForgeIssue:
        binding = self._binding(principal_id, project_id, "forge.write")
        return self._call(binding, lambda provider: provider.issue_create(binding.repository_ref(), title=title, body=body))

    def release_list(self, principal_id: str, project_id: str) -> list[ForgeRelease]:
        binding = self._binding(principal_id, project_id, "forge.read")
        return self._call(binding, lambda provider: provider.release_list(binding.repository_ref()))

    def release_create(
        self,
        principal_id: str,
        project_id: str,
        *,
        tag: str,
        name: str,
        body: str = "",
    ) -> ForgeRelease:
        binding = self._binding(principal_id, project_id, "forge.write")
        return self._call(binding, lambda provider: provider.release_create(binding.repository_ref(), tag=tag, name=name, body=body))

    def branch_protect(self, principal_id: str, project_id: str, branch: str) -> None:
        binding = self._binding(principal_id, project_id, "forge.admin")
        self._call(binding, lambda provider: provider.branch_protect(binding.repository_ref(), branch))

    def webhook_create(
        self,
        principal_id: str,
        project_id: str,
        *,
        url: str,
        events: tuple[str, ...],
    ) -> str:
        binding = self._binding(principal_id, project_id, "forge.admin")
        return self._call(binding, lambda provider: provider.webhook_create(binding.repository_ref(), url, events))

    def webhook_delete(self, principal_id: str, project_id: str, webhook_id: str) -> None:
        binding = self._binding(principal_id, project_id, "forge.admin")
        self._call(binding, lambda provider: provider.webhook_delete(binding.repository_ref(), webhook_id))

    def preview_repository_delete(
        self,
        principal_id: str,
        project_id: str,
    ) -> ForgeDestructivePreview:
        binding = self._binding(principal_id, project_id, "forge.admin")
        payload = {
            "operation": ForgeDestructiveOperation.REPOSITORY_DELETE.value,
            "project_id": project_id,
            "repository": binding.repository_ref().model_dump(mode="json"),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ForgeDestructivePreview(
            operation=ForgeDestructiveOperation.REPOSITORY_DELETE,
            project_id=project_id,
            repository=binding.repository_ref(),
            digest=digest,
        )

    def prepare_repository_delete(
        self,
        principal_id: str,
        project_id: str,
        *,
        ttl_seconds: float = 300.0,
    ) -> ForgeDestructiveConfirmation:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        preview = self.preview_repository_delete(principal_id, project_id)
        token = secrets.token_urlsafe(32)
        confirmation = ForgeDestructiveConfirmation(
            token=token,
            preview_digest=preview.digest,
            expires_at=self.clock() + ttl_seconds,
        )
        self._confirmations[token] = confirmation
        return confirmation

    def repository_delete(
        self,
        principal_id: str,
        project_id: str,
        confirmation_token: str,
    ) -> None:
        preview = self.preview_repository_delete(principal_id, project_id)
        confirmation = self._confirmations.get(confirmation_token)
        if confirmation is None:
            raise PermissionError("valid forge confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("forge confirmation expired")
        if confirmation.preview_digest != preview.digest:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("forge binding changed since confirmation")
        self._confirmations.pop(confirmation_token, None)
        binding = self.registry.project_binding(project_id)
        self._call(binding, lambda provider: provider.repository_delete(binding.repository_ref()))
