from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time
from typing import Callable
from uuid import uuid4

from ai_workshop.models.recovery import ConfirmationToken
from ai_workshop.recovery.store import SnapshotStore


class IdentityConfigurationRecovery:
    domain_id = "identity-config"

    def __init__(
        self,
        *,
        files: dict[str, Path],
        store: SnapshotStore,
        forbidden_roots: tuple[Path, ...] = (),
        clock: Callable[[], float] | None = None,
    ):
        self.files = {key: Path(value).resolve() for key, value in files.items()}
        self.store = store
        self.forbidden_roots = tuple(Path(p).resolve() for p in forbidden_roots)
        self.clock = clock or time.monotonic
        self._confirmations: dict[str, ConfirmationToken] = {}
        self._validate_files()

    def preview_snapshot(self, target_id: str = "server") -> dict[str, object]:
        return {
            "target_id": target_id,
            "files": sorted(self.files),
        }

    def snapshot(self, target_id: str = "server") -> dict[str, object]:
        snapshot_id = uuid4().hex
        directory = self.store.project_dir(snapshot_id, "identity-config")
        entries: list[dict[str, object]] = []
        for logical_name in sorted(self.files):
            source = self.files[logical_name]
            if not source.is_file():
                continue
            data = source.read_bytes()
            artifact_name = f"{logical_name}.bin"
            (directory / artifact_name).write_bytes(data)
            entries.append(
                {
                    "name": logical_name,
                    "artifact": artifact_name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }
            )
        manifest = {
            "version": 1,
            "snapshot_id": snapshot_id,
            "target_id": target_id,
            "entries": entries,
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        manifest["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def preview_restore(self, snapshot_id: str) -> dict[str, object]:
        manifest = self._manifest(snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "target_id": manifest["target_id"],
            "files": [entry["name"] for entry in manifest["entries"]],
            "digest": manifest["manifest_sha256"],
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
            raise PermissionError("valid identity restore confirmation required")
        if self.clock() > confirmation.expires_at:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("identity restore confirmation expired")

        manifest = self._manifest(snapshot_id)
        if confirmation.preview_digest != manifest["manifest_sha256"]:
            self._confirmations.pop(confirmation_token, None)
            raise PermissionError("identity snapshot changed since confirmation")
        self._confirmations.pop(confirmation_token, None)

        directory = self.store.existing_project_dir(snapshot_id, "identity-config")
        for entry in manifest["entries"]:
            logical_name = str(entry["name"])
            destination = self.files.get(logical_name)
            if destination is None:
                raise ValueError(f"identity snapshot references unknown file: {logical_name}")
            artifact = directory / str(entry["artifact"])
            data = artifact.read_bytes()
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("identity snapshot artifact checksum mismatch")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".restore.tmp")
            temporary.write_bytes(data)
            temporary.replace(destination)
        return {
            "snapshot_id": snapshot_id,
            "target_id": manifest["target_id"],
        }

    def _manifest(self, snapshot_id: str) -> dict[str, object]:
        directory = self.store.existing_project_dir(snapshot_id, "identity-config")
        payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if payload.get("version") != 1 or payload.get("snapshot_id") != snapshot_id:
            raise ValueError("invalid identity snapshot manifest")
        claimed = payload.get("manifest_sha256")
        material = dict(payload)
        material.pop("manifest_sha256", None)
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(encoded).hexdigest() != claimed:
            raise ValueError("identity snapshot manifest checksum mismatch")
        return payload

    def _validate_files(self) -> None:
        for path in self.files.values():
            for forbidden in self.forbidden_roots:
                if path == forbidden:
                    raise ValueError("identity backup file overlaps forbidden secret state")
                try:
                    path.relative_to(forbidden)
                except ValueError:
                    continue
                raise ValueError("identity backup file overlaps forbidden secret state")
