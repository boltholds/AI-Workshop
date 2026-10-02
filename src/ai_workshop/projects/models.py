from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


_PROJECT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class ProjectKind(StrEnum):
    GIT_MANAGED = "git-managed"
    EXTERNAL = "external"


class _ProjectBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ProjectKind
    project_id: str = Field(min_length=1, pattern=_PROJECT_ID_PATTERN)
    path: Path

    @field_validator("path")
    @classmethod
    def path_must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("project path must be absolute")
        return value


class GitManagedProject(_ProjectBase):
    kind: ProjectKind = ProjectKind.GIT_MANAGED
    remote_url: str = Field(min_length=1)

    @field_validator("remote_url")
    @classmethod
    def remote_url_must_be_single_value(cls, value: str) -> str:
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("remote URL contains invalid control characters")
        return value


class ExternalProject(_ProjectBase):
    kind: ProjectKind = ProjectKind.EXTERNAL


ProjectRecord = GitManagedProject | ExternalProject
