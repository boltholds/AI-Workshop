from __future__ import annotations

from pathlib import Path


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, snapshot_id: str, project_id: str) -> Path:
        if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id:
            raise ValueError("invalid snapshot id")
        if not project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("invalid project id")
        target = (self.root / snapshot_id / project_id).resolve()
        target.relative_to(self.root)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def existing_project_dir(self, snapshot_id: str, project_id: str) -> Path:
        target = (self.root / snapshot_id / project_id).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("snapshot path escapes store") from exc
        if not target.is_dir():
            raise FileNotFoundError(f"snapshot not found: {snapshot_id}/{project_id}")
        return target

    def find_project_dir(self, snapshot_id: str) -> Path:
        if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id:
            raise ValueError("invalid snapshot id")
        snapshot_root = (self.root / snapshot_id).resolve()
        try:
            snapshot_root.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("snapshot path escapes store") from exc
        if not snapshot_root.is_dir():
            raise FileNotFoundError(f"snapshot not found: {snapshot_id}")
        manifests = sorted(snapshot_root.glob("*/manifest.json"))
        if len(manifests) != 1:
            raise ValueError("snapshot must contain exactly one project manifest")
        return manifests[0].parent

    def load_manifest(self, snapshot_id: str):
        import json
        from ai_workshop.recovery.models import SnapshotManifest

        directory = self.find_project_dir(snapshot_id)
        payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        return SnapshotManifest.model_validate(payload)
