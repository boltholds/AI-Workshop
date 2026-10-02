from __future__ import annotations

from ai_workshop.authz.models import PermissionSet
from ai_workshop.identity.protocol import PrincipalService


class AuthorizationService:
    def __init__(self, principals: PrincipalService):
        self.principals = principals

    def effective_permissions(
        self,
        principal_id: str,
        project_id: str | None,
    ) -> PermissionSet:
        global_role_ids = self.principals.global_roles(principal_id)
        global_allow, global_deny = self._permissions_for_roles(global_role_ids)
        global_effective = global_allow - global_deny

        if project_id is None:
            return PermissionSet(
                principal_id=principal_id,
                project_id=None,
                permissions=frozenset(global_effective),
            )

        membership = self.principals.project_membership(
            principal_id,
            project_id,
        )
        if membership is None:
            return PermissionSet(
                principal_id=principal_id,
                project_id=project_id,
                permissions=frozenset(),
            )

        project_allow, project_deny = self._permissions_for_roles(
            membership.role_ids
        )
        effective = (global_effective & project_allow) - project_deny
        return PermissionSet(
            principal_id=principal_id,
            project_id=project_id,
            permissions=frozenset(effective),
        )

    def require(
        self,
        principal_id: str,
        permission: str,
        project_id: str | None,
    ) -> PermissionSet:
        permissions = self.effective_permissions(
            principal_id,
            project_id,
        )
        if not permissions.allows(permission):
            raise PermissionError(
                f"permission denied: {permission}"
            )
        return permissions

    def _permissions_for_roles(
        self,
        role_ids: tuple[str, ...],
    ) -> tuple[set[str], set[str]]:
        allowed: set[str] = set()
        denied: set[str] = set()
        for role_id in role_ids:
            role = self.principals.get_role(role_id)
            allowed.update(role.allow)
            denied.update(role.deny)
        return allowed, denied
