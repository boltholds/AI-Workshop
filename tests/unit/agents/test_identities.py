from pathlib import Path

import pytest

from ai_workshop.agents.models import AgentLifetime, AgentStatus
from ai_workshop.agents.service import AgentService
from ai_workshop.identity.models import AgentPrincipal, UserPrincipal
from ai_workshop.identity.store import PrincipalStore


def services(tmp_path: Path):
    principals = PrincipalStore(tmp_path / "identity.json")
    principals.create(
        UserPrincipal(principal_id="user-owner", display_name="Owner")
    )
    agents = AgentService(
        principals,
        state_path=tmp_path / "agents.json",
    )
    return principals, agents


def test_persistent_agent_creates_first_class_agent_principal_and_persists(tmp_path: Path):
    principals, agents = services(tmp_path)

    agent = agents.create_persistent(
        "agent-titan",
        display_name="Titan",
        owner_principal_id="user-owner",
    )

    assert agent.lifetime is AgentLifetime.PERSISTENT
    assert agent.status is AgentStatus.ACTIVE
    assert agent.principal_id == "agent-titan"
    principal = principals.get("agent-titan")
    assert isinstance(principal, AgentPrincipal)
    assert principal.display_name == "Titan"

    reloaded = AgentService(
        PrincipalStore(tmp_path / "identity.json"),
        state_path=tmp_path / "agents.json",
    )
    assert reloaded.get("agent-titan") == agent


def test_ephemeral_agent_is_explicit_identity_kind(tmp_path: Path):
    _, agents = services(tmp_path)

    agent = agents.create_ephemeral(
        "agent-task-1",
        display_name="Task Agent",
        owner_principal_id="user-owner",
    )

    assert agent.lifetime is AgentLifetime.EPHEMERAL
    assert agent.status is AgentStatus.ACTIVE


def test_agent_owner_must_be_existing_principal(tmp_path: Path):
    _, agents = services(tmp_path)

    with pytest.raises(KeyError, match="unknown principal"):
        agents.create_persistent(
            "agent-orphan",
            display_name="Orphan",
            owner_principal_id="missing-owner",
        )


def test_duplicate_agent_identity_is_rejected(tmp_path: Path):
    _, agents = services(tmp_path)
    agents.create_persistent(
        "agent-titan",
        display_name="Titan",
        owner_principal_id="user-owner",
    )

    with pytest.raises(ValueError, match="already exists"):
        agents.create_ephemeral(
            "agent-titan",
            display_name="Duplicate",
            owner_principal_id="user-owner",
        )


def test_archive_preserves_principal_for_audit_history(tmp_path: Path):
    principals, agents = services(tmp_path)
    agents.create_persistent(
        "agent-titan",
        display_name="Titan",
        owner_principal_id="user-owner",
    )

    archived = agents.archive("agent-titan")

    assert archived.status is AgentStatus.ARCHIVED
    assert agents.get("agent-titan").status is AgentStatus.ARCHIVED
    assert isinstance(principals.get("agent-titan"), AgentPrincipal)


def test_list_excludes_archived_by_default(tmp_path: Path):
    _, agents = services(tmp_path)
    agents.create_persistent(
        "agent-one",
        display_name="One",
        owner_principal_id="user-owner",
    )
    agents.create_ephemeral(
        "agent-two",
        display_name="Two",
        owner_principal_id="user-owner",
    )
    agents.archive("agent-two")

    assert [item.agent_id for item in agents.list()] == ["agent-one"]
    assert [item.agent_id for item in agents.list(include_archived=True)] == [
        "agent-one",
        "agent-two",
    ]
