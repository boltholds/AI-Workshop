from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RegisteredService:
    service_id: str
    compose_project: str
    working_dir: Path
    compose_files: tuple[Path, ...]
    compose_service: str
    allowed_operations: frozenset[str]

    def __post_init__(self) -> None:
        if not self.service_id:
            raise ValueError("service_id must not be empty")
        if not self.compose_project:
            raise ValueError("compose_project must not be empty")
        if not self.compose_service:
            raise ValueError("compose_service must not be empty")
        object.__setattr__(self, "working_dir", self.working_dir.resolve())
        object.__setattr__(
            self,
            "compose_files",
            tuple(path.resolve() for path in self.compose_files),
        )


class ServiceRegistry:
    def __init__(self, services: list[RegisteredService] | tuple[RegisteredService, ...]):
        mapped: dict[str, RegisteredService] = {}
        for service in services:
            if service.service_id in mapped:
                raise ValueError(f"duplicate service: {service.service_id}")
            mapped[service.service_id] = service
        self._services = mapped

    def list_ids(self) -> list[str]:
        return sorted(self._services)

    def require(self, service_id: str) -> RegisteredService:
        service = self._services.get(service_id)
        if service is None:
            raise KeyError(f"unregistered service: {service_id}")
        return service
