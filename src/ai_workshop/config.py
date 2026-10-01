from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from yaml.resolver import BaseResolver
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class ProjectMount(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    host: Path
    container: PurePosixPath
    mode: Literal["ro", "rw"] = "rw"

    @field_validator("container")
    @classmethod
    def container_must_be_absolute(cls, value: PurePosixPath) -> PurePosixPath:
        if not value.is_absolute():
            raise ValueError("container path must be absolute")
        return value


class WorkshopConfig(BaseModel):
    projects: list[ProjectMount] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "WorkshopConfig":
        if not path.exists():
            raise FileNotFoundError(f"Workshop project config not found: {path}")
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader) or {}
        projects_raw = raw.get("projects") or {}
        if not isinstance(projects_raw, dict):
            raise ValueError("projects must be a mapping")
        projects = [
            ProjectMount(project_id=project_id, **(settings or {}))
            for project_id, settings in projects_raw.items()
        ]
        return cls(projects=projects)
