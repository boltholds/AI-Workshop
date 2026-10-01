from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExecRequest(BaseModel):
    project_id: str
    argv: list[str] = Field(min_length=1)
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 60.0
    run_id: UUID = Field(default_factory=uuid4)


class ExecResult(BaseModel):
    run_id: UUID
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


class GitStatus(BaseModel):
    porcelain: str
