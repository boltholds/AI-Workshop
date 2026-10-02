from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor_principal_id: str = Field(min_length=1)
    owner_principal_id: str | None = None
    delegated_from_principal_id: str | None = None
    run_id: str | None = None
    project_id: str | None = None
    action: str = Field(min_length=1, max_length=200)
    resource: str = Field(default="", max_length=2000)
    outcome: AuditOutcome
    approval_ref: str | None = None
    message: str = Field(default="", max_length=8000)
    attributes: dict[str, str] = Field(default_factory=dict)
    sensitive_values: tuple[str, ...] = Field(
        default=(),
        exclude=True,
        repr=False,
    )

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("audit timestamp must be timezone-aware")
        return value
