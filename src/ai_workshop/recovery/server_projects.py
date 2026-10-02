from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import secrets
import tarfile
import time
from typing import Callable
from uuid import uuid4

from ai_workshop.models.recovery import ConfirmationToken
from ai_workshop.recovery.git_snapshot import GitSnapshotService
from ai_workshop.recovery.restore import RestoreService
from ai_workshop.recovery.store import SnapshotStore
from ai_workshop.runs.workspaces import RunWorkspaceManager
from ai_workshop.server.storage import ServerStorage


class CanonicalProjectRecovery:
    domain_id = "projects"

    def __init__(
        self,
        snapshots: GitSnapshotService,
        restore: RestoreService,
    ):
        self.snapshots = snapshots
        self.restore_service = restore

    def preview_snapshot(self, target_id: str) -> dict[str, object]:
        return {"project_id": target_id, "kind": "git-aware"}

    def snapshot(self, target_id: str) -> dict[str, object]:
        return self.snapshots.create(target_id).model_dump(mode="json")

    def preview_restore(self, snapshot_id: str) -> dict[str, object]:
        return self.restore_service.preview(snapshot_id).model_dump(mode="json")

    def prepare_restore(
        self,
        snapshot_id: str,
        *,
        ttl_seconds: float = 300.0,
    ) -> ConfirmationToken:
        return self.restore_service.prepare(
            snapshot_id,
            ttl_seconds=ttl_seconds,
        )

    def restore(
        self,
        snapshot_id: str,
        confirmation_token: str,
    ) -> dict[str, object]:
        return self.restore_service.restore(
            snapshot_id,
            confirmation_token,
        ).model_dump(mode="json")


class RetainedRunRecovery:
    domain_id = "retained-runs"

    def __init__(
        self,
        workspaces: RunWorkspaceManager,
        storage: ServerStorage,
        store: SnapshotStore,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.workspaces = workspaces
        self.storage = storage
        self.store = store
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ConfirmationToken] = {}

    def preview_snapshot(self, target_id: str) -> dict[str, object]:
        workspace = self.workspaces.get(target_id)
        return {
            "run_id": workspace.run_id,
            "project_id": workspace.project_id,
            "commit_id": workspace.commit_id,
            "writable": workspace.writable,
        }

    def snapshot(self, target_id: str) -> dict[str, object]:
        workspace = self.workspaces.get(target_id)
        snapshot_id = uuid4().hex
        directory = self.store.project_dir(snapshot_id, "retained-run")
        archive = directory / "workspace.tar"
        with tarfile.open(archive, "w", dereference=False) as output:
            for child in sorted(workspace.path.rglob("*")):
                relative = child.relative_to(workspace.path)
                if ".git" in relative.parts:
                    continue
                output.add(child, arcname=relative.as_posix(), recursive=False)
        sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
        manifest = {
            "version": 1,
            "snapshot_id": snapshot_id,
            "run_id": workspace.run_id,
            "project_id": workspace.project_id,
            "commit_id": workspace.commit_id,
            "writable": workspace.writable,
            "sha256": sha256,
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def preview_restore(self, snapshot_id: str) -> dict[str, object]:
        manifest = self._manifest(snapshot_id)
        current = self.workspaces.get(manifest["run_id"])
        if current.project_id != manifest["project_id"]:
            raise ValueError("run workspace project identity mismatch")
        if current.commit_id != manifest["commit_id"]:
            raise ValueError("run workspace commit identity mismatch")
        payload = {
            "snapshot_id": snapshot_id,
            "run_id": manifest["run_id"],
            "project_id": manifest["project_id"],
            "commit_id": manifest["commit_id"],
            "current_path": str(current.path),
        }
        payload["digest"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload

    def prepare_restore(
        self,
        snapshot_id: str,
        *,
        ttl_seconds: float = 300.0,
    ) -> ConfirmationToken:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        preview = self.preview_restore(snapshot_id)
        token = secrets.token_urlsafe(32)
        confirmation = ConfirmationToken(
            token=token,
            snapshot_id=snapshot_id,
            preview_digest=str(preview["digest"]),
            expires_at=self.clock() + ttl_seconds,
        )
        self._confirmations[token] = confirmation
        return confirmation

    def restore(
        self,
        snapshot_id: str,
        confirmation_token: str,
    ) -> dict[str, object]:
        confirmation = self._confirmations.get(confirmation_token)
        if confirmation is None or confirmation.snapshot_id != snapshot_id:
            raise PermissionError("valid retained-run restore confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("retained-run restore confirmation expired")

        preview = self.preview_restore(snapshot_id)
        if confirmation.preview_digest != preview["digest"]:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("run workspace changed since confirmation")
        self._confirmations.pop(confirmation_token, None)

        manifest = self._manifest(snapshot_id)
        directory = self.store.existing_project_dir(snapshot_id, "retained-run")
        archive = directory / "workspace.tar"
        if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("retained-run snapshot checksum mismatch")

        workspace = self.workspaces.get(manifest["run_id"])
        for child in workspace.path.iterdir():
            if child.name == ".git":
                continue
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                import shutil
                shutil.rmtree(child)

        with tarfile.open(archive, "r") as source:
            for member in source.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts or ".git" in relative.parts:
                    raise ValueError("unsafe path in retained-run snapshot")
                destination = self.storage.resolve_run_path(
                    manifest["run_id"],
                    f"workspace/{relative.as_posix()}",
                )
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ValueError("unsupported retained-run archive entry")
                destination.parent.mkdir(parents=True, exist_ok=True)
                handle = source.extractfile(member)
                if handle is None:
                    raise ValueError("invalid retained-run archive")
                with handle, destination.open("wb") as output:
                    output.write(handle.read())

        return {
            "snapshot_id": snapshot_id,
            "run_id": manifest["run_id"],
            "project_id": manifest["project_id"],
        }

    def _manifest(self, snapshot_id: str) -> dict[str, object]:
        directory = self.store.existing_project_dir(snapshot_id, "retained-run")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or manifest.get("snapshot_id") != snapshot_id:
            raise ValueError("invalid retained-run snapshot manifest")
        return manifest
