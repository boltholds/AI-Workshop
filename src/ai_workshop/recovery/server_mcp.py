from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import time
from typing import Callable
from uuid import uuid4

from ai_workshop.models.recovery import ConfirmationToken
from ai_workshop.mcp_runtime.models import McpServerRecord
from ai_workshop.recovery.store import SnapshotStore


class McpRegistryRecovery:
    domain_id = "mcp-registry"

    def __init__(
        self,
        registry,
        store: SnapshotStore,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.registry = registry
        self.store = store
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ConfirmationToken] = {}

    def preview_snapshot(self, target_id: str = "registry") -> dict[str, object]:
        records = self.registry.export_metadata()
        return {
            "target_id": target_id,
            "server_ids": [record.registration.server_id for record in records],
        }

    def snapshot(self, target_id: str = "registry") -> dict[str, object]:
        snapshot_id = uuid4().hex
        directory = self.store.project_dir(snapshot_id, "mcp-registry")
        records = [
            record.model_dump(mode="json")
            for record in self.registry.export_metadata()
        ]
        payload = {
            "version": 1,
            "snapshot_id": snapshot_id,
            "target_id": target_id,
            "records": records,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        payload["sha256"] = hashlib.sha256(encoded).hexdigest()
        (directory / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload

    def preview_restore(self, snapshot_id: str) -> dict[str, object]:
        manifest = self._manifest(snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "target_id": manifest["target_id"],
            "server_ids": [
                record["registration"]["server_id"]
                for record in manifest["records"]
            ],
            "digest": manifest["sha256"],
        }

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
            raise PermissionError("valid MCP registry restore confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("MCP registry restore confirmation expired")

        manifest = self._manifest(snapshot_id)
        if confirmation.preview_digest != manifest["sha256"]:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("MCP registry snapshot changed since confirmation")
        self._confirmations.pop(confirmation_token, None)

        records = tuple(
            McpServerRecord.model_validate(raw)
            for raw in manifest["records"]
        )
        self.registry.restore_metadata(records)
        return {
            "snapshot_id": snapshot_id,
            "target_id": manifest["target_id"],
            "server_ids": [
                record.registration.server_id
                for record in self.registry.export_metadata()
            ],
        }

    def _manifest(self, snapshot_id: str) -> dict[str, object]:
        directory = self.store.existing_project_dir(snapshot_id, "mcp-registry")
        payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if payload.get("version") != 1 or payload.get("snapshot_id") != snapshot_id:
            raise ValueError("invalid MCP registry snapshot manifest")
        claimed = payload.get("sha256")
        material = dict(payload)
        material.pop("sha256", None)
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(encoded).hexdigest() != claimed:
            raise ValueError("MCP registry snapshot checksum mismatch")
        return payload
