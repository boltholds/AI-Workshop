from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class RunResourceLimits(_FrozenModel):
    cpu_cores: float = Field(default=2.0, gt=0, le=64)
    memory_mb: int = Field(default=4096, ge=128, le=262144)


class AgentRun(_FrozenModel):
    run_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    agent_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    initiator_principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    project_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    base_ref: str = Field(min_length=1, max_length=500)
    writable: bool
    workspace_path: Path
    effective_permissions: frozenset[str]
    limits: RunResourceLimits = RunResourceLimits()
    state: RunState
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: datetime | None = None

    @field_validator("workspace_path")
    @classmethod
    def workspace_path_is_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("run workspace path must be absolute")
        return value

    @field_validator("created_at", "stopped_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("run timestamp must be timezone-aware")
        return value
