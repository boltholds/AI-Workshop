from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ai_workshop.credentials.store import CredentialStore
from ai_workshop.git.service import GitRepositoryError, GitRepositoryService
from ai_workshop.projects.store import ProjectStore
from ai_workshop.server.storage import ServerStorage


def run_git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_remote(tmp_path: Path) -> tuple[Path, str]:
    seed = tmp_path / "seed"
    seed.mkdir()
    run_git(seed, "init")
    run_git(seed, "config", "user.email", "test@example.com")
    run_git(seed, "config", "user.name", "Test User")
    run_git(seed, "checkout", "-b", "main")
    (seed / "README.md").write_text("v1\n", encoding="utf-8")
    run_git(seed, "add", "README.md")
    run_git(seed, "commit", "-m", "initial")

    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    run_git(seed, "remote", "add", "origin", str(remote))
    run_git(seed, "push", "-u", "origin", "main")
    subprocess.run(
        ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
        capture_output=True,
    )
    return remote, run_git(seed, "rev-parse", "HEAD")


def service(tmp_path: Path) -> tuple[GitRepositoryService, ProjectStore]:
    storage = ServerStorage(tmp_path / "server-storage")
    projects = ProjectStore(
        storage=storage,
        state_path=tmp_path / "state" / "projects.json",
    )
    credentials = CredentialStore(
        state_path=tmp_path / "state" / "credentials.json",
        secret_root=tmp_path / "secrets",
        forbidden_roots=(storage.root,),
    )
    return GitRepositoryService(
        projects,
        credentials,
        allowed_local_remote_roots=(tmp_path,),
    ), projects


def test_clone_status_commit_and_log_against_local_bare_remote(tmp_path: Path):
    remote, initial = init_remote(tmp_path)
    git, projects = service(tmp_path)

    project = git.clone("demo", str(remote))
    run_git(project.path, "config", "user.email", "test@example.com")
    run_git(project.path, "config", "user.name", "Test User")

    status = git.status("demo")
    assert status.branch == "main"
    assert status.porcelain == ""

    (project.path / "README.md").write_text("v2\n", encoding="utf-8")
    dirty = git.status("demo")
    assert "README.md" in dirty.porcelain

    git.add("demo", ["README.md"])
    commit = git.commit("demo", "update readme")
    assert commit.commit_id != initial
    assert git.status("demo").porcelain == ""

    entries = git.log("demo", limit=2)
    assert entries[0].commit_id == commit.commit_id
    assert entries[0].subject == "update readme"
    assert projects.get("demo").path == project.path


def test_diff_supports_worktree_and_staged_views(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    (project.path / "README.md").write_text("changed\n", encoding="utf-8")

    assert "+changed" in git.diff("demo")
    git.add("demo", ["README.md"])
    assert git.diff("demo") == ""
    assert "+changed" in git.diff("demo", staged=True)


def test_fetch_and_fast_forward_pull(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))

    writer = tmp_path / "writer"
    subprocess.run(["git", "clone", str(remote), str(writer)], check=True, capture_output=True)
    run_git(writer, "config", "user.email", "writer@example.com")
    run_git(writer, "config", "user.name", "Writer")
    (writer / "remote.txt").write_text("from remote\n", encoding="utf-8")
    run_git(writer, "add", "remote.txt")
    run_git(writer, "commit", "-m", "remote update")
    run_git(writer, "push", "origin", "main")

    git.fetch("demo")
    assert run_git(project.path, "rev-parse", "origin/main") != run_git(
        project.path, "rev-parse", "HEAD"
    )

    git.pull("demo", remote="origin", branch="main")
    assert (project.path / "remote.txt").read_text(encoding="utf-8") == "from remote\n"


def test_pull_conflict_preserves_worktree(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))

    (project.path / "README.md").write_text("local dirty\n", encoding="utf-8")

    writer = tmp_path / "writer"
    subprocess.run(["git", "clone", str(remote), str(writer)], check=True, capture_output=True)
    run_git(writer, "config", "user.email", "writer@example.com")
    run_git(writer, "config", "user.name", "Writer")
    (writer / "README.md").write_text("remote change\n", encoding="utf-8")
    run_git(writer, "add", "README.md")
    run_git(writer, "commit", "-m", "conflicting remote change")
    run_git(writer, "push", "origin", "main")

    before = (project.path / "README.md").read_text(encoding="utf-8")
    with pytest.raises(GitRepositoryError, match="GIT_COMMAND_FAILED"):
        git.pull("demo", remote="origin", branch="main")

    assert (project.path / "README.md").read_text(encoding="utf-8") == before
    assert "README.md" in git.status("demo").porcelain


def test_branch_create_switch_and_list(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    git.clone("demo", str(remote))

    git.branch_create("demo", "feature/demo")
    git.switch("demo", "feature/demo")

    assert git.status("demo").branch == "feature/demo"
    branches = git.branch_list("demo")
    assert "main" in branches
    assert "feature/demo" in branches


def test_remote_list_and_set_url(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    git.clone("demo", str(remote))

    remotes = git.remote_list("demo")
    assert remotes["origin"] == str(remote)

    replacement = tmp_path / "replacement.git"
    subprocess.run(["git", "init", "--bare", str(replacement)], check=True, capture_output=True)
    git.remote_set("demo", "origin", str(replacement))
    assert git.remote_list("demo")["origin"] == str(replacement)


def test_add_rejects_path_traversal(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    git.clone("demo", str(remote))

    with pytest.raises(ValueError, match="relative"):
        git.add("demo", ["../outside.txt"])


def test_clone_failure_rolls_back_project_registration(tmp_path: Path):
    git, projects = service(tmp_path)

    with pytest.raises(GitRepositoryError):
        git.clone("broken", str(tmp_path / "does-not-exist.git"))

    with pytest.raises(KeyError):
        projects.get("broken")
    assert not (tmp_path / "server-storage" / "projects" / "broken").exists()


def test_remote_set_rejects_http_remote_with_embedded_credentials(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    git.clone("demo", str(remote))

    with pytest.raises(ValueError, match="credential"):
        git.remote_set(
            "demo",
            "origin",
            "https://user:super-secret@example.test/team/repo.git",
        )

    assert "super-secret" not in git.remote_list("demo")["origin"]


def test_default_git_service_rejects_untrusted_local_remote(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    storage = ServerStorage(tmp_path / "locked-server-storage")
    projects = ProjectStore(
        storage=storage,
        state_path=tmp_path / "locked-state" / "projects.json",
    )
    credentials = CredentialStore(
        state_path=tmp_path / "locked-state" / "credentials.json",
        secret_root=tmp_path / "locked-secrets",
        forbidden_roots=(storage.root,),
    )
    git = GitRepositoryService(projects, credentials)

    with pytest.raises(ValueError, match="local Git remote"):
        git.clone("blocked", str(remote))

    with pytest.raises(KeyError):
        projects.get("blocked")
