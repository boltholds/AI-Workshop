from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_workshop.config import WorkshopConfig
from ai_workshop.workspace.paths import PathPolicy


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuildSource(StrictModel):
    kind: Literal["build"] = "build"
    project_id: str = Field(min_length=1)
    context: str = "."
    dockerfile: str | None = None

    @field_validator("context", "dockerfile")
    @classmethod
    def paths_must_be_relative(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = PurePosixPath(value)
        if path.is_absolute():
            raise ValueError("service paths must be relative")
        return value


class ImageSource(StrictModel):
    kind: Literal["image"] = "image"
    image: str = Field(min_length=1)


ServiceSource = Annotated[BuildSource | ImageSource, Field(discriminator="kind")]


class PortBinding(StrictModel):
    container: int = Field(ge=1, le=65535)
    host: int | None = Field(default=None, ge=1, le=65535)
    host_ip: Literal["127.0.0.1"] = "127.0.0.1"


class PersistentVolume(StrictModel):
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_.-]+$")
    target: str = Field(min_length=1)

    @field_validator("target")
    @classmethod
    def target_must_be_absolute(cls, value: str) -> str:
        if not PurePosixPath(value).is_absolute():
            raise ValueError("volume target must be absolute")
        return value


class Healthcheck(StrictModel):
    command: list[str] = Field(min_length=1)
    interval: str = "10s"
    timeout: str = "3s"
    retries: int = Field(default=5, ge=1)


class ServiceDefinition(StrictModel):
    source: ServiceSource
    command: list[str] | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    env_files: list[str] = Field(default_factory=list)
    ports: list[PortBinding] = Field(default_factory=list)
    volumes: list[PersistentVolume] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    healthcheck: Healthcheck | None = None

    @field_validator("env_files")
    @classmethod
    def env_files_must_be_private_workshop_paths(cls, values: list[str]) -> list[str]:
        for value in values:
            path = PurePosixPath(value)
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(path.parts) < 3
                or path.parts[:2] != (".workshop", "secrets")
            ):
                raise ValueError("env files must live under .workshop/secrets/")
        return values


class ServiceProfile(StrictModel):
    services: list[str] = Field(default_factory=list)


class ServiceConfig(StrictModel):
    services: dict[str, ServiceDefinition] = Field(default_factory=dict)
    profiles: dict[str, ServiceProfile] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ServiceConfig":
        if not path.exists():
            raise FileNotFoundError(f"Workshop service config not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(raw)

    def validate(self, projects: WorkshopConfig) -> None:
        project_ids = {project.project_id for project in projects.projects}
        policy = PathPolicy(projects, host_paths=True)
        host_ports: dict[int, str] = {}

        for service_id, service in self.services.items():
            if isinstance(service.source, BuildSource):
                if service.source.project_id not in project_ids:
                    raise ValueError(
                        f"service {service_id} build source must reference a registered project"
                    )
                context = policy.resolve(service.source.project_id, service.source.context)
                if not context.exists() or not context.is_dir():
                    raise ValueError(f"service {service_id} build context does not exist")
                if service.source.dockerfile is not None:
                    dockerfile = PurePosixPath(service.source.dockerfile)
                    if ".." in dockerfile.parts:
                        raise ValueError("dockerfile path resolves outside build context")

            unknown_dependencies = sorted(set(service.depends_on) - set(self.services))
            if unknown_dependencies:
                raise ValueError(
                    f"service {service_id} depends on unknown service: {unknown_dependencies[0]}"
                )

            volume_names: set[str] = set()
            for volume in service.volumes:
                if volume.name in volume_names:
                    raise ValueError(f"duplicate volume {volume.name} in service {service_id}")
                volume_names.add(volume.name)

            for port in service.ports:
                if port.host is None:
                    continue
                owner = host_ports.get(port.host)
                if owner is not None:
                    raise ValueError(
                        f"host port {port.host} is used by both {owner} and {service_id}"
                    )
                host_ports[port.host] = service_id

        for profile_id, profile in self.profiles.items():
            for service_id in profile.services:
                if service_id not in self.services:
                    raise ValueError(
                        f"profile {profile_id} references unknown service: {service_id}"
                    )
