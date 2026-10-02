from pathlib import Path

import pytest

from ai_workshop.authz.service import AuthorizationService
from ai_workshop.identity.models import (
    ProjectMembership,
    RoleDefinition,
    UserPrincipal,
)
from ai_workshop.identity.store import PrincipalStore


def configured_identity(tmp_path: Path) -> PrincipalStore:
    identity = PrincipalStore(tmp_path / "identity.json")
    identity.create(UserPrincipal(principal_id="user-one", display_name="One"))
    identity.create_role(
        RoleDefinition(
            role_id="developer-ceiling",
            allow=(
                "filesystem.read",
                "filesystem.write",
                "git.read",
                "git.write",
                "git.force_push",
            ),
            deny=("admin.manage", "git.force_push"),
        )
    )
    identity.create_role(
        RoleDefinition(
            role_id="project-developer",
            allow=(
                "filesystem.read",
                "filesystem.write",
                "git.read",
                "git.write",
                "git.force_push",
                "admin.manage",
            ),
        )
    )
    identity.create_role(
        RoleDefinition(
            role_id="project-viewer",
            allow=("filesystem.read", "git.read"),
        )
    )
    identity.create_role(
        RoleDefinition(
            role_id="project-no-git-write",
            allow=("filesystem.read", "filesystem.write", "git.read", "git.write"),
            deny=("git.write",),
        )
    )
    identity.grant_global_role("user-one", "developer-ceiling")
    return identity


def test_global_permissions_are_available_without_project_scope(tmp_path: Path):
    authz = AuthorizationService(configured_identity(tmp_path))

    result = authz.effective_permissions("user-one", None)

    assert result.permissions == frozenset(
        {"filesystem.read", "filesystem.write", "git.read", "git.write"}
    )
    assert result.project_id is None


def test_project_membership_narrows_global_permissions(tmp_path: Path):
    identity = configured_identity(tmp_path)
    identity.set_project_membership(
        ProjectMembership(
            principal_id="user-one",
            project_id="project-alpha",
            role_ids=("project-viewer",),
        )
    )
    authz = AuthorizationService(identity)

    result = authz.effective_permissions("user-one", "project-alpha")

    assert result.permissions == frozenset({"filesystem.read", "git.read"})


def test_project_membership_cannot_expand_global_denial(tmp_path: Path):
    identity = configured_identity(tmp_path)
    identity.set_project_membership(
        ProjectMembership(
            principal_id="user-one",
            project_id="project-alpha",
            role_ids=("project-developer",),
        )
    )
    authz = AuthorizationService(identity)

    result = authz.effective_permissions("user-one", "project-alpha")

    assert "git.force_push" not in result.permissions
    assert "admin.manage" not in result.permissions
    assert "filesystem.write" in result.permissions


def test_project_deny_wins_over_project_allow(tmp_path: Path):
    identity = configured_identity(tmp_path)
    identity.set_project_membership(
        ProjectMembership(
            principal_id="user-one",
            project_id="project-alpha",
            role_ids=("project-developer", "project-no-git-write"),
        )
    )
    authz = AuthorizationService(identity)

    result = authz.effective_permissions("user-one", "project-alpha")

    assert "git.write" not in result.permissions
    assert "filesystem.write" in result.permissions


def test_project_scope_requires_membership(tmp_path: Path):
    authz = AuthorizationService(configured_identity(tmp_path))

    result = authz.effective_permissions("user-one", "project-alpha")

    assert result.permissions == frozenset()


def test_require_returns_permission_set_when_allowed(tmp_path: Path):
    identity = configured_identity(tmp_path)
    identity.set_project_membership(
        ProjectMembership(
            principal_id="user-one",
            project_id="project-alpha",
            role_ids=("project-developer",),
        )
    )
    authz = AuthorizationService(identity)

    result = authz.require("user-one", "git.write", "project-alpha")

    assert result.allows("git.write") is True


def test_require_rejects_missing_permission(tmp_path: Path):
    identity = configured_identity(tmp_path)
    identity.set_project_membership(
        ProjectMembership(
            principal_id="user-one",
            project_id="project-alpha",
            role_ids=("project-viewer",),
        )
    )
    authz = AuthorizationService(identity)

    with pytest.raises(PermissionError, match="permission denied"):
        authz.require("user-one", "filesystem.write", "project-alpha")
