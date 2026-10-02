from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ServerModeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    storage_root: Path
    private_endpoint_host: str = Field(
        default="rootless-runtime",
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*$",
    )
    private_endpoint_start_port: int = Field(default=41000, ge=1024, le=65535)
    private_endpoint_end_port: int = Field(default=41999, ge=1024, le=65535)

    @field_validator("storage_root")
    @classmethod
    def storage_root_must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("storage_root must be absolute")
        return value

    @model_validator(mode="after")
    def endpoint_range_must_be_ordered(self) -> "ServerModeConfig":
        if self.private_endpoint_end_port < self.private_endpoint_start_port:
            raise ValueError("private endpoint port range is invalid")
        return self

    @classmethod
    def load(cls, path: Path) -> "ServerModeConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Server Mode config not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("server config must be a mapping")
        return cls.model_validate(raw)
