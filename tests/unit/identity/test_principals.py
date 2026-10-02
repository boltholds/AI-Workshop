from __future__ import annotations

from pathlib import Path

import pytest

from ai_workshop.identity.models import (
    AgentPrincipal,
    ExternalIdentityPrincipal,
    ProjectMembership,
    RoleDefinition,
    ServiceAccountPrincipal,
    UserPrincipal,
)
from ai_workshop.identity.store import PrincipalStore


def store(tmp_path: Path) -> PrincipalStore:
    return PrincipalStore(tmp_path / "identity.json")


def test_principal_variants_persist_and_reload(tmp_path: Path):
    identity = store(tmp_path)
    records = [
        UserPrincipal(principal_id="user-gracie", display_name="Gracie"),
        AgentPrincipal(principal_id="agent-titan", display_name="Titan"),
        ServiceAccountPrincipal(
            principal_id="service-ci",
            display_name="CI Service",
        ),
        ExternalIdentityPrincipal(
            principal_id="external-github",
            display_name="GitHub Identity",
            provider_id="github",
            subject="49822014",
        ),
    ]

    for record in records:
        assert identity.create(record) == record

    reloaded = PrincipalStore(tmp_path / "identity.json")
    assert reloaded.list() == records
    assert reloaded.get("agent-titan") == records[1]


def test_duplicate_principal_id_is_rejected(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(UserPrincipal(principal_id="user-one", display_name="One"))

    with pytest.raises(ValueError, match="already exists"):
        identity.create(
            AgentPrincipal(principal_id="user-one", display_name="Collision")
        )


def test_external_identity_provider_subject_is_unique(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(
        ExternalIdentityPrincipal(
            principal_id="external-one",
            display_name="First",
            provider_id="github",
            subject="subject-1",
        )
    )

    with pytest.raises(ValueError, match="external identity"):
        identity.create(
            ExternalIdentityPrincipal(
                principal_id="external-two",
                display_name="Second",
                provider_id="github",
                subject="subject-1",
            )
        )


def test_roles_and_global_grants_persist(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(UserPrincipal(principal_id="user-one", display_name="One"))
    role = RoleDefinition(
        role_id="developer",
        allow=("filesystem.read", "filesystem.write", "git.read", "git.write"),
        deny=("admin.manage",),
    )

    identity.create_role(role)
    identity.grant_global_role("user-one", "developer")

    assert identity.get_role("developer") == role
    assert identity.global_roles("user-one") == ("developer",)

    reloaded = PrincipalStore(tmp_path / "identity.json")
    assert reloaded.get_role("developer") == role
    assert reloaded.global_roles("user-one") == ("developer",)


def test_role_can_be_granted_to_agent_principal(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(AgentPrincipal(principal_id="agent-review", display_name="Review"))
    identity.create_role(
        RoleDefinition(role_id="reviewer", allow=("filesystem.read", "git.read"))
    )

    identity.grant_global_role("agent-review", "reviewer")

    assert identity.global_roles("agent-review") == ("reviewer",)


def test_unknown_role_grant_is_rejected(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(UserPrincipal(principal_id="user-one", display_name="One"))

    with pytest.raises(KeyError, match="unknown role"):
        identity.grant_global_role("user-one", "missing")


def test_project_membership_persists_named_roles(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(UserPrincipal(principal_id="user-one", display_name="One"))
    identity.create_role(RoleDefinition(role_id="viewer", allow=("filesystem.read",)))
    identity.create_role(
        RoleDefinition(
            role_id="developer",
            allow=("filesystem.read", "filesystem.write"),
        )
    )

    membership = ProjectMembership(
        principal_id="user-one",
        project_id="project-alpha",
        role_ids=("viewer", "developer"),
    )
    identity.set_project_membership(membership)

    loaded = identity.project_membership("user-one", "project-alpha")
    assert loaded == membership

    reloaded = PrincipalStore(tmp_path / "identity.json")
    assert reloaded.project_membership("user-one", "project-alpha") == membership


def test_project_membership_rejects_unknown_role(tmp_path: Path):
    identity = store(tmp_path)
    identity.create(UserPrincipal(principal_id="user-one", display_name="One"))

    with pytest.raises(KeyError, match="unknown role"):
        identity.set_project_membership(
            ProjectMembership(
                principal_id="user-one",
                project_id="project-alpha",
                role_ids=("missing",),
            )
        )


def test_models_reject_duplicate_permission_and_role_entries():
    with pytest.raises(ValueError, match="duplicate"):
        RoleDefinition(
            role_id="bad",
            allow=("git.read", "git.read"),
        )

    with pytest.raises(ValueError, match="duplicate"):
        ProjectMembership(
            principal_id="user-one",
            project_id="project-alpha",
            role_ids=("viewer", "viewer"),
        )
