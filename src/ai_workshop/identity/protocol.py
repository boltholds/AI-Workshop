from __future__ import annotations

from typing import Protocol

from ai_workshop.identity.models import (
    PrincipalRecord,
    ProjectMembership,
    RoleDefinition,
)


class PrincipalService(Protocol):
    def create(self, principal: PrincipalRecord) -> PrincipalRecord: ...

    def get(self, principal_id: str) -> PrincipalRecord: ...

    def list(self) -> list[PrincipalRecord]: ...

    def create_role(self, role: RoleDefinition) -> RoleDefinition: ...

    def get_role(self, role_id: str) -> RoleDefinition: ...

    def list_roles(self) -> list[RoleDefinition]: ...

    def grant_global_role(self, principal_id: str, role_id: str) -> None: ...

    def global_roles(self, principal_id: str) -> tuple[str, ...]: ...

    def set_project_membership(self, membership: ProjectMembership) -> None: ...

    def project_membership(
        self,
        principal_id: str,
        project_id: str,
    ) -> ProjectMembership | None: ...
