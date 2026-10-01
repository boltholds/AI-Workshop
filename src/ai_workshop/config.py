from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


class ProjectMount(BaseModel):
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
    projects: dict[str, ProjectMount] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "WorkshopConfig":
        if not path.exists():
            raise ValueError(f"configuration file does not exist: {path}")
        try:
            raw = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader) or {}
        except (yaml.YAMLError, ValueError) as exc:
            raise ValueError(f"invalid project configuration: {exc}") from exc
        projects_raw = raw.get("projects", {})
        if not isinstance(projects_raw, dict):
            raise ValueError("projects must be a mapping")
        projects: dict[str, ProjectMount] = {}
        for project_id, value in projects_raw.items():
            if not isinstance(value, dict):
                raise ValueError(f"project {project_id!r} must be a mapping")
            projects[project_id] = ProjectMount(project_id=project_id, **value)
        return cls(projects=projects)
