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
