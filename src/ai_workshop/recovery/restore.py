from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import subprocess
import tarfile
import time
from typing import Callable

from ai_workshop.models.recovery import ConfirmationToken, RestorePreview, RestoreResult
from ai_workshop.recovery.git_snapshot import (
    ensure_git_repository,
    git_bytes,
    repository_identity,
    worktree_hashes,
)
from ai_workshop.recovery.store import SnapshotStore
from ai_workshop.workspace.paths import PathPolicy


class RestoreService:
    def __init__(
        self,
        policy: PathPolicy,
        store: SnapshotStore,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.policy = policy
        self.store = store
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ConfirmationToken] = {}

    def preview(self, snapshot_id: str) -> RestorePreview:
        manifest = self.store.load_manifest(snapshot_id)
        root = self.policy.project_root(manifest.project_id)
        ensure_git_repository(root)
        if repository_identity(root) != manifest.repository_id:
            raise ValueError("repository identity does not match snapshot")

        current_head = git_bytes(root, "rev-parse", "HEAD").decode().strip()
        current_hashes = worktree_hashes(root)
        snapshot_paths = set(manifest.file_hashes)
        current_paths = set(current_hashes)

        reset_paths = sorted(
            path for path in snapshot_paths & current_paths
            if manifest.file_hashes[path] != current_hashes[path]
        )
        delete_paths = sorted(current_paths - snapshot_paths)
        restore_paths = sorted(snapshot_paths - current_paths)

        payload = {
            "snapshot_id": snapshot_id,
            "project_id": manifest.project_id,
            "current_head": current_head,
            "target_head": manifest.head,
            "reset_paths": reset_paths,
            "delete_paths": delete_paths,
            "restore_paths": restore_paths,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return RestorePreview(**payload, digest=digest)

    def prepare(self, snapshot_id: str, *, ttl_seconds: float = 300.0) -> ConfirmationToken:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        preview = self.preview(snapshot_id)
        token = secrets.token_urlsafe(32)
        confirmation = ConfirmationToken(
            token=token,
            snapshot_id=snapshot_id,
            preview_digest=preview.digest,
            expires_at=self.clock() + ttl_seconds,
        )
        self._confirmations[token] = confirmation
        return confirmation

    def restore(self, snapshot_id: str, token: str) -> RestoreResult:
        confirmation = self._confirmations.get(token)
        if confirmation is None or confirmation.snapshot_id != snapshot_id:
            raise PermissionError("valid restore confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(token, None)
            raise PermissionError("restore confirmation expired")

        preview = self.preview(snapshot_id)
        if preview.digest != confirmation.preview_digest:
            self._confirmations.pop(token, None)
            raise PermissionError("workspace changed since confirmation")

        # One use, even if a later recovery command fails.
        self._confirmations.pop(token, None)

        manifest = self.store.load_manifest(snapshot_id)
        root = self.policy.project_root(manifest.project_id)
        snapshot_dir = self.store.find_project_dir(snapshot_id)

        self._run_git(root, "checkout", "--detach", "-f", manifest.head)
        if manifest.branch is not None:
            self._run_git(root, "branch", "-f", manifest.branch, manifest.head)
            self._run_git(root, "checkout", "-f", manifest.branch)
        self._run_git(root, "clean", "-fd")

        staged = snapshot_dir / "staged.patch"
        if staged.stat().st_size:
            self._run_git(root, "apply", "--binary", "--index", str(staged))

        unstaged = snapshot_dir / "unstaged.patch"
        if unstaged.stat().st_size:
            self._run_git(root, "apply", "--binary", str(unstaged))

        self._restore_untracked(root, snapshot_dir / "untracked.tar", manifest.project_id)
        return RestoreResult(snapshot_id=snapshot_id, project_id=manifest.project_id)

    @staticmethod
    def _run_git(root: Path, *args: str) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Git restore operation failed")

    def _restore_untracked(self, root: Path, archive_path: Path, project_id: str) -> None:
        with tarfile.open(archive_path, "r") as archive:
            for member in archive.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe path in untracked snapshot archive")
                destination = root.joinpath(*relative.parts)

                if member.issym():
                    # Creating a link does not follow its target. Validate only the
                    # parent write location; later agent access is still protected
                    # by PathPolicy's canonical containment check.
                    parent_relative = relative.parent.as_posix()
                    parent = self.policy.resolve(
                        project_id,
                        "." if parent_relative == "." else parent_relative,
                    )
                    parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists() or destination.is_symlink():
                        destination.unlink()
                    os.symlink(member.linkname, destination)
                    continue

                if not member.isfile():
                    raise ValueError("unsupported entry in untracked snapshot archive")
                safe_destination = self.policy.resolve(project_id, relative.as_posix())
                safe_destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("invalid file in untracked snapshot archive")
                with source, safe_destination.open("wb") as output:
                    output.write(source.read())
                os.chmod(safe_destination, member.mode & 0o777)
