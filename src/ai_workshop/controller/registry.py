from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


@dataclass(frozen=True, slots=True)
class RegisteredService:
    service_id: str
    compose_project: str
    working_dir: Path
    compose_files: tuple[Path, ...]
    compose_service: str
    allowed_operations: frozenset[str]

    def __post_init__(self) -> None:
        name_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
        if not name_pattern.fullmatch(self.service_id):
            raise ValueError("service_id must be a safe identifier")
        if not name_pattern.fullmatch(self.compose_project):
            raise ValueError("compose_project must be a safe identifier")
        if not name_pattern.fullmatch(self.compose_service):
            raise ValueError("compose_service must be a safe identifier")
        object.__setattr__(self, "working_dir", self.working_dir.resolve())
        object.__setattr__(
            self,
            "compose_files",
            tuple(path.resolve() for path in self.compose_files),
        )


class ServiceRegistry:
    def __init__(
        self,
        services: list[RegisteredService] | tuple[RegisteredService, ...],
        *,
        profiles: dict[str, frozenset[str]] | None = None,
    ):
        mapped: dict[str, RegisteredService] = {}
        for service in services:
            if service.service_id in mapped:
                raise ValueError(f"duplicate service: {service.service_id}")
            mapped[service.service_id] = service
        self._services = mapped

        normalized_profiles: dict[str, frozenset[str]] = {}
        for profile_id, service_ids in (profiles or {}).items():
            missing = sorted(set(service_ids) - set(mapped))
            if missing:
                raise ValueError(
                    f"profile {profile_id} references unknown service: {missing[0]}"
                )
            normalized_profiles[profile_id] = frozenset(service_ids)
        self._profiles = normalized_profiles

    @classmethod
    def load(cls, path: Path) -> "ServiceRegistry":
        if not path.exists():
            raise FileNotFoundError(f"service registry not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        services_raw = raw.get("services") or {}
        if not isinstance(services_raw, dict):
            raise ValueError("registry services must be a mapping")
        services: list[RegisteredService] = []
        for service_id, data in services_raw.items():
            if not isinstance(data, dict):
                raise ValueError(f"invalid registry entry: {service_id}")
            working_dir = Path(data["working_dir"]).resolve()
            compose_files = tuple(Path(value).resolve() for value in data.get("compose_files", []))
            if not compose_files:
                raise ValueError(f"service {service_id} has no compose files")
            for compose_file in compose_files:
                try:
                    compose_file.relative_to(working_dir)
                except ValueError as exc:
                    raise ValueError(
                        f"service {service_id} compose file is outside working_dir"
                    ) from exc
            services.append(
                RegisteredService(
                    service_id=service_id,
                    compose_project=str(data["compose_project"]),
                    working_dir=working_dir,
                    compose_files=compose_files,
                    compose_service=str(data["compose_service"]),
                    allowed_operations=frozenset(data.get("allowed_operations", [])),
                )
            )
        profiles_raw = raw.get("profiles") or {}
        if not isinstance(profiles_raw, dict):
            raise ValueError("registry profiles must be a mapping")
        profiles = {
            str(profile_id): frozenset(str(service_id) for service_id in (service_ids or []))
            for profile_id, service_ids in profiles_raw.items()
        }
        return cls(services, profiles=profiles)

    def list_ids(self, profile_id: str | None = None) -> list[str]:
        if profile_id is None:
            return sorted(self._services)
        service_ids = self._profiles.get(profile_id)
        if service_ids is None:
            raise KeyError(f"unknown service profile: {profile_id}")
        return sorted(service_ids)

    def require(self, service_id: str) -> RegisteredService:
        service = self._services.get(service_id)
        if service is None:
            raise KeyError(f"unregistered service: {service_id}")
        return service
