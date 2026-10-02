from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from ai_workshop.agents.models import AgentIdentity, AgentLifetime
from ai_workshop.authz.models import PermissionSet
from ai_workshop.gateway.agent_tools import register_agent_tools
from ai_workshop.gateway.run_tools import register_run_tools
from ai_workshop.gateway.server import build_server
from ai_workshop.runs.models import AgentRun, RunResourceLimits, RunState


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


class FakeResolver:
    def __init__(self, principal_id: str = "user-operator"):
        self.principal_id = principal_id

    def current_principal_id(self) -> str:
        return self.principal_id


class FakeAuthorization:
    def __init__(self):
        self.allowed: dict[tuple[str, str | None], set[str]] = {}

    def allow(self, principal_id: str, project_id: str | None, *permissions: str):
        self.allowed.setdefault((principal_id, project_id), set()).update(permissions)

    def effective_permissions(self, principal_id: str, project_id: str | None):
        return PermissionSet(
            principal_id=principal_id,
            project_id=project_id,
            permissions=frozenset(self.allowed.get((principal_id, project_id), set())),
        )

    def require(self, principal_id: str, permission: str, project_id: str | None):
        result = self.effective_permissions(principal_id, project_id)
        if not result.allows(permission):
            raise PermissionError(f"permission denied: {permission}")
        return result


class FakeAgents:
    def __init__(self):
        self.items = {
            "agent-titan": AgentIdentity(
                agent_id="agent-titan",
                principal_id="agent-titan",
                display_name="Titan",
                owner_principal_id="user-owner",
                lifetime=AgentLifetime.PERSISTENT,
            )
        }
        self.last = None

    def list(self, *, include_archived: bool = False):
        return list(self.items.values())

    def get(self, agent_id: str):
        return self.items[agent_id]

    def create_persistent(self, agent_id: str, *, display_name: str, owner_principal_id: str):
        self.last = ("persistent", agent_id, display_name, owner_principal_id)
        agent = AgentIdentity(
            agent_id=agent_id,
            principal_id=agent_id,
            display_name=display_name,
            owner_principal_id=owner_principal_id,
            lifetime=AgentLifetime.PERSISTENT,
        )
        self.items[agent_id] = agent
        return agent

    def create_ephemeral(self, agent_id: str, *, display_name: str, owner_principal_id: str):
        self.last = ("ephemeral", agent_id, display_name, owner_principal_id)
        agent = AgentIdentity(
            agent_id=agent_id,
            principal_id=agent_id,
            display_name=display_name,
            owner_principal_id=owner_principal_id,
            lifetime=AgentLifetime.EPHEMERAL,
        )
        self.items[agent_id] = agent
        return agent

    def archive(self, agent_id: str):
        self.last = ("archive", agent_id)
        return self.items[agent_id]


class FakeRuns:
    def __init__(self):
        self.last = None
        self.items = {
            "run-visible": self._run("run-visible", "project-visible"),
            "run-hidden": self._run("run-hidden", "project-hidden"),
        }

    @staticmethod
    def _run(run_id: str, project_id: str):
        return AgentRun(
            run_id=run_id,
            agent_id="agent-titan",
            principal_id="agent-titan",
            initiator_principal_id="user-operator",
            project_id=project_id,
            base_ref="main",
            writable=True,
            workspace_path=Path(f"/srv/ai-workshop/runs/{run_id}/workspace"),
            effective_permissions=frozenset({"filesystem.read"}),
            limits=RunResourceLimits(cpu_cores=1.0, memory_mb=512),
            state=RunState.RUNNING,
        )

    def list(self):
        return list(self.items.values())

    def status(self, run_id: str):
        return self.items[run_id]

    def start(
        self,
        run_id: str,
        *,
        agent_id: str,
        project_id: str,
        base_ref: str,
        writable: bool,
        limits: RunResourceLimits,
        initiator_principal_id: str | None = None,
    ):
        self.last = (
            "start",
            run_id,
            agent_id,
            project_id,
            base_ref,
            writable,
            limits,
            initiator_principal_id,
        )
        run = AgentRun(
            run_id=run_id,
            agent_id=agent_id,
            principal_id=agent_id,
            initiator_principal_id=initiator_principal_id or agent_id,
            project_id=project_id,
            base_ref=base_ref,
            writable=writable,
            workspace_path=Path(f"/srv/ai-workshop/runs/{run_id}/workspace"),
            effective_permissions=frozenset({"filesystem.read"}),
            limits=limits,
            state=RunState.RUNNING,
        )
        self.items[run_id] = run
        return run

    def stop(self, run_id: str, *, initiator_principal_id: str | None = None):
        self.last = ("stop", run_id, initiator_principal_id)
        return self.items[run_id]


def test_agent_create_uses_trusted_actor_as_owner():
    server = FakeServer()
    agents = FakeAgents()
    authz = FakeAuthorization()
    resolver = FakeResolver()
    authz.allow("user-operator", None, "agents.manage")
    register_agent_tools(server, agents, authz, resolver)

    created = server.tools["agents_create_persistent"]("agent-review", "Review")

    assert created["agent_id"] == "agent-review"
    assert agents.last == (
        "persistent",
        "agent-review",
        "Review",
        "user-operator",
    )
    params = inspect.signature(server.tools["agents_create_persistent"]).parameters
    assert "owner_principal_id" not in params
    assert "actor_id" not in params
    assert "principal_id" not in params


def test_agent_mutation_requires_permission():
    server = FakeServer()
    register_agent_tools(
        server,
        FakeAgents(),
        FakeAuthorization(),
        FakeResolver(),
    )

    with pytest.raises(RuntimeError, match="permission denied: agents.manage"):
        server.tools["agents_archive"]("agent-titan")


def test_run_start_uses_trusted_actor_and_has_no_runtime_escape_parameters():
    server = FakeServer()
    runs = FakeRuns()
    authz = FakeAuthorization()
    resolver = FakeResolver()
    authz.allow(
        "user-operator",
        "project-visible",
        "runs.start",
        "runs.read",
        "runs.stop",
        "filesystem.read",
        "filesystem.write",
    )
    register_run_tools(server, runs, authz, resolver)

    result = server.tools["runs_start"](
        "run-new",
        "agent-titan",
        "project-visible",
        "main",
        True,
        2.0,
        2048,
    )

    assert result["run_id"] == "run-new"
    assert "workspace_path" not in result
    assert runs.last[-1] == "user-operator"
    params = inspect.signature(server.tools["runs_start"]).parameters
    forbidden = {
        "actor_id",
        "principal_id",
        "initiator_principal_id",
        "runtime_image",
        "image",
        "workspace_path",
        "permissions",
    }
    assert forbidden.isdisjoint(params)


def test_run_start_requires_project_permission():
    server = FakeServer()
    runs = FakeRuns()
    register_run_tools(
        server,
        runs,
        FakeAuthorization(),
        FakeResolver(),
    )

    with pytest.raises(RuntimeError, match="permission denied: runs.start"):
        server.tools["runs_start"](
            "run-new",
            "agent-titan",
            "project-visible",
            "main",
            False,
            1.0,
            512,
        )

    assert runs.last is None


def test_runs_list_filters_projects_actor_cannot_read():
    server = FakeServer()
    runs = FakeRuns()
    authz = FakeAuthorization()
    authz.allow("user-operator", "project-visible", "runs.read")
    register_run_tools(server, runs, authz, FakeResolver())

    result = server.tools["runs_list"]()

    assert [item["run_id"] for item in result] == ["run-visible"]
    assert "workspace_path" not in result[0]


def test_runs_stop_checks_permission_before_mutation():
    server = FakeServer()
    runs = FakeRuns()
    authz = FakeAuthorization()
    register_run_tools(server, runs, authz, FakeResolver())

    with pytest.raises(RuntimeError, match="permission denied: runs.stop"):
        server.tools["runs_stop"]("run-visible")

    assert runs.last is None


def test_build_server_fails_closed_without_principal_resolver():
    with pytest.raises(ValueError, match="principal resolver"):
        build_server(
            "http://127.0.0.1:8766",
            token="workspace-token",
            agent_service=FakeAgents(),
            run_service=FakeRuns(),
            authorization_service=FakeAuthorization(),
        )


def test_build_server_registers_agent_run_tools_with_trusted_actor():
    agents = FakeAgents()
    runs = FakeRuns()
    authz = FakeAuthorization()
    authz.allow("user-operator", None, "agents.read", "agents.manage")
    authz.allow(
        "user-operator",
        "project-visible",
        "runs.read",
        "runs.start",
        "runs.stop",
        "filesystem.read",
    )
    server = build_server(
        "http://127.0.0.1:8766",
        token="workspace-token",
        agent_service=agents,
        run_service=runs,
        authorization_service=authz,
        principal_resolver=FakeResolver(),
    )

    import asyncio
    names = {tool.name for tool in asyncio.run(server.list_tools())}

    assert {
        "agents_list",
        "agents_get",
        "agents_create_persistent",
        "agents_create_ephemeral",
        "agents_archive",
        "runs_list",
        "runs_status",
        "runs_start",
        "runs_stop",
    } <= names
