from __future__ import annotations

import json
from pathlib import Path
import threading

from ai_workshop.mcp_runtime.models import (
    McpDiscoveredCapabilities,
    McpRegistration,
    McpRegistrationScope,
    McpServerRecord,
    McpServerState,
)


class McpRegistryStore:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._records: dict[str, McpServerRecord] = {}
        self._load()

    def register(self, registration: McpRegistration) -> McpServerRecord:
        with self._lock:
            if registration.server_id in self._records:
                raise ValueError(f"MCP server already registered: {registration.server_id}")
            record = McpServerRecord(
                registration=registration,
                capabilities=McpDiscoveredCapabilities(server_id=registration.server_id),
            )
            self._records[registration.server_id] = record
            try:
                self._persist()
            except Exception:
                self._records.pop(registration.server_id, None)
                raise
            return record

    def get(self, server_id: str) -> McpServerRecord:
        with self._lock:
            record = self._records.get(server_id)
            if record is None:
                raise KeyError(f"unknown MCP server: {server_id}")
            return record

    def list(self) -> list[McpServerRecord]:
        with self._lock:
            return [self._records[key] for key in sorted(self._records)]

    def set_state(self, server_id: str, state: McpServerState) -> McpServerRecord:
        with self._lock:
            current = self.get(server_id)
            registration = current.registration.model_copy(update={"state": state})
            updated = current.model_copy(update={"registration": registration})
            self._records[server_id] = updated
            self._persist()
            return updated

    def update_capabilities(
        self,
        server_id: str,
        capabilities: McpDiscoveredCapabilities,
    ) -> McpServerRecord:
        with self._lock:
            current = self.get(server_id)
            if capabilities.server_id != server_id:
                raise ValueError("MCP capability server_id mismatch")
            if capabilities.revision <= current.capabilities.revision:
                raise ValueError("MCP capability revision must increase")
            updated = current.model_copy(update={"capabilities": capabilities})
            self._records[server_id] = updated
            self._persist()
            return updated

    def remove(self, server_id: str, *, actor_principal_id: str) -> None:
        with self._lock:
            current = self.get(server_id)
            if current.registration.owner_principal_id != actor_principal_id:
                raise PermissionError("MCP registration owner required")
            self._records.pop(server_id)
            try:
                self._persist()
            except Exception:
                self._records[server_id] = current
                raise

    def remove_scope(
        self,
        scope: str,
        scope_id: str,
    ) -> tuple[str, ...]:
        parsed_scope = McpRegistrationScope(scope)
        with self._lock:
            removed = tuple(
                key
                for key, record in sorted(self._records.items())
                if record.registration.scope is parsed_scope
                and record.registration.scope_id == scope_id
            )
            snapshot = {key: self._records[key] for key in removed}
            for key in removed:
                self._records.pop(key)
            try:
                self._persist()
            except Exception:
                self._records.update(snapshot)
                raise
            return removed

    def export_metadata(self) -> tuple[McpServerRecord, ...]:
        with self._lock:
            return tuple(self._records[key] for key in sorted(self._records))

    def restore_metadata(
        self,
        records: tuple[McpServerRecord, ...],
    ) -> None:
        restored: dict[str, McpServerRecord] = {}
        for record in records:
            server_id = record.registration.server_id
            if server_id in restored:
                raise ValueError("duplicate MCP server registration")
            registration = record.registration.model_copy(
                update={"state": McpServerState.STOPPED}
            )
            restored[server_id] = record.model_copy(
                update={"registration": registration}
            )

        with self._lock:
            previous = self._records
            self._records = restored
            try:
                self._persist()
            except Exception:
                self._records = previous
                raise

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported MCP registry version")
        raw_records = payload.get("servers", [])
        if not isinstance(raw_records, list):
            raise ValueError("MCP registry servers must be a list")
        for raw in raw_records:
            record = McpServerRecord.model_validate(raw)
            server_id = record.registration.server_id
            if server_id in self._records:
                raise ValueError("duplicate MCP server registration")
            if record.capabilities.server_id != server_id:
                raise ValueError("MCP capability server_id mismatch")
            self._records[server_id] = record

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "servers": [
                self._records[key].model_dump(mode="json")
                for key in sorted(self._records)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
