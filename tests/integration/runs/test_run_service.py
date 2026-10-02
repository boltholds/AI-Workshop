from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from ai_workshop.agents.service import AgentService
from ai_workshop.audit.store import AuditStore
from ai_workshop.authz.service import AuthorizationService
from ai_workshop.identity.models import ProjectMembership, RoleDefinition, UserPrincipal
from ai_workshop.identity.store import PrincipalStore
from ai_workshop.runs.models import RunResourceLimits, RunState
from ai_workshop.runs.service import RunService
from ai_workshop.runs.workspaces import RunWorkspace
from ai_workshop.server.models import RuntimeWorkloadState, RuntimeWorkloadStatus


class FakeWorkspaces:
    def __init__(self, root: Path):
        self.root = root
        self.created: list[tuple[str, str, str, bool]] = []
        self.removed: list[str] = []

    def create(self, project_id: str, run_id: str, base_ref: str, writable: bool):
        path = self.root / run_id / "workspace"
        path.mkdir(parents=True)
        self.created.append((project_id, run_id, base_ref, writable))
        return RunWorkspace(
            run_id=run_id,
            project_id=project_id,
            path=path,
            base_ref=base_ref,
            commit_id="a" * 40,
            writable=writable,
        )

    def remove(self, run_id: str) -> None:
        self.removed.append(run_id)


class FakeRuntime:
    def __init__(self):
        self.ensured_images: list[str] = []
        self.created = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.removed: list[str] = []

    def ensure_image(self, image: str) -> None:
        self.ensured_images.append(image)

    def create(self, spec):
        self.created.append(spec)
        return RuntimeWorkloadStatus(
            workload_id=spec.workload_id,
            state=RuntimeWorkloadState.CREATED,
        )

    def start(self, workload_id: str):
        self.started.append(workload_id)
        return RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.RUNNING,
        )

    def stop(self, workload_id: str):
        self.stopped.append(workload_id)
        return RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.STOPPED,
        )

    def remove(self, workload_id: str):
        self.removed.append(workload_id)

    def status(self, workload_id: str):
        return RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.RUNNING,
        )

    def logs(self, workload_id: str, *, tail: int = 200):
        return ""

    def publish_private_endpoint(self, workload_id: str, container_port: int):
        raise AssertionError("not used")


class FakeRunCleaner:
    def __init__(self):
        self.cleaned: list[str] = []

    def cleanup_run(self, run_id: str) -> None:
        self.cleaned.append(run_id)


def configured(tmp_path: Path):
    principals = PrincipalStore(tmp_path / "identity.json")
    principals.create(UserPrincipal(principal_id="user-owner", display_name="Owner"))
    principals.create_role(
        RoleDefinition(
            role_id="ceiling",
            allow=("filesystem.read", "filesystem.write", "git.read", "git.write"),
        )
    )
    principals.create_role(
        RoleDefinition(
            role_id="developer",
            allow=("filesystem.read", "filesystem.write", "git.read", "git.write"),
        )
    )
    principals.create_role(
        RoleDefinition(
            role_id="viewer",
            allow=("filesystem.read", "git.read"),
        )
    )
    agents = AgentService(principals, state_path=tmp_path / "agents.json")
    agents.create_persistent(
        "agent-titan",
        display_name="Titan",
        owner_principal_id="user-owner",
    )
    principals.grant_global_role("agent-titan", "ceiling")
    principals.set_project_membership(
        ProjectMembership(
            principal_id="agent-titan",
            project_id="project-alpha",
            role_ids=("developer",),
        )
    )
    runtime = FakeRuntime()
    workspaces = FakeWorkspaces(tmp_path / "runs")
    audit = AuditStore(tmp_path / "audit.jsonl")
    cleaner = FakeRunCleaner()
    service = RunService(
        agents=agents,
        authorization=AuthorizationService(principals),
        workspaces=workspaces,
        runtime=runtime,
        audit=audit,
        state_path=tmp_path / "runs.json",
        runtime_image="ai-workshop-agent:server",
        run_cleaners=(cleaner,),
    )
    return service, principals, agents, runtime, workspaces, audit, cleaner


def test_run_start_captures_permissions_and_mounts_only_run_workspace(tmp_path: Path):
    service, _, _, runtime, workspaces, audit, _ = configured(tmp_path)

    run = service.start(
        "run-one",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=True,
        limits=RunResourceLimits(cpu_cores=2.0, memory_mb=2048),
    )

    assert run.state is RunState.RUNNING
    assert run.effective_permissions == frozenset(
        {"filesystem.read", "filesystem.write", "git.read", "git.write"}
    )
    assert workspaces.created == [("project-alpha", "run-one", "main", True)]
    spec = runtime.created[0]
    assert runtime.ensured_images == ["ai-workshop-agent:server"]
    assert spec.workload_id == "run-one"
    assert spec.image == "ai-workshop-agent:server"
    assert spec.entrypoint is None
    assert spec.command == ("run-host",)
    assert spec.cpu_limit == 2.0
    assert spec.memory_limit_mb == 2048
    assert len(spec.mounts) == 1
    assert spec.mounts[0].source == run.workspace_path
    assert spec.mounts[0].target == PurePosixPath("/workspace/project")
    assert spec.mounts[0].read_only is False
    assert [item.action for item in audit.query(run_id="run-one")] == ["run.start"]


def test_read_only_run_mount_is_read_only_and_needs_only_read_permission(tmp_path: Path):
    service, principals, _, runtime, _, _, _ = configured(tmp_path)
    principals.set_project_membership(
        ProjectMembership(
            principal_id="agent-titan",
            project_id="project-alpha",
            role_ids=("viewer",),
        )
    )

    run = service.start(
        "run-read",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=False,
    )

    assert run.state is RunState.RUNNING
    assert runtime.created[0].mounts[0].read_only is True


def test_writable_run_requires_filesystem_write(tmp_path: Path):
    service, principals, _, runtime, workspaces, _, _ = configured(tmp_path)
    principals.set_project_membership(
        ProjectMembership(
            principal_id="agent-titan",
            project_id="project-alpha",
            role_ids=("viewer",),
        )
    )

    with pytest.raises(PermissionError, match="filesystem.write"):
        service.start(
            "run-denied",
            agent_id="agent-titan",
            project_id="project-alpha",
            base_ref="main",
            writable=True,
        )

    assert runtime.created == []
    assert workspaces.created == []


def test_run_permissions_are_immutable_after_start(tmp_path: Path):
    service, principals, _, _, _, _, _ = configured(tmp_path)
    service.start(
        "run-one",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=True,
    )

    principals.set_project_membership(
        ProjectMembership(
            principal_id="agent-titan",
            project_id="project-alpha",
            role_ids=("viewer",),
        )
    )

    snapshot = service.effective_permissions_for_run("run-one")
    assert "filesystem.write" in snapshot.permissions


def test_run_stop_cleans_scoped_resources(tmp_path: Path):
    service, _, _, runtime, workspaces, audit, cleaner = configured(tmp_path)
    service.start(
        "run-one",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=True,
    )

    stopped = service.stop("run-one")

    assert stopped.state is RunState.STOPPED
    assert runtime.stopped == ["run-one"]
    assert runtime.removed == ["run-one"]
    assert cleaner.cleaned == ["run-one"]
    assert workspaces.removed == ["run-one"]
    assert [item.action for item in audit.query(run_id="run-one")] == [
        "run.start",
        "run.stop",
    ]


def test_archived_agent_cannot_start_run(tmp_path: Path):
    service, _, agents, runtime, _, _, _ = configured(tmp_path)
    agents.archive("agent-titan")

    with pytest.raises(ValueError, match="archived"):
        service.start(
            "run-one",
            agent_id="agent-titan",
            project_id="project-alpha",
            base_ref="main",
            writable=False,
        )

    assert runtime.created == []


def test_duplicate_run_id_is_rejected(tmp_path: Path):
    service, _, _, _, _, _, _ = configured(tmp_path)
    service.start(
        "run-one",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=False,
    )

    with pytest.raises(ValueError, match="already exists"):
        service.start(
            "run-one",
            agent_id="agent-titan",
            project_id="project-alpha",
            base_ref="main",
            writable=False,
        )


def test_initiator_cannot_start_agent_above_own_project_permissions(tmp_path: Path):
    service, principals, _, runtime, workspaces, _, _ = configured(tmp_path)
    principals.create(UserPrincipal(principal_id="user-viewer", display_name="Viewer"))
    principals.grant_global_role("user-viewer", "ceiling")
    principals.set_project_membership(
        ProjectMembership(
            principal_id="user-viewer",
            project_id="project-alpha",
            role_ids=("viewer",),
        )
    )

    with pytest.raises(PermissionError, match="filesystem.write"):
        service.start(
            "run-escalation",
            agent_id="agent-titan",
            project_id="project-alpha",
            base_ref="main",
            writable=True,
            initiator_principal_id="user-viewer",
        )

    assert runtime.created == []
    assert workspaces.created == []


class FailingAudit:
    def record(self, event) -> None:
        raise OSError("audit unavailable")


def test_run_start_audit_failure_rolls_back_persisted_run(tmp_path: Path):
    service, principals, agents, runtime, workspaces, _, cleaner = configured(tmp_path)
    failing = RunService(
        agents=agents,
        authorization=AuthorizationService(principals),
        workspaces=workspaces,
        runtime=runtime,
        audit=FailingAudit(),
        state_path=tmp_path / "audit-failure-runs.json",
        runtime_image="ai-workshop-agent:server",
        run_cleaners=(cleaner,),
    )

    with pytest.raises(OSError, match="audit unavailable"):
        failing.start(
            "run-audit-failure",
            agent_id="agent-titan",
            project_id="project-alpha",
            base_ref="main",
            writable=False,
        )

    assert failing.list() == []
    assert runtime.stopped == ["run-audit-failure"]
    assert runtime.removed == ["run-audit-failure"]
    assert workspaces.removed == ["run-audit-failure"]

    reloaded = RunService(
        agents=agents,
        authorization=AuthorizationService(principals),
        workspaces=workspaces,
        runtime=runtime,
        audit=AuditStore(tmp_path / "reloaded-audit.jsonl"),
        state_path=tmp_path / "audit-failure-runs.json",
        runtime_image="ai-workshop-agent:server",
    )
    assert reloaded.list() == []


def test_run_status_marks_run_failed_when_runtime_exited(tmp_path: Path):
    service, _, _, runtime, _, _, cleaner = configured(tmp_path)
    service.start(
        "run-one",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=False,
    )
    runtime.status = lambda workload_id: RuntimeWorkloadStatus(
        workload_id=workload_id,
        state=RuntimeWorkloadState.EXITED,
    )

    run = service.status("run-one")

    assert run.state is RunState.FAILED
    assert cleaner.cleaned == ["run-one"]


def test_run_list_reconciles_running_runtime_state(tmp_path: Path):
    service, _, _, runtime, _, _, cleaner = configured(tmp_path)
    service.start(
        "run-one",
        agent_id="agent-titan",
        project_id="project-alpha",
        base_ref="main",
        writable=False,
    )
    runtime.status = lambda workload_id: RuntimeWorkloadStatus(
        workload_id=workload_id,
        state=RuntimeWorkloadState.STOPPED,
    )

    runs = service.list()

    assert runs[0].state is RunState.FAILED
    assert cleaner.cleaned == ["run-one"]
