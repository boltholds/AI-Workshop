from __future__ import annotations

from datetime import datetime
from pathlib import Path
import threading

from ai_workshop.audit.models import AuditEvent


_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "password",
    "secret",
    "private_key",
    "private-key",
    "credential",
    "authorization",
    "api_key",
    "api-key",
    "access_key",
    "access-key",
    "refresh_token",
    "refresh-token",
)


class AuditStore:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._events: list[AuditEvent] = []
        self._load()

    def record(self, event: AuditEvent) -> None:
        normalized = self._redact_event(event)
        line = normalized.model_dump_json()
        with self._lock:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with self.state_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
                handle.flush()
            self._events.append(normalized)

    def query(
        self,
        *,
        actor_principal_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        action: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[AuditEvent]:
        with self._lock:
            result = list(self._events)

        if actor_principal_id is not None:
            result = [
                item for item in result
                if item.actor_principal_id == actor_principal_id
            ]
        if project_id is not None:
            result = [item for item in result if item.project_id == project_id]
        if run_id is not None:
            result = [item for item in result if item.run_id == run_id]
        if action is not None:
            result = [item for item in result if item.action == action]
        if start_time is not None:
            result = [item for item in result if item.timestamp >= start_time]
        if end_time is not None:
            result = [item for item in result if item.timestamp <= end_time]
        return result

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        for line_number, line in enumerate(
            self.state_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line:
                continue
            try:
                event = AuditEvent.model_validate_json(line)
            except Exception as exc:
                raise ValueError(
                    f"invalid audit record at line {line_number}"
                ) from exc
            self._events.append(event)

    @classmethod
    def _redact_event(cls, event: AuditEvent) -> AuditEvent:
        secrets = tuple(value for value in event.sensitive_values if value)
        message = cls._redact_text(event.message, secrets)
        resource = cls._redact_text(event.resource, secrets)
        attributes: dict[str, str] = {}
        for key, value in event.attributes.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
                attributes[key] = _REDACTED
            else:
                attributes[key] = cls._redact_text(value, secrets)
        return event.model_copy(
            update={
                "message": message,
                "resource": resource,
                "attributes": attributes,
                "sensitive_values": (),
            }
        )

    @staticmethod
    def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(secret, _REDACTED)
        return redacted
