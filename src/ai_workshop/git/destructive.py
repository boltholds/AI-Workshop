from __future__ import annotations

from enum import StrEnum
import hashlib
import json
import secrets
import time
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from ai_workshop.git.service import GitRepositoryService


class GitDestructiveOperation(StrEnum):
    HARD_RESET = "hard-reset"
    DELETE_BRANCH = "delete-branch"
    DELETE_TAG = "delete-tag"
    FORCE_PUSH = "force-push"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GitDestructivePreview(_FrozenModel):
    operation: GitDestructiveOperation
    project_id: str
    target: str
    target_oid: str
    remote: str = ""
    remote_url: str = ""
    current_head: str
    current_status: str
    digest: str


class GitDestructiveConfirmation(_FrozenModel):
    token: str
    preview_digest: str
    expires_at: float


class GitDestructiveResult(_FrozenModel):
    operation: GitDestructiveOperation
    project_id: str
    completed: bool = True


class GitDestructiveService:
    def __init__(
        self,
        git: GitRepositoryService,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.git = git
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, GitDestructiveConfirmation] = {}

    def preview_hard_reset(
        self,
        project_id: str,
        target: str,
    ) -> GitDestructivePreview:
        return self._preview(
            GitDestructiveOperation.HARD_RESET,
            project_id,
            target=self.git._ref(target),
        )

    def preview_delete_branch(
        self,
        project_id: str,
        branch: str,
    ) -> GitDestructivePreview:
        return self._preview(
            GitDestructiveOperation.DELETE_BRANCH,
            project_id,
            target=self.git._ref(branch),
        )

    def preview_delete_tag(
        self,
        project_id: str,
        tag: str,
    ) -> GitDestructivePreview:
        return self._preview(
            GitDestructiveOperation.DELETE_TAG,
            project_id,
            target=self.git._ref(tag),
        )

    def preview_force_push(
        self,
        project_id: str,
        *,
        remote: str,
        branch: str,
    ) -> GitDestructivePreview:
        return self._preview(
            GitDestructiveOperation.FORCE_PUSH,
            project_id,
            target=self.git._ref(branch),
            remote=self.git._remote_name(remote),
        )

    def prepare(
        self,
        preview: GitDestructivePreview,
        *,
        ttl_seconds: float = 300.0,
    ) -> GitDestructiveConfirmation:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        current = self._rebuild_preview(preview)
        if current.digest != preview.digest:
            raise PermissionError("Git repository changed before confirmation")
        token = secrets.token_urlsafe(32)
        confirmation = GitDestructiveConfirmation(
            token=token,
            preview_digest=preview.digest,
            expires_at=self.clock() + ttl_seconds,
        )
        self._confirmations[token] = confirmation
        return confirmation

    def hard_reset(
        self,
        project_id: str,
        target: str,
        confirmation_token: str,
    ) -> GitDestructiveResult:
        preview = self.preview_hard_reset(project_id, target)
        self._consume(confirmation_token, preview)
        self.git._hard_reset_confirmed(project_id, target)
        return GitDestructiveResult(
            operation=GitDestructiveOperation.HARD_RESET,
            project_id=project_id,
        )

    def delete_branch(
        self,
        project_id: str,
        branch: str,
        confirmation_token: str,
    ) -> GitDestructiveResult:
        preview = self.preview_delete_branch(project_id, branch)
        self._consume(confirmation_token, preview)
        self.git._delete_branch_confirmed(project_id, branch)
        return GitDestructiveResult(
            operation=GitDestructiveOperation.DELETE_BRANCH,
            project_id=project_id,
        )

    def delete_tag(
        self,
        project_id: str,
        tag: str,
        confirmation_token: str,
    ) -> GitDestructiveResult:
        preview = self.preview_delete_tag(project_id, tag)
        self._consume(confirmation_token, preview)
        self.git._delete_tag_confirmed(project_id, tag)
        return GitDestructiveResult(
            operation=GitDestructiveOperation.DELETE_TAG,
            project_id=project_id,
        )

    def force_push(
        self,
        project_id: str,
        *,
        remote: str,
        branch: str,
        confirmation_token: str,
        credential_id: str | None = None,
    ) -> GitDestructiveResult:
        preview = self.preview_force_push(
            project_id,
            remote=remote,
            branch=branch,
        )
        self._consume(confirmation_token, preview)
        self.git._force_push_confirmed(
            project_id,
            remote=remote,
            branch=branch,
            credential_id=credential_id,
        )
        return GitDestructiveResult(
            operation=GitDestructiveOperation.FORCE_PUSH,
            project_id=project_id,
        )

    def _preview(
        self,
        operation: GitDestructiveOperation,
        project_id: str,
        *,
        target: str,
        remote: str = "",
    ) -> GitDestructivePreview:
        project = self.git._project(project_id)
        head = self.git._run(project.path, ["rev-parse", "HEAD"]).stdout.strip()
        status = self.git._run(
            project.path,
            ["status", "--porcelain=v1", "--untracked-files=all"],
        ).stdout.rstrip("\n")
        target_oid = self._resolve_target_oid(
            operation,
            project.path,
            target,
        )
        remote_url = ""
        if remote:
            remote_url = self.git._run(
                project.path,
                ["remote", "get-url", remote],
            ).stdout.strip()
        payload = {
            "operation": operation.value,
            "project_id": project_id,
            "target": target,
            "target_oid": target_oid,
            "remote": remote,
            "remote_url": remote_url,
            "current_head": head,
            "current_status": status,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return GitDestructivePreview(**payload, digest=digest)

    def _resolve_target_oid(
        self,
        operation: GitDestructiveOperation,
        project_path,
        target: str,
    ) -> str:
        if operation is GitDestructiveOperation.DELETE_BRANCH:
            ref = f"refs/heads/{target}"
        elif operation is GitDestructiveOperation.DELETE_TAG:
            ref = f"refs/tags/{target}"
        else:
            ref = f"{target}^{{commit}}"
        return self.git._run(
            project_path,
            ["rev-parse", "--verify", ref],
        ).stdout.strip()

    def _rebuild_preview(
        self,
        preview: GitDestructivePreview,
    ) -> GitDestructivePreview:
        return self._preview(
            preview.operation,
            preview.project_id,
            target=preview.target,
            remote=preview.remote,
        )

    def _consume(
        self,
        token: str,
        preview: GitDestructivePreview,
    ) -> None:
        confirmation = self._confirmations.get(token)
        if confirmation is None:
            raise PermissionError("valid Git confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(token, None)
            raise PermissionError("Git confirmation expired")
        if confirmation.preview_digest != preview.digest:
            self._confirmations.pop(token, None)
            raise PermissionError("Git repository changed since confirmation")
        self._confirmations.pop(token, None)
