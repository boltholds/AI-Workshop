from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess

from ai_workshop.projects.models import GitManagedProject
from ai_workshop.projects.protocol import ProjectService
from ai_workshop.server.storage import ServerStorage


_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}+-]*$")


@dataclass(frozen=True, slots=True)
class RunWorkspace:
    run_id: str
    project_id: str
    path: Path
    base_ref: str
    commit_id: str
    writable: bool


class RunWorkspaceManager:
    def __init__(
        self,
        projects: ProjectService,
        storage: ServerStorage,
        *,
        timeout_seconds: float = 60.0,
    ):
        self.projects = projects
        self.storage = storage
        self.timeout_seconds = timeout_seconds

    def create(
        self,
        project_id: str,
        run_id: str,
        base_ref: str,
        writable: bool,
    ) -> RunWorkspace:
        if _REF_PATTERN.fullmatch(base_ref) is None or base_ref.startswith("-"):
            raise ValueError("invalid base ref")

        project = self.projects.get(project_id)
        if not isinstance(project, GitManagedProject):
            raise ValueError("AgentRun worktrees require a Git-managed project")
        if not project.path.is_dir():
            raise ValueError("canonical project checkout is unavailable")

        run_root = self.storage.run_root(run_id)
        workspace_path = run_root / "workspace"
        marker_path = run_root / "workspace.json"
        if workspace_path.exists() or marker_path.exists():
            raise ValueError(f"run workspace already exists: {run_id}")

        commit_id = self._git(
            project.path,
            "rev-parse",
            "--verify",
            f"{base_ref}^{{commit}}",
        ).strip()
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_id) is None:
            raise RuntimeError("Git returned an invalid commit id")

        try:
            self._git(
                project.path,
                "worktree",
                "add",
                "--detach",
                str(workspace_path),
                commit_id,
            )
            workspace = RunWorkspace(
                run_id=run_id,
                project_id=project_id,
                path=workspace_path,
                base_ref=base_ref,
                commit_id=commit_id,
                writable=writable,
            )
            marker_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "run_id": run_id,
                        "project_id": project_id,
                        "path": str(workspace_path),
                        "base_ref": base_ref,
                        "commit_id": commit_id,
                        "writable": writable,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return workspace
        except Exception:
            if workspace_path.exists():
                self._git(
                    project.path,
                    "worktree",
                    "remove",
                    "--force",
                    str(workspace_path),
                    check=False,
                )
                shutil.rmtree(workspace_path, ignore_errors=True)
            marker_path.unlink(missing_ok=True)
            raise

    def get(self, run_id: str) -> RunWorkspace:
        run_root = self.storage.run_root(run_id)
        marker_path = run_root / "workspace.json"
        if not marker_path.is_file():
            raise KeyError(f"unknown run workspace: {run_id}")
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1 or payload.get("run_id") != run_id:
            raise ValueError("invalid run workspace marker")
        workspace = RunWorkspace(
            run_id=run_id,
            project_id=str(payload["project_id"]),
            path=Path(payload["path"]),
            base_ref=str(payload["base_ref"]),
            commit_id=str(payload["commit_id"]),
            writable=bool(payload["writable"]),
        )
        expected = run_root / "workspace"
        if workspace.path.resolve(strict=False) != expected.resolve(strict=False):
            raise ValueError("run workspace marker path escapes run storage")
        return workspace

    def remove(self, run_id: str) -> None:
        try:
            workspace = self.get(run_id)
        except KeyError:
            return

        project = self.projects.get(workspace.project_id)
        if not isinstance(project, GitManagedProject):
            raise ValueError("run workspace project is no longer Git-managed")

        self._git(
            project.path,
            "worktree",
            "remove",
            "--force",
            str(workspace.path),
            check=False,
        )
        shutil.rmtree(workspace.path, ignore_errors=True)
        (self.storage.run_root(run_id) / "workspace.json").unlink(missing_ok=True)
        self._git(project.path, "worktree", "prune", check=False)

    def _git(
        self,
        cwd: Path,
        *args: str,
        check: bool = True,
    ) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env={
                    "PATH": __import__("os").environ.get("PATH", ""),
                    "HOME": __import__("os").devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": __import__("os").devnull,
                    "GIT_TERMINAL_PROMPT": "0",
                },
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Git worktree operation timed out") from exc
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "Git worktree operation failed"
            raise RuntimeError(detail)
        return result.stdout
