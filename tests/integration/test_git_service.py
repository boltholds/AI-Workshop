import subprocess
from pathlib import Path

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.git import GitService
from ai_workshop.workspace.paths import PathPolicy
from ai_workshop.workspace.processes import ProcessService


def run(cwd: Path, *args: str) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def test_git_status_and_diff_are_read_only(tmp_path: Path) -> None:
    root = tmp_path / "repo"; root.mkdir()
    run(root, "git", "init", "-q")
    run(root, "git", "config", "user.email", "test@example.com")
    run(root, "git", "config", "user.name", "Test")
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    run(root, "git", "add", "a.txt")
    run(root, "git", "commit", "-qm", "initial")
    (root / "a.txt").write_text("one\ntwo\n", encoding="utf-8")

    cfg = WorkshopConfig(projects={"repo": ProjectMount(project_id="repo", host=root, container=root.as_posix(), mode="rw")})
    svc = GitService(ProcessService(PathPolicy(cfg)))
    status = svc.status("repo")
    assert "a.txt" in status.porcelain
    diff = svc.diff("repo", staged=False)
    assert "+two" in diff
    assert (root / "a.txt").read_text(encoding="utf-8") == "one\ntwo\n"
