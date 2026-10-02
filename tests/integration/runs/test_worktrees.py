from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ai_workshop.projects.store import ProjectStore
from ai_workshop.runs.workspaces import RunWorkspaceManager
from ai_workshop.server.storage import ServerStorage


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def fixture(tmp_path: Path):
    storage = ServerStorage(tmp_path / "server-storage")
    projects = ProjectStore(
        storage=storage,
        state_path=tmp_path / "state" / "projects.json",
    )
    project = projects.register_git("demo", remote_url="ssh://git@example.test/demo.git")
    run_git(project.path, "init")
    run_git(project.path, "config", "user.email", "test@example.com")
    run_git(project.path, "config", "user.name", "Test User")
    run_git(project.path, "checkout", "-b", "main")
    (project.path / "README.md").write_text("base\n", encoding="utf-8")
    run_git(project.path, "add", "README.md")
    run_git(project.path, "commit", "-m", "initial")
    return storage, projects, project


def test_parallel_runs_use_distinct_worktrees(tmp_path: Path):
    storage, projects, project = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)

    first = manager.create("demo", "run-one", "main", writable=True)
    second = manager.create("demo", "run-two", "main", writable=True)

    assert first.path != second.path
    assert first.path == storage.run_root("run-one") / "workspace"
    assert second.path == storage.run_root("run-two") / "workspace"
    assert (first.path / "README.md").read_text(encoding="utf-8") == "base\n"
    assert (second.path / "README.md").read_text(encoding="utf-8") == "base\n"
    assert run_git(first.path, "rev-parse", "HEAD") == run_git(second.path, "rev-parse", "HEAD")
    assert run_git(first.path, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert run_git(second.path, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"


def test_run_workspace_isolated_from_canonical_project(tmp_path: Path):
    storage, projects, project = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)

    workspace = manager.create("demo", "run-one", "main", writable=True)
    (workspace.path / "README.md").write_text("run edit\n", encoding="utf-8")

    assert (project.path / "README.md").read_text(encoding="utf-8") == "base\n"


def test_read_only_intent_is_recorded_on_workspace(tmp_path: Path):
    storage, projects, _ = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)

    workspace = manager.create("demo", "run-read", "main", writable=False)

    assert workspace.writable is False
    assert workspace.project_id == "demo"
    assert workspace.run_id == "run-read"


def test_remove_deletes_worktree_and_prunes_git_registration(tmp_path: Path):
    storage, projects, project = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)
    workspace = manager.create("demo", "run-one", "main", writable=True)

    manager.remove("run-one")

    assert not workspace.path.exists()
    listed = run_git(project.path, "worktree", "list", "--porcelain")
    assert str(workspace.path) not in listed


def test_create_rejects_non_git_managed_project(tmp_path: Path):
    storage = ServerStorage(tmp_path / "server-storage")
    external_root = tmp_path / "external"
    external_root.mkdir()
    external = external_root / "repo"
    external.mkdir()
    projects = ProjectStore(
        storage=storage,
        state_path=tmp_path / "state" / "projects.json",
        external_roots=(external_root,),
    )
    projects.register_external("external", external)
    manager = RunWorkspaceManager(projects, storage)

    with pytest.raises(ValueError, match="Git-managed"):
        manager.create("external", "run-one", "HEAD", writable=True)


def test_create_rejects_ref_cli_fragment(tmp_path: Path):
    storage, projects, _ = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)

    with pytest.raises(ValueError, match="base ref"):
        manager.create("demo", "run-one", "--help", writable=True)


def test_remove_unknown_run_is_idempotent(tmp_path: Path):
    storage, projects, _ = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)

    manager.remove("missing")


def test_remove_worktree_survives_project_deregistration(tmp_path: Path):
    storage, projects, _ = fixture(tmp_path)
    manager = RunWorkspaceManager(projects, storage)
    workspace = manager.create("demo", "run-one", "main", writable=True)

    projects.remove_registration("demo")
    manager.remove("run-one")

    assert not workspace.path.exists()
    assert not (storage.run_root("run-one") / "workspace.json").exists()
