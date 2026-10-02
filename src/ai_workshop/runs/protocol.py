from __future__ import annotations

from typing import Protocol

from ai_workshop.authz.models import PermissionSet
from ai_workshop.runs.models import AgentRun, RunResourceLimits


class RunScopedResourceCleaner(Protocol):
    def cleanup_run(self, run_id: str) -> None: ...


class RunServiceProtocol(Protocol):
    def start(
        self,
        run_id: str,
        *,
        agent_id: str,
        project_id: str,
        base_ref: str,
        writable: bool,
        limits: RunResourceLimits = RunResourceLimits(),
    ) -> AgentRun: ...

    def stop(self, run_id: str) -> AgentRun: ...

    def status(self, run_id: str) -> AgentRun: ...

    def list(self) -> list[AgentRun]: ...

    def effective_permissions_for_run(self, run_id: str) -> PermissionSet: ...
