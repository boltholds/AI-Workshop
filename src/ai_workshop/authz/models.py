from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PermissionSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_id: str = Field(min_length=1)
    project_id: str | None = None
    permissions: frozenset[str] = frozenset()

    def allows(self, permission: str) -> bool:
        return (
            permission in self.permissions
            or "workshop.admin" in self.permissions
        )
