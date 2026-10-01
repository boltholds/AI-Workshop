from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ExecRequest(BaseModel):
    project_id: str
    argv: list[str] | None = None
    shell: str | None = None
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=120.0, gt=0, le=3600)

    @model_validator(mode="after")
    def exactly_one_command_form(self) -> Self:
        if (self.argv is None) == (self.shell is None):
            raise ValueError("exactly one of argv or shell is required")
        if self.argv is not None and not self.argv:
            raise ValueError("argv must not be empty")
        return self


class ExecResult(BaseModel):
    run_id: UUID
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False
