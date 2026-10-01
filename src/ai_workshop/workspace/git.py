from __future__ import annotations

import asyncio
from pydantic import BaseModel

from ai_workshop.models.process import ExecRequest
from ai_workshop.workspace.processes import ProcessService


class GitStatus(BaseModel):
    branch: str | None
    porcelain: str


class GitService:
    def __init__(self, processes: ProcessService) -> None:
        self._processes = processes

    def _exec(self, project_id: str, *argv: str):
        result = asyncio.run(self._processes.exec(ExecRequest(
            project_id=project_id,
            argv=["git", *argv],
            timeout_seconds=30,
        )))
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or f"git {' '.join(argv)} failed")
        return result

    def status(self, project_id: str) -> GitStatus:
        result = self._exec(project_id, "status", "--short", "--branch")
        lines = result.stdout.splitlines()
        branch = None
        if lines and lines[0].startswith("## "):
            branch = lines[0][3:].split("...", 1)[0].strip()
        porcelain = "\n".join(line for line in lines if not line.startswith("## "))
        return GitStatus(branch=branch, porcelain=porcelain)

    def diff(self, project_id: str, staged: bool = False) -> str:
        args = ["diff"]
        if staged:
            args.append("--cached")
        return self._exec(project_id, *args).stdout
