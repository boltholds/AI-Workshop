from __future__ import annotations

from pydantic import BaseModel, Field


class SnapshotManifest(BaseModel):
    snapshot_id: str
    project_id: str
    repository_id: str
    head: str
    branch: str | None
    staged_patch_bytes: int = 0
    unstaged_patch_bytes: int = 0
    untracked_files: list[str] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(default_factory=dict)
