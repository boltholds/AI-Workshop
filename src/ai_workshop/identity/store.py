from __future__ import annotations

import json
from pathlib import Path
import threading

from ai_workshop.identity.models import (
    AgentPrincipal,
    ExternalIdentityPrincipal,
    GlobalRoleGrant,
    PrincipalKind,
    PrincipalRecord,
    ProjectMembership,
    RoleDefinition,
    ServiceAccountPrincipal,
    UserPrincipal,
)


class PrincipalStore:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._principals: dict[str, PrincipalRecord] = {}
        self._roles: dict[str, RoleDefinition] = {}
        self._global_roles: dict[str, list[str]] = {}
        self._memberships: dict[tuple[str, str], ProjectMembership] = {}
        self._load()

    def create(self, principal: PrincipalRecord) -> PrincipalRecord:
        with self._lock:
            if principal.principal_id in self._principals:
                raise ValueError(
                    f"principal already exists: {principal.principal_id}"
                )
            if isinstance(principal, ExternalIdentityPrincipal):
                binding = (principal.provider_id, principal.subject)
                for existing in self._principals.values():
                    if (
                        isinstance(existing, ExternalIdentityPrincipal)
                        and (existing.provider_id, existing.subject) == binding
                    ):
                        raise ValueError("external identity already exists")
            self._principals[principal.principal_id] = principal
            try:
                self._persist()
            except Exception:
                self._principals.pop(principal.principal_id, None)
                raise
            return principal

    def get(self, principal_id: str) -> PrincipalRecord:
        with self._lock:
            principal = self._principals.get(principal_id)
            if principal is None:
                raise KeyError(f"unknown principal: {principal_id}")
            return principal

    def list(self) -> list[PrincipalRecord]:
        with self._lock:
            return list(self._principals.values())

    def find_external(
        self,
        provider_id: str,
        subject: str,
    ) -> ExternalIdentityPrincipal | None:
        with self._lock:
            for principal in self._principals.values():
                if (
                    isinstance(principal, ExternalIdentityPrincipal)
                    and principal.provider_id == provider_id
                    and principal.subject == subject
                ):
                    return principal
            return None

    def remove_unreferenced(self, principal_id: str) -> None:
        with self._lock:
            self.get(principal_id)
            if self._global_roles.get(principal_id):
                raise ValueError("principal still has global role grants")
            if any(
                key[0] == principal_id
                for key in self._memberships
            ):
                raise ValueError("principal still has project memberships")
            principal = self._principals.pop(principal_id)
            try:
                self._persist()
            except Exception:
                self._principals[principal_id] = principal
                raise

    def create_role(self, role: RoleDefinition) -> RoleDefinition:
        with self._lock:
            if role.role_id in self._roles:
                raise ValueError(f"role already exists: {role.role_id}")
            self._roles[role.role_id] = role
            try:
                self._persist()
            except Exception:
                self._roles.pop(role.role_id, None)
                raise
            return role

    def get_role(self, role_id: str) -> RoleDefinition:
        with self._lock:
            role = self._roles.get(role_id)
            if role is None:
                raise KeyError(f"unknown role: {role_id}")
            return role

    def list_roles(self) -> list[RoleDefinition]:
        with self._lock:
            return [self._roles[key] for key in sorted(self._roles)]

    def grant_global_role(self, principal_id: str, role_id: str) -> None:
        with self._lock:
            self.get(principal_id)
            self.get_role(role_id)
            roles = self._global_roles.setdefault(principal_id, [])
            if role_id in roles:
                return
            roles.append(role_id)
            try:
                self._persist()
            except Exception:
                roles.remove(role_id)
                if not roles:
                    self._global_roles.pop(principal_id, None)
                raise

    def revoke_global_role(self, principal_id: str, role_id: str) -> None:
        with self._lock:
            self.get(principal_id)
            self.get_role(role_id)
            roles = self._global_roles.get(principal_id)
            if roles is None or role_id not in roles:
                return
            roles.remove(role_id)
            if not roles:
                self._global_roles.pop(principal_id, None)
            try:
                self._persist()
            except Exception:
                restored = self._global_roles.setdefault(principal_id, [])
                if role_id not in restored:
                    restored.append(role_id)
                raise

    def global_roles(self, principal_id: str) -> tuple[str, ...]:
        with self._lock:
            self.get(principal_id)
            return tuple(self._global_roles.get(principal_id, ()))

    def set_project_membership(self, membership: ProjectMembership) -> None:
        with self._lock:
            self.get(membership.principal_id)
            for role_id in membership.role_ids:
                self.get_role(role_id)
            key = (membership.principal_id, membership.project_id)
            previous = self._memberships.get(key)
            self._memberships[key] = membership
            try:
                self._persist()
            except Exception:
                if previous is None:
                    self._memberships.pop(key, None)
                else:
                    self._memberships[key] = previous
                raise

    def project_membership(
        self,
        principal_id: str,
        project_id: str,
    ) -> ProjectMembership | None:
        with self._lock:
            self.get(principal_id)
            return self._memberships.get((principal_id, project_id))

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported identity store version")

        for raw in payload.get("principals", []):
            kind = raw.get("kind") if isinstance(raw, dict) else None
            if kind == PrincipalKind.USER.value:
                principal: PrincipalRecord = UserPrincipal.model_validate(raw)
            elif kind == PrincipalKind.AGENT.value:
                principal = AgentPrincipal.model_validate(raw)
            elif kind == PrincipalKind.SERVICE_ACCOUNT.value:
                principal = ServiceAccountPrincipal.model_validate(raw)
            elif kind == PrincipalKind.EXTERNAL.value:
                principal = ExternalIdentityPrincipal.model_validate(raw)
            else:
                raise ValueError("unknown principal kind")
            if principal.principal_id in self._principals:
                raise ValueError("duplicate principal id")
            if isinstance(principal, ExternalIdentityPrincipal):
                binding = (principal.provider_id, principal.subject)
                if any(
                    isinstance(existing, ExternalIdentityPrincipal)
                    and (existing.provider_id, existing.subject) == binding
                    for existing in self._principals.values()
                ):
                    raise ValueError("duplicate external identity")
            self._principals[principal.principal_id] = principal

        for raw in payload.get("roles", []):
            role = RoleDefinition.model_validate(raw)
            if role.role_id in self._roles:
                raise ValueError("duplicate role id")
            self._roles[role.role_id] = role

        for raw in payload.get("global_role_grants", []):
            grant = GlobalRoleGrant.model_validate(raw)
            self._require_principal_and_role(grant.principal_id, grant.role_id)
            roles = self._global_roles.setdefault(grant.principal_id, [])
            if grant.role_id in roles:
                raise ValueError("duplicate global role grant")
            roles.append(grant.role_id)

        for raw in payload.get("project_memberships", []):
            membership = ProjectMembership.model_validate(raw)
            self.get(membership.principal_id)
            for role_id in membership.role_ids:
                self.get_role(role_id)
            key = (membership.principal_id, membership.project_id)
            if key in self._memberships:
                raise ValueError("duplicate project membership")
            self._memberships[key] = membership

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "principals": [
                principal.model_dump(mode="json")
                for principal in self._principals.values()
            ],
            "roles": [
                self._roles[key].model_dump(mode="json")
                for key in sorted(self._roles)
            ],
            "global_role_grants": [
                GlobalRoleGrant(
                    principal_id=principal_id,
                    role_id=role_id,
                ).model_dump(mode="json")
                for principal_id in sorted(self._global_roles)
                for role_id in self._global_roles[principal_id]
            ],
            "project_memberships": [
                self._memberships[key].model_dump(mode="json")
                for key in sorted(self._memberships)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _require_principal_and_role(
        self,
        principal_id: str,
        role_id: str,
    ) -> None:
        self.get(principal_id)
        self.get_role(role_id)
