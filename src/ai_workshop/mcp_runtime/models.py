from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
_PERMISSION = r"^[A-Za-z][A-Za-z0-9_.:-]*$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class McpRegistrationScope(StrEnum):
    RUN = "run"
    PROJECT = "project"
    USER = "user"
    GLOBAL = "global"


class McpTransportKind(StrEnum):
    STDIO = "stdio"
    HTTP = "http"
    CONTAINER = "container"


class McpServerState(StrEnum):
    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class McpRegistration(_FrozenModel):
    server_id: str = Field(min_length=1, pattern=_ID)
    display_name: str = Field(min_length=1, max_length=200)
    transport: McpTransportKind
    scope: McpRegistrationScope
    scope_id: str = Field(min_length=1, max_length=200)
    owner_principal_id: str = Field(min_length=1, pattern=_ID)
    permissions: frozenset[str] = frozenset()
    state: McpServerState = McpServerState.REGISTERED

    @field_validator("permissions")
    @classmethod
    def permissions_are_valid(cls, values: frozenset[str]) -> frozenset[str]:
        import re
        for value in values:
            if re.fullmatch(_PERMISSION, value) is None:
                raise ValueError("invalid MCP permission")
        return values

    @field_validator("scope_id")
    @classmethod
    def scope_id_matches_scope(cls, value: str, info):
        scope = info.data.get("scope")
        if scope is McpRegistrationScope.GLOBAL and value != "global":
            raise ValueError("global MCP registration scope_id must be global")
        return value


class McpToolDescriptor(_FrozenModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    required_permissions: frozenset[str] = frozenset()


class McpResourceDescriptor(_FrozenModel):
    uri: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class McpPromptDescriptor(_FrozenModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class McpDiscoveredCapabilities(_FrozenModel):
    server_id: str = Field(min_length=1, pattern=_ID)
    revision: int = Field(default=0, ge=0)
    tools: tuple[McpToolDescriptor, ...] = ()
    resources: tuple[McpResourceDescriptor, ...] = ()
    prompts: tuple[McpPromptDescriptor, ...] = ()


class McpServerRecord(_FrozenModel):
    registration: McpRegistration
    capabilities: McpDiscoveredCapabilities
