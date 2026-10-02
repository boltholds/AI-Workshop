from __future__ import annotations

from typing import Protocol

from ai_workshop.mcp_runtime.models import McpRegistration


class McpScopeContextResolver(Protocol):
    def project_id_for(
        self,
        registration: McpRegistration,
    ) -> str | None: ...


class McpProjectPolicy(Protocol):
    def permissions_for(
        self,
        registration: McpRegistration,
    ) -> frozenset[str]: ...


class McpPermissionEvaluator:
    def __init__(
        self,
        authorization,
        scope_context: McpScopeContextResolver,
        project_policy: McpProjectPolicy,
        *,
        deployment_permissions: frozenset[str],
    ):
        self.authorization = authorization
        self.scope_context = scope_context
        self.project_policy = project_policy
        self.deployment_permissions = frozenset(deployment_permissions)

    def effective_permissions(
        self,
        principal_id: str,
        registration: McpRegistration,
    ) -> frozenset[str]:
        project_id = self.scope_context.project_id_for(registration)
        caller = self.authorization.effective_permissions(
            principal_id,
            project_id,
        ).permissions
        project = self.project_policy.permissions_for(registration)
        return frozenset(
            set(caller)
            & set(registration.permissions)
            & set(project)
            & set(self.deployment_permissions)
        )

    def require(
        self,
        principal_id: str,
        registration: McpRegistration,
        required: frozenset[str],
    ) -> frozenset[str]:
        effective = self.effective_permissions(
            principal_id,
            registration,
        )
        missing = sorted(set(required) - set(effective))
        if missing:
            raise PermissionError(
                "downstream MCP permission denied: " + missing[0]
            )
        return effective
