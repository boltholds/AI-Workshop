from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _GitModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GitStatus(_GitModel):
    project_id: str
    branch: str
    porcelain: str


class GitCommitResult(_GitModel):
    project_id: str
    commit_id: str = Field(min_length=7)


class GitLogEntry(_GitModel):
    commit_id: str = Field(min_length=7)
    subject: str
