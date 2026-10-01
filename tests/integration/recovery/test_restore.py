from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.recovery.git_snapshot import GitSnapshotService
from ai_workshop.recovery.restore import RestoreService
from ai_workshop.recovery.store import SnapshotStore
from ai_workshop.workspace.paths import PathPolicy


def git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_repo(root: Path, *, text: str = "base\n") -> None:
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "tracked.txt").write_text(text, encoding="utf-8")
    git(root, "add", "tracked.txt")
    git(root, "commit", "-m", "initial")


def services(root: Path, state: Path, *, clock=None):
    config = WorkshopConfig(projects=[
        ProjectMount(project_id="project", host=root, container="/workspace/project", mode="rw")
    ])
    policy = PathPolicy(config, host_paths=True)
    store = SnapshotStore(state)
    snapshots = GitSnapshotService(policy, store)
    restores = RestoreService(policy, store, clock=clock)
    return snapshots, restores


def dirty_snapshot(root: Path, state: Path):
    snapshots, restores = services(root, state)
    (root / "tracked.txt").write_text("staged\n", encoding="utf-8")
    git(root, "add", "tracked.txt")
    (root / "tracked.txt").write_text("staged\nunstaged\n", encoding="utf-8")
    (root / "preexisting.txt").write_text("preexisting\n", encoding="utf-8")
    manifest = snapshots.create("project")
    return manifest, restores


def test_restore_round_trip_preserves_dirty_snapshot(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    init_repo(root)
    manifest, restores = dirty_snapshot(root, tmp_path / "state")
    status_before = git(root, "status", "--porcelain=v1")
    staged_before = git(root, "diff", "--cached")
    unstaged_before = git(root, "diff")
    contents_before = (root / "tracked.txt").read_text(encoding="utf-8")

    # Mutate everything after the snapshot.
    (root / "tracked.txt").write_text("later\n", encoding="utf-8")
    (root / "preexisting.txt").unlink()
    (root / "created-after.txt").write_text("delete me\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-m", "later", check=True)

    preview = restores.preview(manifest.snapshot_id)
    assert "created-after.txt" in preview.delete_paths
    confirmation = restores.prepare(manifest.snapshot_id)
    result = restores.restore(manifest.snapshot_id, confirmation.token)

    assert result.snapshot_id == manifest.snapshot_id
    assert git(root, "status", "--porcelain=v1") == status_before
    assert git(root, "diff", "--cached") == staged_before
    assert git(root, "diff") == unstaged_before
    assert (root / "tracked.txt").read_text(encoding="utf-8") == contents_before
    assert (root / "preexisting.txt").read_text(encoding="utf-8") == "preexisting\n"
    assert not (root / "created-after.txt").exists()


def test_restore_rejects_different_repository(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    init_repo(root, text="first\n")
    snapshots, restores = services(root, tmp_path / "state")
    manifest = snapshots.create("project")

    # Replace only Git identity while keeping the configured project root.
    subprocess.run(["rm", "-rf", ".git"], cwd=root, check=True)
    init_repo(root, text="second\n")

    with pytest.raises(ValueError, match="repository identity"):
        restores.preview(manifest.snapshot_id)


def test_restore_cleans_only_project_root(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    init_repo(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-before\n", encoding="utf-8")
    snapshots, restores = services(root, tmp_path / "state")
    manifest = snapshots.create("project")

    (root / "new.txt").write_text("inside\n", encoding="utf-8")
    outside.write_text("outside-after\n", encoding="utf-8")
    token = restores.prepare(manifest.snapshot_id).token
    restores.restore(manifest.snapshot_id, token)

    assert not (root / "new.txt").exists()
    assert outside.read_text(encoding="utf-8") == "outside-after\n"


def test_restore_requires_valid_unexpired_confirmation(tmp_path: Path):
    now = [1000.0]
    root = tmp_path / "project"
    root.mkdir()
    init_repo(root)
    snapshots, restores = services(root, tmp_path / "state", clock=lambda: now[0])
    manifest = snapshots.create("project")
    (root / "tracked.txt").write_text("later\n", encoding="utf-8")

    with pytest.raises(PermissionError, match="confirmation"):
        restores.restore(manifest.snapshot_id, "missing")

    confirmation = restores.prepare(manifest.snapshot_id, ttl_seconds=5)
    now[0] += 6
    with pytest.raises(PermissionError, match="expired"):
        restores.restore(manifest.snapshot_id, confirmation.token)


def test_restore_token_is_bound_to_preview_digest(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    init_repo(root)
    snapshots, restores = services(root, tmp_path / "state")
    manifest = snapshots.create("project")
    (root / "tracked.txt").write_text("first mutation\n", encoding="utf-8")
    confirmation = restores.prepare(manifest.snapshot_id)

    (root / "tracked.txt").write_text("second mutation\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="changed since confirmation"):
        restores.restore(manifest.snapshot_id, confirmation.token)
