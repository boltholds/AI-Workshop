from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentLifetime(StrEnum):
    PERSISTENT = "persistent"
    EPHEMERAL = "ephemeral"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentIdentity(_FrozenModel):
    agent_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)
    owner_principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    lifetime: AgentLifetime
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: datetime | None = None

    @field_validator("created_at", "archived_at")
    @classmethod
    def timestamps_must_be_timezone_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("agent timestamp must be timezone-aware")
        return value


class DelegationGrant(_FrozenModel):
    grant_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    parent_run_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    parent_principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    child_agent_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    project_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    permissions: frozenset[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("permissions")
    @classmethod
    def permissions_must_be_nonempty(
        cls,
        value: frozenset[str],
    ) -> frozenset[str]:
        if not value:
            raise ValueError("delegation requires at least one permission")
        return value
