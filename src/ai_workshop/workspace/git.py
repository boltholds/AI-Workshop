from __future__ import annotations

from ai_workshop.models.process import ExecRequest, GitStatus
from ai_workshop.workspace.processes import ProcessService


class GitService:
    def __init__(self, processes: ProcessService):
        self.processes = processes

    def status(self, project_id: str) -> GitStatus:
        result = self.processes.exec(ExecRequest(project_id=project_id, argv=["git", "status", "--porcelain=v1"]))
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git status failed")
        return GitStatus(porcelain=result.stdout)

    def diff(self, project_id: str, staged: bool = False) -> str:
        argv = ["git", "diff"]
        if staged:
            argv.append("--staged")
        result = self.processes.exec(ExecRequest(project_id=project_id, argv=argv))
        if result.exit_code != 0:
            raise RuntimeError(result.stderr.strip() or "git diff failed")
        return result.stdout
