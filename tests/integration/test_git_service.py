from pathlib import Path
import subprocess

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.git import GitService
from ai_workshop.workspace.paths import PathPolicy
from ai_workshop.workspace.processes import ProcessService


def test_git_status_and_diff_do_not_mutate_repo(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")

    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=tmp_path, container="/workspace/p", mode="rw")])
    svc = GitService(ProcessService(PathPolicy(cfg, host_paths=True)))
    status = svc.status("p")
    diff = svc.diff("p", staged=False)

    assert "a.txt" in status.porcelain
    assert "-one" in diff and "+two" in diff
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "two\n"
