from __future__ import annotations

from ai_workshop.runs.models import RunResourceLimits


def _run_payload(run) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "agent_id": run.agent_id,
        "principal_id": run.principal_id,
        "initiator_principal_id": run.initiator_principal_id,
        "project_id": run.project_id,
        "base_ref": run.base_ref,
        "writable": run.writable,
        "effective_permissions": sorted(run.effective_permissions),
        "limits": run.limits.model_dump(),
        "state": run.state.value,
        "created_at": run.created_at.isoformat(),
        "stopped_at": (
            run.stopped_at.isoformat()
            if run.stopped_at is not None
            else None
        ),
    }


def register_run_tools(server, runs, authorization, principal_resolver) -> None:
    def actor() -> str:
        principal_id = principal_resolver.current_principal_id()
        if not principal_id:
            raise RuntimeError("AUTHENTICATION_REQUIRED")
        return principal_id

    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except (KeyError, ValueError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("RUN_OPERATION_FAILED: run operation failed") from None

    @server.tool()
    def runs_list() -> list[dict[str, object]]:
        principal_id = actor()
        visible = []
        for run in safe(runs.list):
            permissions = safe(
                authorization.effective_permissions,
                principal_id,
                run.project_id,
            )
            if permissions.allows("runs.read"):
                visible.append(_run_payload(run))
        return visible

    @server.tool()
    def runs_status(run_id: str) -> dict[str, object]:
        principal_id = actor()
        run = safe(runs.status, run_id)
        safe(
            authorization.require,
            principal_id,
            "runs.read",
            run.project_id,
        )
        return _run_payload(run)

    @server.tool()
    def runs_start(
        run_id: str,
        agent_id: str,
        project_id: str,
        base_ref: str,
        writable: bool,
        cpu_cores: float = 2.0,
        memory_mb: int = 4096,
    ) -> dict[str, object]:
        principal_id = actor()
        safe(
            authorization.require,
            principal_id,
            "runs.start",
            project_id,
        )
        limits = RunResourceLimits(
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
        )
        run = safe(
            runs.start,
            run_id,
            agent_id=agent_id,
            project_id=project_id,
            base_ref=base_ref,
            writable=writable,
            limits=limits,
            initiator_principal_id=principal_id,
        )
        return _run_payload(run)

    @server.tool()
    def runs_stop(run_id: str) -> dict[str, object]:
        principal_id = actor()
        run = safe(runs.status, run_id)
        safe(
            authorization.require,
            principal_id,
            "runs.stop",
            run.project_id,
        )
        stopped = safe(
            runs.stop,
            run_id,
            initiator_principal_id=principal_id,
        )
        return _run_payload(stopped)
