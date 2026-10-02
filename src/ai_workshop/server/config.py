from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator


class ServerModeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    storage_root: Path

    @field_validator("storage_root")
    @classmethod
    def storage_root_must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("storage_root must be absolute")
        return value

    @classmethod
    def load(cls, path: Path) -> "ServerModeConfig":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Server Mode config not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("server config must be a mapping")
        return cls.model_validate(raw)
