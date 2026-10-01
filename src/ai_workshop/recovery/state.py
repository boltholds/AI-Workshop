from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import time
from typing import Callable, Protocol
from uuid import uuid4

from ai_workshop.models.recovery import (
    ConfirmationToken,
    StateRestoreResult,
    StateSnapshotArtifact,
)
from ai_workshop.recovery.store import SnapshotStore


class StateAdapter(Protocol):
    def snapshot(self, target_id: str, destination: Path) -> None: ...
    def restore(self, target_id: str, artifact: Path) -> None: ...


class StateAdapterRegistry:
    def __init__(self, adapters: dict[str, StateAdapter]):
        self._adapters = dict(adapters)

    def require(self, adapter_id: str) -> StateAdapter:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise KeyError(f"unknown state adapter: {adapter_id}")
        return adapter

    def list_ids(self) -> list[str]:
        return sorted(self._adapters)


class StateSnapshotService:
    def __init__(
        self,
        registry: StateAdapterRegistry,
        store: SnapshotStore,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.registry = registry
        self.store = store
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ConfirmationToken] = {}

    def create(self, adapter_id: str, target_id: str) -> StateSnapshotArtifact:
        adapter = self.registry.require(adapter_id)
        snapshot_id = uuid4().hex
        directory = self.store.project_dir(snapshot_id, "state")
        artifact_path = directory / "artifact.bin"
        adapter.snapshot(target_id, artifact_path)
        if not artifact_path.is_file():
            raise RuntimeError("state adapter did not produce an artifact")
        data = artifact_path.read_bytes()
        artifact = StateSnapshotArtifact(
            snapshot_id=snapshot_id,
            adapter_id=adapter_id,
            target_id=target_id,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )
        (directory / "state.json").write_text(
            json.dumps(artifact.model_dump(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return artifact

    def load(self, snapshot_id: str) -> StateSnapshotArtifact:
        directory = self.store.existing_project_dir(snapshot_id, "state")
        payload = json.loads((directory / "state.json").read_text(encoding="utf-8"))
        return StateSnapshotArtifact.model_validate(payload)

    def prepare_restore(
        self,
        snapshot_id: str,
        *,
        ttl_seconds: float = 300.0,
    ) -> ConfirmationToken:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        artifact = self.load(snapshot_id)
        digest = self._artifact_digest(artifact)
        token = secrets.token_urlsafe(32)
        confirmation = ConfirmationToken(
            token=token,
            snapshot_id=snapshot_id,
            preview_digest=digest,
            expires_at=self.clock() + ttl_seconds,
        )
        self._confirmations[token] = confirmation
        return confirmation

    def restore(self, snapshot_id: str, token: str) -> StateRestoreResult:
        confirmation = self._confirmations.get(token)
        if confirmation is None or confirmation.snapshot_id != snapshot_id:
            raise PermissionError("valid state restore confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(token, None)
            raise PermissionError("state restore confirmation expired")

        artifact = self.load(snapshot_id)
        if confirmation.preview_digest != self._artifact_digest(artifact):
            self._confirmations.pop(token, None)
            raise PermissionError("state snapshot changed since confirmation")

        directory = self.store.existing_project_dir(snapshot_id, "state")
        artifact_path = directory / "artifact.bin"
        data = artifact_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            self._confirmations.pop(token, None)
            raise ValueError("state snapshot artifact checksum mismatch")

        adapter = self.registry.require(artifact.adapter_id)
        self._confirmations.pop(token, None)
        # The artifact is deliberately retained whether restore succeeds or fails.
        adapter.restore(artifact.target_id, artifact_path)
        return StateRestoreResult(
            snapshot_id=snapshot_id,
            adapter_id=artifact.adapter_id,
            target_id=artifact.target_id,
        )

    @staticmethod
    def _artifact_digest(artifact: StateSnapshotArtifact) -> str:
        return hashlib.sha256(
            json.dumps(
                artifact.model_dump(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
