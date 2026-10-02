from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeEnvironmentVariable(StrictFrozenModel):
    name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str

    @field_validator("value")
    @classmethod
    def value_must_not_contain_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("environment value cannot contain NUL")
        return value


class RuntimeWorkloadKind(StrEnum):
    AGENT_RUN = "agent-run"
    MCP = "mcp"
    PROJECT_SERVICE = "project-service"
    INFRASTRUCTURE = "infrastructure"


class RuntimeOutboundAccess(StrEnum):
    NONE = "none"
    INTERNET = "internet"


class RuntimePidNamespace(StrEnum):
    ISOLATED = "isolated"
    HOST = "host"


class RuntimeNetworkNamespace(StrEnum):
    ISOLATED = "isolated"
    HOST = "host"


class RuntimeMount(StrictFrozenModel):
    source: Path
    target: PurePosixPath
    read_only: bool = False

    @field_validator("source")
    @classmethod
    def source_must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("runtime mount source must be absolute")
        return value

    @field_validator("target")
    @classmethod
    def target_must_be_absolute(cls, value: PurePosixPath) -> PurePosixPath:
        if not value.is_absolute():
            raise ValueError("runtime mount target must be absolute")
        return value


class RuntimeDeviceMapping(StrictFrozenModel):
    source: Path
    target: PurePosixPath

    @field_validator("source")
    @classmethod
    def device_source_must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("device source must be absolute")
        return value

    @field_validator("target")
    @classmethod
    def device_target_must_be_absolute(cls, value: PurePosixPath) -> PurePosixPath:
        if not value.is_absolute():
            raise ValueError("device target must be absolute")
        return value


RuntimePort = Annotated[int, Field(ge=1, le=65535)]


class RuntimeWorkloadState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    EXITED = "exited"
    UNKNOWN = "unknown"


class RuntimeWorkloadSpec(StrictFrozenModel):
    workload_id: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    image: str = Field(min_length=1)
    command: tuple[str, ...] = ()
    environment: tuple[RuntimeEnvironmentVariable, ...] = ()
    kind: RuntimeWorkloadKind = RuntimeWorkloadKind.AGENT_RUN
    outbound: RuntimeOutboundAccess = RuntimeOutboundAccess.NONE
    mounts: tuple[RuntimeMount, ...] = ()
    privileged: bool = False
    pid_namespace: RuntimePidNamespace = RuntimePidNamespace.ISOLATED
    network_namespace: RuntimeNetworkNamespace = RuntimeNetworkNamespace.ISOLATED
    devices: tuple[RuntimeDeviceMapping, ...] = ()
    container_ports: tuple[RuntimePort, ...] = ()

    @field_validator("image")
    @classmethod
    def image_must_not_be_cli_fragment(cls, value: str) -> str:
        if value.startswith("-") or any(char.isspace() for char in value):
            raise ValueError("image must be a container image reference")
        return value


class RuntimeWorkloadStatus(StrictFrozenModel):
    workload_id: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    state: RuntimeWorkloadState


class RuntimeEndpoint(StrictFrozenModel):
    workload_id: str = Field(min_length=1, pattern=_IDENTIFIER_PATTERN)
    host: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*$",
    )
    host_port: int = Field(ge=1, le=65535)
    container_port: int = Field(ge=1, le=65535)
