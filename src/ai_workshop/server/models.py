from __future__ import annotations

from enum import StrEnum
from ipaddress import IPv4Address

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
    host: IPv4Address
    host_port: int = Field(ge=1, le=65535)
    container_port: int = Field(ge=1, le=65535)
