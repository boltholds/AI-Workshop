from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ai_workshop.config import WorkshopConfig
from ai_workshop.recovery.adapters.postgres import (
    PostgresAdapter,
    PostgresTarget,
)
from ai_workshop.recovery.reset import ResetService
from ai_workshop.recovery.state import (
    StateAdapterRegistry,
    StateSnapshotService,
)
from ai_workshop.recovery.store import SnapshotStore


class PostgresTargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password_env: str | None = None


class PostgresAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["postgres"] = "postgres"
    targets: dict[str, PostgresTargetConfig] = Field(default_factory=dict)


StateAdapterConfig = Annotated[
    PostgresAdapterConfig,
    Field(discriminator="kind"),
]


class ResetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_paths: list[Path] = Field(default_factory=list)
    browser_artifact_paths: list[Path] = Field(default_factory=list)


class RecoveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_adapters: dict[str, StateAdapterConfig] = Field(default_factory=dict)
    reset: ResetConfig | None = None
    _base_dir: Path = PrivateAttr(default=Path("."))

    @classmethod
    def load(cls, path: Path) -> "RecoveryConfig":
        path = Path(path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"recovery config not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        config = cls.model_validate(raw)
        config._base_dir = path.parent
        return config

    def resolve_local_path(self, value: Path) -> Path:
        if value.is_absolute():
            return value.resolve()
        return (self._base_dir / value).resolve()


@dataclass(slots=True)
class RecoveryRuntime:
    state_service: StateSnapshotService | None
    reset_service: ResetService | None


def build_recovery_runtime(
    config: RecoveryConfig,
    *,
    state_root: Path,
    projects: WorkshopConfig,
) -> RecoveryRuntime:
    adapters: dict[str, object] = {}

    for adapter_id, adapter_config in config.state_adapters.items():
        if isinstance(adapter_config, PostgresAdapterConfig):
            targets: dict[str, PostgresTarget] = {}
            for target_id, target_config in adapter_config.targets.items():
                password = None
                if target_config.password_env is not None:
                    if target_config.password_env not in os.environ:
                        raise ValueError(
                            f"missing recovery secret environment variable: "
                            f"{target_config.password_env}"
                        )
                    password = os.environ[target_config.password_env]
                targets[target_id] = PostgresTarget(
                    host=target_config.host,
                    port=target_config.port,
                    database=target_config.database,
                    user=target_config.user,
                    password=password,
                )
            adapters[adapter_id] = PostgresAdapter(targets)

    state_service = None
    if adapters:
        state_service = StateSnapshotService(
            StateAdapterRegistry(adapters),
            SnapshotStore(Path(state_root) / "state"),
        )

    reset_service = None
    if config.reset is not None:
        reset_service = ResetService(
            cache_paths=[
                config.resolve_local_path(path)
                for path in config.reset.cache_paths
            ],
            browser_artifact_paths=[
                config.resolve_local_path(path)
                for path in config.reset.browser_artifact_paths
            ],
            state_resetters={},
            infrastructure_resetter=None,
            project_roots=[project.host for project in projects.projects],
        )

    return RecoveryRuntime(
        state_service=state_service,
        reset_service=reset_service,
    )
