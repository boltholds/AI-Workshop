from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
_PERMISSION_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]*$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrincipalKind(StrEnum):
    USER = "user"
    AGENT = "agent"
    SERVICE_ACCOUNT = "service-account"
    EXTERNAL = "external"


class _PrincipalBase(_FrozenModel):
    kind: PrincipalKind
    principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=200)


class UserPrincipal(_PrincipalBase):
    kind: PrincipalKind = PrincipalKind.USER


class AgentPrincipal(_PrincipalBase):
    kind: PrincipalKind = PrincipalKind.AGENT


class ServiceAccountPrincipal(_PrincipalBase):
    kind: PrincipalKind = PrincipalKind.SERVICE_ACCOUNT


class ExternalIdentityPrincipal(_PrincipalBase):
    kind: PrincipalKind = PrincipalKind.EXTERNAL
    provider_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    subject: str = Field(min_length=1, max_length=500)


PrincipalRecord = Annotated[
    UserPrincipal
    | AgentPrincipal
    | ServiceAccountPrincipal
    | ExternalIdentityPrincipal,
    Field(discriminator="kind"),
]


class RoleDefinition(_FrozenModel):
    role_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    @field_validator("allow", "deny")
    @classmethod
    def permissions_are_unique_and_valid(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate permission entry")
        for value in values:
            import re
            if re.fullmatch(_PERMISSION_PATTERN, value) is None:
                raise ValueError("invalid permission")
        return values


class GlobalRoleGrant(_FrozenModel):
    principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    role_id: str = Field(min_length=1, pattern=_ID_PATTERN)


class ProjectMembership(_FrozenModel):
    principal_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    project_id: str = Field(min_length=1, pattern=_ID_PATTERN)
    role_ids: tuple[str, ...]

    @field_validator("role_ids")
    @classmethod
    def role_ids_are_nonempty_and_unique(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not values:
            raise ValueError("project membership requires at least one role")
        if len(set(values)) != len(values):
            raise ValueError("duplicate role entry")
        return values
