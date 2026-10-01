from __future__ import annotations

from pydantic import BaseModel, Field


class RestorePreview(BaseModel):
    snapshot_id: str
    project_id: str
    current_head: str
    target_head: str
    reset_paths: list[str] = Field(default_factory=list)
    delete_paths: list[str] = Field(default_factory=list)
    restore_paths: list[str] = Field(default_factory=list)
    current_state_digest: str
    digest: str


class ConfirmationToken(BaseModel):
    token: str
    snapshot_id: str
    preview_digest: str
    expires_at: float


class RestoreResult(BaseModel):
    snapshot_id: str
    project_id: str
    restored: bool = True


class ResetPlan(BaseModel):
    scope: str
    filesystem_paths: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    digest: str


class ResetResult(BaseModel):
    scope: str
    completed: bool = True


class StateSnapshotArtifact(BaseModel):
    snapshot_id: str
    adapter_id: str
    target_id: str
    sha256: str
    size_bytes: int


class StateRestoreResult(BaseModel):
    snapshot_id: str
    adapter_id: str
    target_id: str
    restored: bool = True
