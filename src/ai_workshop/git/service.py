from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import ContextManager

from ai_workshop.credentials.git_env import GitCredentialContext
from ai_workshop.credentials.protocol import CredentialProvider
from ai_workshop.git.models import GitCommitResult, GitLogEntry, GitStatus
from ai_workshop.projects.models import GitManagedProject, ProjectRecord
from ai_workshop.projects.protocol import ProjectService


_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}+-]*$")
_REMOTE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_CONTROL_ENV = {
    "AI_WORKSHOP_WORKSPACE_TOKEN",
    "AI_WORKSHOP_BROWSER_TOKEN",
    "AI_WORKSHOP_MCP_TOKEN",
}


@dataclass(slots=True)
class GitRepositoryError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class GitRepositoryService:
    def __init__(
        self,
        projects: ProjectService,
        credentials: CredentialProvider,
        *,
        timeout_seconds: float = 60.0,
    ):
        self.projects = projects
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds

    def clone(
        self,
        project_id: str,
        remote_url: str,
        *,
        credential_id: str | None = None,
    ) -> GitManagedProject:
        self._validate_remote_url(remote_url)
        project = self.projects.register_git(project_id, remote_url=remote_url)
        context_manager = self._credential_context(credential_id)
        try:
            with context_manager as context:
                self._run(
                    None,
                    ["clone", "--", remote_url, str(project.path)],
                    context=context,
                )
        except Exception:
            self.projects.delete_checkout(project_id)
            raise
        return project

    def status(self, project_id: str) -> GitStatus:
        project = self._project(project_id)
        branch_result = self._run(
            project.path,
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            check=False,
        )
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
        else:
            commit = self._run(project.path, ["rev-parse", "--short", "HEAD"])
            branch = f"(detached:{commit.stdout.strip()})"
        porcelain = self._run(
            project.path,
            ["status", "--porcelain=v1"],
        ).stdout.rstrip("\n")
        return GitStatus(
            project_id=project_id,
            branch=branch,
            porcelain=porcelain,
        )

    def diff(self, project_id: str, *, staged: bool = False) -> str:
        project = self._project(project_id)
        argv = ["diff"]
        if staged:
            argv.append("--cached")
        return self._run(project.path, argv).stdout

    def fetch(
        self,
        project_id: str,
        *,
        remote: str = "origin",
        credential_id: str | None = None,
    ) -> None:
        project = self._project(project_id)
        remote = self._remote_name(remote)
        with self._credential_context(credential_id) as context:
            self._run(project.path, ["fetch", remote], context=context)

    def pull(
        self,
        project_id: str,
        *,
        remote: str = "origin",
        branch: str,
        credential_id: str | None = None,
    ) -> None:
        project = self._project(project_id)
        remote = self._remote_name(remote)
        branch = self._ref(branch)
        with self._credential_context(credential_id) as context:
            self._run(
                project.path,
                ["pull", "--ff-only", remote, branch],
                context=context,
            )

    def add(self, project_id: str, paths: list[str]) -> None:
        if not paths:
            raise ValueError("at least one Git path is required")
        project = self._project(project_id)
        safe_paths = [self._relative_path(path) for path in paths]
        self._run(project.path, ["add", "--", *safe_paths])

    def commit(self, project_id: str, message: str) -> GitCommitResult:
        if not message or "\x00" in message:
            raise ValueError("commit message must not be empty or contain NUL")
        project = self._project(project_id)
        self._run(project.path, ["commit", "-m", message])
        commit_id = self._run(project.path, ["rev-parse", "HEAD"]).stdout.strip()
        return GitCommitResult(project_id=project_id, commit_id=commit_id)

    def log(self, project_id: str, *, limit: int = 20) -> list[GitLogEntry]:
        if limit < 1 or limit > 200:
            raise ValueError("log limit must be between 1 and 200")
        project = self._project(project_id)
        output = self._run(
            project.path,
            ["log", "-n", str(limit), "--format=%H%x00%s"],
        ).stdout
        entries: list[GitLogEntry] = []
        for line in output.splitlines():
            if not line:
                continue
            commit_id, separator, subject = line.partition("\x00")
            if not separator:
                raise GitRepositoryError("GIT_OUTPUT_INVALID", "Git log output was invalid")
            entries.append(GitLogEntry(commit_id=commit_id, subject=subject))
        return entries

    def branch_list(self, project_id: str) -> list[str]:
        project = self._project(project_id)
        output = self._run(
            project.path,
            ["for-each-ref", "--format=%(refname:short)", "refs/heads/"],
        ).stdout
        return sorted(line for line in output.splitlines() if line)

    def branch_create(self, project_id: str, branch: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["branch", self._ref(branch)])

    def switch(self, project_id: str, branch: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["switch", self._ref(branch)])

    def checkout(self, project_id: str, ref: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["checkout", "--detach", self._ref(ref)])

    def remote_list(self, project_id: str) -> dict[str, str]:
        project = self._project(project_id)
        names = self._run(project.path, ["remote"]).stdout.splitlines()
        result: dict[str, str] = {}
        for name in names:
            if not name:
                continue
            safe_name = self._remote_name(name)
            result[safe_name] = self._run(
                project.path,
                ["remote", "get-url", safe_name],
            ).stdout.strip()
        return result

    def remote_set(self, project_id: str, name: str, url: str) -> None:
        project = self._project(project_id)
        name = self._remote_name(name)
        self._validate_remote_url(url)
        self._run(project.path, ["remote", "set-url", name, url])

    def stash(self, project_id: str, *, message: str = "AI Workshop stash") -> None:
        if "\x00" in message:
            raise ValueError("stash message contains NUL")
        project = self._project(project_id)
        self._run(project.path, ["stash", "push", "-m", message])

    def tag(self, project_id: str, tag: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["tag", self._ref(tag)])

    def push(
        self,
        project_id: str,
        *,
        remote: str = "origin",
        branch: str,
        credential_id: str | None = None,
    ) -> None:
        project = self._project(project_id)
        remote = self._remote_name(remote)
        branch = self._ref(branch)
        with self._credential_context(credential_id) as context:
            self._run(
                project.path,
                ["push", remote, branch],
                context=context,
            )

    def merge(self, project_id: str, ref: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["merge", "--no-edit", self._ref(ref)])

    def rebase(self, project_id: str, ref: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["rebase", self._ref(ref)])

    def rebase_continue(self, project_id: str) -> None:
        project = self._project(project_id)
        self._run(
            project.path,
            ["-c", "core.editor=true", "rebase", "--continue"],
        )

    def rebase_abort(self, project_id: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["rebase", "--abort"])

    def cherry_pick(self, project_id: str, ref: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["cherry-pick", self._ref(ref)])

    def _hard_reset_confirmed(self, project_id: str, ref: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["reset", "--hard", self._ref(ref)])

    def _delete_branch_confirmed(self, project_id: str, branch: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["branch", "-D", self._ref(branch)])

    def _delete_tag_confirmed(self, project_id: str, tag: str) -> None:
        project = self._project(project_id)
        self._run(project.path, ["tag", "-d", self._ref(tag)])

    def _force_push_confirmed(
        self,
        project_id: str,
        *,
        remote: str,
        branch: str,
        credential_id: str | None = None,
    ) -> None:
        project = self._project(project_id)
        remote = self._remote_name(remote)
        branch = self._ref(branch)
        with self._credential_context(credential_id) as context:
            self._run(
                project.path,
                ["push", "--force-with-lease", remote, branch],
                context=context,
            )

    def _project(self, project_id: str) -> ProjectRecord:
        project = self.projects.get(project_id)
        if not project.path.is_dir():
            raise GitRepositoryError(
                "GIT_PROJECT_UNAVAILABLE",
                "Project checkout is unavailable",
            )
        return project

    def _credential_context(
        self,
        credential_id: str | None,
    ) -> ContextManager[GitCredentialContext | None]:
        if credential_id is None:
            return nullcontext(None)
        return self.credentials.git_context(credential_id)

    def _run(
        self,
        cwd: Path | None,
        args: list[str],
        *,
        context: GitCredentialContext | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in _CONTROL_ENV:
            env.pop(key, None)
        if context is not None:
            env.update(context.environment())
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitRepositoryError("GIT_TIMEOUT", "Git operation timed out") from exc

        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "Git operation failed"
            if context is not None:
                detail = context.redact(detail)
            raise GitRepositoryError("GIT_COMMAND_FAILED", detail)
        return result

    @staticmethod
    def _remote_name(value: str) -> str:
        if _REMOTE_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid Git remote name")
        return value

    @staticmethod
    def _ref(value: str) -> str:
        if _REF_PATTERN.fullmatch(value) is None or value.startswith("-"):
            raise ValueError("invalid Git ref")
        return value

    @staticmethod
    def _relative_path(value: str) -> str:
        if not value or "\\" in value:
            raise ValueError("Git path must be a relative POSIX path")
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("Git path must be relative and cannot escape project")
        return parsed.as_posix()

    @staticmethod
    def _validate_remote_url(value: str) -> None:
        if (
            not value
            or value.startswith("-")
            or "\x00" in value
            or "\n" in value
            or "\r" in value
        ):
            raise ValueError("invalid Git remote URL")
