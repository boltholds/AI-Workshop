from pathlib import Path

import pytest

from ai_workshop.agents.service import AgentService, DelegationService
from ai_workshop.authz.models import PermissionSet
from ai_workshop.identity.models import UserPrincipal
from ai_workshop.identity.store import PrincipalStore


class FakeRunPermissions:
    def __init__(self, permissions: frozenset[str]):
        self.permissions = permissions

    def effective_permissions_for_run(self, run_id: str) -> PermissionSet:
        assert run_id == "run-parent"
        return PermissionSet(
            principal_id="agent-parent",
            project_id="project-alpha",
            permissions=self.permissions,
        )


def agent_service(tmp_path: Path) -> AgentService:
    principals = PrincipalStore(tmp_path / "identity.json")
    principals.create(
        UserPrincipal(principal_id="user-owner", display_name="Owner")
    )
    service = AgentService(
        principals,
        state_path=tmp_path / "agents.json",
    )
    service.create_persistent(
        "agent-child",
        display_name="Child",
        owner_principal_id="user-owner",
    )
    return service


def test_agent_cannot_delegate_permission_it_does_not_hold(tmp_path: Path):
    agents = agent_service(tmp_path)
    delegation = DelegationService(
        agents,
        FakeRunPermissions(frozenset({"filesystem.read"})),
    )

    with pytest.raises(PermissionError, match="delegated permissions"):
        delegation.delegate(
            "run-parent",
            "agent-child",
            frozenset({"filesystem.read", "filesystem.write"}),
        )


def test_delegation_accepts_strict_subset_of_parent_permissions(tmp_path: Path):
    agents = agent_service(tmp_path)
    delegation = DelegationService(
        agents,
        FakeRunPermissions(
            frozenset({"filesystem.read", "filesystem.write", "git.read"})
        ),
    )

    grant = delegation.delegate(
        "run-parent",
        "agent-child",
        frozenset({"filesystem.read", "git.read"}),
    )

    assert grant.parent_run_id == "run-parent"
    assert grant.child_agent_id == "agent-child"
    assert grant.permissions == frozenset({"filesystem.read", "git.read"})


def test_delegation_rejects_archived_child_agent(tmp_path: Path):
    agents = agent_service(tmp_path)
    agents.archive("agent-child")
    delegation = DelegationService(
        agents,
        FakeRunPermissions(frozenset({"filesystem.read"})),
    )

    with pytest.raises(ValueError, match="archived"):
        delegation.delegate(
            "run-parent",
            "agent-child",
            frozenset({"filesystem.read"}),
        )


def test_delegation_requires_nonempty_permission_set(tmp_path: Path):
    agents = agent_service(tmp_path)
    delegation = DelegationService(
        agents,
        FakeRunPermissions(frozenset({"filesystem.read"})),
    )

    with pytest.raises(ValueError, match="at least one"):
        delegation.delegate("run-parent", "agent-child", frozenset())
