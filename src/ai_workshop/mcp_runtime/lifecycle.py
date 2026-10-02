from __future__ import annotations

from ai_workshop.mcp_runtime.models import McpRegistrationScope


class RunScopedMcpCleaner:
    def __init__(self, registry, transports):
        self.registry = registry
        self.transports = transports

    def cleanup_run(self, run_id: str) -> None:
        records = [
            record
            for record in self.registry.list()
            if record.registration.scope is McpRegistrationScope.RUN
            and record.registration.scope_id == run_id
        ]

        errors: list[Exception] = []
        for record in records:
            server_id = record.registration.server_id
            try:
                self.transports.stop(server_id)
            except Exception as exc:
                errors.append(exc)

        removed = self.registry.remove_scope("run", run_id)
        if errors:
            raise RuntimeError(
                f"failed to stop {len(errors)} run-scoped MCP runtime(s)"
            ) from errors[0]

        expected = tuple(
            sorted(record.registration.server_id for record in records)
        )
        if tuple(sorted(removed)) != expected:
            raise RuntimeError("run-scoped MCP registry cleanup mismatch")
