from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ai_workshop.audit.models import AuditEvent


class AuditService(Protocol):
    def record(self, event: AuditEvent) -> None: ...

    def query(
        self,
        *,
        actor_principal_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        action: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[AuditEvent]: ...
