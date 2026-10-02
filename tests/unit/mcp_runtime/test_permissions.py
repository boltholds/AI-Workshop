from __future__ import annotations

import pytest

from ai_workshop.authz.models import PermissionSet
from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.permissions import McpPermissionEvaluator


class FakeAuthorization:
    def __init__(self, permissions):
        self.permissions = frozenset(permissions)

    def effective_permissions(self, principal_id, project_id):
        return PermissionSet(
            principal_id=principal_id,
            project_id=project_id,
            permissions=self.permissions,
        )


class ScopeContext:
    def project_id_for(self, registration):
        if registration.scope is McpRegistrationScope.PROJECT:
            return registration.scope_id
        return None


class ProjectPolicy:
    def __init__(self, permissions):
        self.permissions = frozenset(permissions)

    def permissions_for(self, registration):
        return self.permissions


def registration(*permissions):
    return McpRegistration(
        server_id="writer",
        display_name="Writer",
        transport=McpTransportKind.HTTP,
        scope=McpRegistrationScope.PROJECT,
        scope_id="demo",
        owner_principal_id="alice",
        permissions=frozenset(permissions),
    )


def test_effective_mcp_permissions_use_intersection():
    evaluator = McpPermissionEvaluator(
        FakeAuthorization({"filesystem.read", "filesystem.write", "shell.exec"}),
        ScopeContext(),
        ProjectPolicy({"filesystem.read", "filesystem.write"}),
        deployment_permissions=frozenset({"filesystem.read", "shell.exec"}),
    )

    effective = evaluator.effective_permissions(
        "alice",
        registration(
            "filesystem.read",
            "filesystem.write",
            "shell.exec",
        ),
    )

    assert effective == frozenset({"filesystem.read"})


def test_read_only_caller_cannot_gain_write_from_permissive_server():
    evaluator = McpPermissionEvaluator(
        FakeAuthorization({"filesystem.read"}),
        ScopeContext(),
        ProjectPolicy({"filesystem.read", "filesystem.write"}),
        deployment_permissions=frozenset(
            {"filesystem.read", "filesystem.write"}
        ),
    )

    with pytest.raises(
        PermissionError,
        match="downstream MCP permission denied: filesystem.write",
    ):
        evaluator.require(
            "alice",
            registration("filesystem.read", "filesystem.write"),
            frozenset({"filesystem.write"}),
        )
