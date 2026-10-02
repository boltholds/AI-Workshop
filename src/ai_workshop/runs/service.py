from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import threading

from ai_workshop.agents.models import AgentStatus
from ai_workshop.agents.service import AgentService
from ai_workshop.audit.models import AuditEvent, AuditOutcome
from ai_workshop.audit.protocol import AuditService
from ai_workshop.authz.models import PermissionSet
from ai_workshop.authz.service import AuthorizationService
from ai_workshop.runs.models import AgentRun, RunResourceLimits, RunState
from ai_workshop.runs.protocol import RunScopedResourceCleaner
from ai_workshop.runs.workspaces import RunWorkspaceManager
from ai_workshop.server.models import (
    RuntimeMount,
    RuntimeWorkloadKind,
    RuntimeWorkloadSpec,
    RuntimeWorkloadState,
)
from ai_workshop.server.runtime import RuntimeController


class RunService:
    def __init__(
        self,
        *,
        agents: AgentService,
        authorization: AuthorizationService,
        workspaces: RunWorkspaceManager,
        runtime: RuntimeController,
        audit: AuditService,
        state_path: Path,
        runtime_image: str,
        run_cleaners: tuple[RunScopedResourceCleaner, ...] = (),
    ):
        self.agents = agents
        self.authorization = authorization
        self.workspaces = workspaces
        self.runtime = runtime
        self.audit = audit
        self.state_path = Path(state_path)
        self.runtime_image = runtime_image
        self.run_cleaners = run_cleaners
        self._lock = threading.RLock()
        self._runs: dict[str, AgentRun] = {}
        self._load()

    def start(
        self,
        run_id: str,
        *,
        agent_id: str,
        project_id: str,
        base_ref: str,
        writable: bool,
        limits: RunResourceLimits = RunResourceLimits(),
        initiator_principal_id: str | None = None,
    ) -> AgentRun:
        with self._lock:
            if run_id in self._runs:
                raise ValueError(f"run already exists: {run_id}")

            agent = self.agents.get(agent_id)
            if agent.status is AgentStatus.ARCHIVED:
                raise ValueError("cannot start run for archived agent")

            agent_permissions = self.authorization.effective_permissions(
                agent.principal_id,
                project_id,
            )
            initiator_id = initiator_principal_id or agent.principal_id
            if initiator_id == agent.principal_id:
                permissions = agent_permissions
            else:
                initiator_permissions = self.authorization.effective_permissions(
                    initiator_id,
                    project_id,
                )
                permissions = PermissionSet(
                    principal_id=agent.principal_id,
                    project_id=project_id,
                    permissions=(
                        agent_permissions.permissions
                        & initiator_permissions.permissions
                    ),
                )

            required = "filesystem.write" if writable else "filesystem.read"
            if not permissions.allows(required):
                raise PermissionError(f"permission denied: {required}")

            self.runtime.ensure_image(self.runtime_image)
            workspace = self.workspaces.create(
                project_id,
                run_id,
                base_ref,
                writable,
            )
            created = False
            started = False
            state_persisted = False
            try:
                spec = RuntimeWorkloadSpec(
                    workload_id=run_id,
                    image=self.runtime_image,
                    command=("run-host",),
                    kind=RuntimeWorkloadKind.AGENT_RUN,
                    mounts=(
                        RuntimeMount(
                            source=workspace.path,
                            target=PurePosixPath("/workspace/project"),
                            read_only=not writable,
                        ),
                    ),
                    cpu_limit=limits.cpu_cores,
                    memory_limit_mb=limits.memory_mb,
                )
                self.runtime.create(spec)
                created = True
                self.runtime.start(run_id)
                started = True

                run = AgentRun(
                    run_id=run_id,
                    agent_id=agent_id,
                    principal_id=agent.principal_id,
                    initiator_principal_id=initiator_id,
                    project_id=project_id,
                    base_ref=base_ref,
                    writable=writable,
                    workspace_path=workspace.path,
                    effective_permissions=permissions.permissions,
                    limits=limits,
                    state=RunState.RUNNING,
                )
                self._runs[run_id] = run
                self._persist()
                state_persisted = True
                self.audit.record(
                    AuditEvent(
                        actor_principal_id=initiator_id,
                        owner_principal_id=agent.owner_principal_id,
                        run_id=run_id,
                        project_id=project_id,
                        action="run.start",
                        resource=run_id,
                        outcome=AuditOutcome.SUCCESS,
                    )
                )
                return run
            except Exception as exc:
                self._runs.pop(run_id, None)
                rollback_persist_error: Exception | None = None
                if state_persisted:
                    try:
                        self._persist()
                    except Exception as rollback_exc:
                        rollback_persist_error = rollback_exc
                if started:
                    try:
                        self.runtime.stop(run_id)
                    except Exception:
                        pass
                if created:
                    try:
                        self.runtime.remove(run_id)
                    except Exception:
                        pass
                try:
                    self.workspaces.remove(run_id)
                except Exception:
                    pass
                if rollback_persist_error is not None:
                    raise RuntimeError(
                        "run rollback state persistence failed"
                    ) from rollback_persist_error
                raise exc

    def stop(
        self,
        run_id: str,
        *,
        initiator_principal_id: str | None = None,
    ) -> AgentRun:
        with self._lock:
            current = self._require(run_id)
            if current.state is RunState.STOPPED:
                return current

            errors: list[Exception] = []
            for operation in (
                lambda: self.runtime.stop(run_id),
                lambda: self.runtime.remove(run_id),
            ):
                try:
                    operation()
                except Exception as exc:
                    errors.append(exc)

            for cleaner in self.run_cleaners:
                try:
                    cleaner.cleanup_run(run_id)
                except Exception as exc:
                    errors.append(exc)

            try:
                self.workspaces.remove(run_id)
            except Exception as exc:
                errors.append(exc)

            stopped = current.model_copy(
                update={
                    "state": RunState.STOPPED if not errors else RunState.FAILED,
                    "stopped_at": datetime.now(timezone.utc),
                }
            )
            self._runs[run_id] = stopped
            self._persist()
            self.audit.record(
                AuditEvent(
                    actor_principal_id=(
                        initiator_principal_id
                        or current.principal_id
                    ),
                    owner_principal_id=self.agents.get(current.agent_id).owner_principal_id,
                    run_id=run_id,
                    project_id=current.project_id,
                    action="run.stop",
                    resource=run_id,
                    outcome=(
                        AuditOutcome.SUCCESS
                        if not errors
                        else AuditOutcome.FAILURE
                    ),
                    message=(
                        ""
                        if not errors
                        else f"{len(errors)} run cleanup operation(s) failed"
                    ),
                )
            )
            if errors:
                raise RuntimeError(
                    f"run cleanup failed in {len(errors)} operation(s)"
                ) from errors[0]
            return stopped

    def status(self, run_id: str) -> AgentRun:
        with self._lock:
            return self._reconcile_runtime_state(self._require(run_id))

    def list(self) -> list[AgentRun]:
        with self._lock:
            return [
                self._reconcile_runtime_state(self._runs[key])
                for key in sorted(self._runs)
            ]

    def effective_permissions_for_run(self, run_id: str) -> PermissionSet:
        run = self.status(run_id)
        return PermissionSet(
            principal_id=run.principal_id,
            project_id=run.project_id,
            permissions=run.effective_permissions,
        )

    def _reconcile_runtime_state(self, run: AgentRun) -> AgentRun:
        if run.state is not RunState.RUNNING:
            return run
        runtime_status = self.runtime.status(run.run_id)
        if runtime_status.state is RuntimeWorkloadState.RUNNING:
            return run

        cleanup_errors: list[Exception] = []
        for cleaner in self.run_cleaners:
            try:
                cleaner.cleanup_run(run.run_id)
            except Exception as exc:
                cleanup_errors.append(exc)

        failed = run.model_copy(update={"state": RunState.FAILED})
        self._runs[run.run_id] = failed
        try:
            self._persist()
        except Exception:
            self._runs[run.run_id] = run
            raise
        if cleanup_errors:
            raise RuntimeError(
                f"run reconciliation cleanup failed in {len(cleanup_errors)} operation(s)"
            ) from cleanup_errors[0]
        return failed

    def _require(self, run_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run: {run_id}")
        return run

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported run store version")
        for raw in payload.get("runs", []):
            run = AgentRun.model_validate(raw)
            if run.run_id in self._runs:
                raise ValueError("duplicate run id")
            self._runs[run.run_id] = run

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "runs": [
                self._runs[key].model_dump(mode="json")
                for key in sorted(self._runs)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
