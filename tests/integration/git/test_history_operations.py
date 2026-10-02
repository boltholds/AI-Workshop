from __future__ import annotations

import inspect
from pathlib import Path
import subprocess

import pytest

from ai_workshop.git.destructive import GitDestructiveService
from ai_workshop.git.service import GitRepositoryError
from tests.integration.git.test_repository_service import (
    init_remote,
    run_git,
    service,
)


def configure_user(root: Path) -> None:
    run_git(root, "config", "user.email", "test@example.com")
    run_git(root, "config", "user.name", "Test User")


def test_normal_push_has_no_force_option(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    parameters = inspect.signature(git.push).parameters
    assert "force" not in parameters
    assert "force_with_lease" not in parameters

    (project.path / "local.txt").write_text("local\n", encoding="utf-8")
    git.add("demo", ["local.txt"])
    git.commit("demo", "local commit")
    git.push("demo", remote="origin", branch="main")

    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert remote_head == run_git(project.path, "rev-parse", "HEAD")


def test_normal_push_rejects_non_fast_forward(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    writer = tmp_path / "writer"
    subprocess.run(["git", "clone", str(remote), str(writer)], check=True, capture_output=True)
    configure_user(writer)
    (writer / "remote.txt").write_text("remote\n", encoding="utf-8")
    run_git(writer, "add", "remote.txt")
    run_git(writer, "commit", "-m", "remote")
    run_git(writer, "push", "origin", "main")

    (project.path / "local.txt").write_text("local\n", encoding="utf-8")
    git.add("demo", ["local.txt"])
    git.commit("demo", "local")

    with pytest.raises(GitRepositoryError, match="GIT_COMMAND_FAILED"):
        git.push("demo", remote="origin", branch="main")


def test_merge_and_cherry_pick_are_explicit_operations(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    git.branch_create("demo", "feature")
    git.switch("demo", "feature")
    (project.path / "feature.txt").write_text("feature\n", encoding="utf-8")
    git.add("demo", ["feature.txt"])
    feature_commit = git.commit("demo", "feature").commit_id

    git.switch("demo", "main")
    git.merge("demo", "feature")
    assert (project.path / "feature.txt").read_text(encoding="utf-8") == "feature\n"

    git.branch_create("demo", "other")
    git.switch("demo", "other")
    (project.path / "picked.txt").write_text("picked\n", encoding="utf-8")
    git.add("demo", ["picked.txt"])
    picked = git.commit("demo", "picked").commit_id
    git.switch("demo", "main")
    git.cherry_pick("demo", picked)

    assert (project.path / "picked.txt").read_text(encoding="utf-8") == "picked\n"
    assert feature_commit in {entry.commit_id for entry in git.log("demo", limit=10)}


def test_rebase_conflict_can_be_aborted_and_preserves_branch_state(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    git.branch_create("demo", "feature")
    git.switch("demo", "feature")
    (project.path / "README.md").write_text("feature\n", encoding="utf-8")
    git.add("demo", ["README.md"])
    git.commit("demo", "feature change")
    feature_head = run_git(project.path, "rev-parse", "HEAD")

    git.switch("demo", "main")
    (project.path / "README.md").write_text("main\n", encoding="utf-8")
    git.add("demo", ["README.md"])
    git.commit("demo", "main change")

    git.switch("demo", "feature")
    with pytest.raises(GitRepositoryError):
        git.rebase("demo", "main")

    git.rebase_abort("demo")
    assert run_git(project.path, "rev-parse", "HEAD") == feature_head
    assert (project.path / "README.md").read_text(encoding="utf-8") == "feature\n"


def test_hard_reset_requires_bound_confirmation_token(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)
    before = run_git(project.path, "rev-parse", "HEAD")

    (project.path / "second.txt").write_text("second\n", encoding="utf-8")
    git.add("demo", ["second.txt"])
    git.commit("demo", "second")

    destructive = GitDestructiveService(git)
    preview = destructive.preview_hard_reset("demo", before)

    with pytest.raises(PermissionError, match="confirmation"):
        destructive.hard_reset("demo", before, "missing")

    token = destructive.prepare(preview).token
    result = destructive.hard_reset("demo", before, token)

    assert result.completed is True
    assert run_git(project.path, "rev-parse", "HEAD") == before
    assert not (project.path / "second.txt").exists()


def test_destructive_token_rejects_repository_change_after_prepare(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)
    target = run_git(project.path, "rev-parse", "HEAD")

    destructive = GitDestructiveService(git)
    preview = destructive.preview_hard_reset("demo", target)
    token = destructive.prepare(preview).token

    (project.path / "changed.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(PermissionError, match="changed since confirmation"):
        destructive.hard_reset("demo", target, token)


def test_delete_branch_and_tag_require_confirmation(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)
    git.branch_create("demo", "delete-me")
    git.tag("demo", "delete-tag")

    destructive = GitDestructiveService(git)

    branch_preview = destructive.preview_delete_branch("demo", "delete-me")
    branch_token = destructive.prepare(branch_preview).token
    destructive.delete_branch("demo", "delete-me", branch_token)
    assert "delete-me" not in git.branch_list("demo")

    tag_preview = destructive.preview_delete_tag("demo", "delete-tag")
    tag_token = destructive.prepare(tag_preview).token
    destructive.delete_tag("demo", "delete-tag", tag_token)
    assert "delete-tag" not in run_git(project.path, "tag").splitlines()


def test_force_push_requires_confirmation_and_uses_force_with_lease(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    initial = run_git(project.path, "rev-parse", "HEAD")
    (project.path / "replacement.txt").write_text("replacement\n", encoding="utf-8")
    git.add("demo", ["replacement.txt"])
    git.commit("demo", "replacement")
    replacement = run_git(project.path, "rev-parse", "HEAD")

    run_git(project.path, "reset", "--hard", initial)
    (project.path / "new-history.txt").write_text("new history\n", encoding="utf-8")
    git.add("demo", ["new-history.txt"])
    rewritten = git.commit("demo", "rewritten").commit_id

    # First put the other commit on the remote so normal push becomes non-fast-forward.
    run_git(project.path, "push", "origin", f"{replacement}:main")

    destructive = GitDestructiveService(git)
    preview = destructive.preview_force_push("demo", remote="origin", branch="main")
    token = destructive.prepare(preview).token
    destructive.force_push(
        "demo",
        remote="origin",
        branch="main",
        confirmation_token=token,
    )

    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert remote_head == rewritten


def test_force_push_confirmation_rejects_remote_url_change(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    destructive = GitDestructiveService(git)
    preview = destructive.preview_force_push("demo", remote="origin", branch="main")
    token = destructive.prepare(preview).token

    replacement = tmp_path / "replacement.git"
    subprocess.run(
        ["git", "init", "--bare", str(replacement)],
        check=True,
        capture_output=True,
    )
    git.remote_set("demo", "origin", str(replacement))

    with pytest.raises(PermissionError, match="changed since confirmation"):
        destructive.force_push(
            "demo",
            remote="origin",
            branch="main",
            confirmation_token=token,
        )


def test_delete_branch_confirmation_rejects_target_ref_change(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    git.branch_create("demo", "other")
    git.switch("demo", "other")
    (project.path / "other.txt").write_text("other\n", encoding="utf-8")
    git.add("demo", ["other.txt"])
    git.commit("demo", "other commit")
    git.switch("demo", "main")

    git.branch_create("demo", "delete-me")
    destructive = GitDestructiveService(git)
    preview = destructive.preview_delete_branch("demo", "delete-me")
    token = destructive.prepare(preview).token

    run_git(project.path, "branch", "-f", "delete-me", "other")
    assert git.status("demo").porcelain == ""

    with pytest.raises(PermissionError, match="changed since confirmation"):
        destructive.delete_branch("demo", "delete-me", token)


def test_hard_reset_confirmation_rejects_target_ref_change(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    git.branch_create("demo", "other")
    git.switch("demo", "other")
    (project.path / "other.txt").write_text("other\n", encoding="utf-8")
    git.add("demo", ["other.txt"])
    git.commit("demo", "other commit")
    git.switch("demo", "main")

    git.branch_create("demo", "target")
    destructive = GitDestructiveService(git)
    preview = destructive.preview_hard_reset("demo", "target")
    token = destructive.prepare(preview).token

    run_git(project.path, "branch", "-f", "target", "other")
    assert git.status("demo").porcelain == ""

    with pytest.raises(PermissionError, match="changed since confirmation"):
        destructive.hard_reset("demo", "target", token)


def test_delete_tag_confirmation_rejects_target_ref_change(tmp_path: Path):
    remote, _ = init_remote(tmp_path)
    git, _ = service(tmp_path)
    project = git.clone("demo", str(remote))
    configure_user(project.path)

    git.branch_create("demo", "other")
    git.switch("demo", "other")
    (project.path / "other-tag.txt").write_text("other\n", encoding="utf-8")
    git.add("demo", ["other-tag.txt"])
    git.commit("demo", "other tag commit")
    git.switch("demo", "main")

    git.tag("demo", "delete-tag")
    destructive = GitDestructiveService(git)
    preview = destructive.preview_delete_tag("demo", "delete-tag")
    token = destructive.prepare(preview).token

    run_git(project.path, "tag", "-f", "delete-tag", "other")
    assert git.status("demo").porcelain == ""

    with pytest.raises(PermissionError, match="changed since confirmation"):
        destructive.delete_tag("demo", "delete-tag", token)
