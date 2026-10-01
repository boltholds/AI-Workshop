from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tarfile

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.recovery.git_snapshot import GitSnapshotService
from ai_workshop.recovery.store import SnapshotStore
from ai_workshop.workspace.paths import PathPolicy


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_repo(root: Path) -> None:
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    (root / "binary.bin").write_bytes(b"\x00\x01base\xff")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")


def service(project_root: Path, state_root: Path) -> GitSnapshotService:
    config = WorkshopConfig(
        projects=[
            ProjectMount(
                project_id="project",
                host=project_root,
                container="/workspace/project",
                mode="rw",
            )
        ]
    )
    return GitSnapshotService(
        PathPolicy(config, host_paths=True),
        SnapshotStore(state_root),
    )


def test_snapshot_captures_clean_repository_identity(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    init_repo(project)

    manifest = service(project, tmp_path / "state").create("project")

    assert manifest.project_id == "project"
    assert manifest.head == git(project, "rev-parse", "HEAD")
    assert manifest.branch in {"master", "main"}
    assert manifest.repository_id
    assert manifest.staged_patch_bytes == 0
    assert manifest.unstaged_patch_bytes == 0
    assert manifest.untracked_files == []
    assert manifest.file_hashes["tracked.txt"]
    assert manifest.file_hashes["binary.bin"]

    manifest_path = tmp_path / "state" / manifest.snapshot_id / "project" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["head"] == manifest.head


def test_snapshot_round_trip_preserves_preexisting_dirty_state(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    init_repo(project)

    # Pre-existing staged state.
    (project / "tracked.txt").write_text("staged\n", encoding="utf-8")
    git(project, "add", "tracked.txt")

    # Additional unstaged state on the same tracked file.
    (project / "tracked.txt").write_text("staged\nunstaged\n", encoding="utf-8")

    # Untracked text and binary files.
    (project / "notes.txt").write_text("keep me\n", encoding="utf-8")
    (project / "payload.bin").write_bytes(b"\x00\x10\x20\xff")

    manifest = service(project, tmp_path / "state").create("project")
    snapshot_dir = tmp_path / "state" / manifest.snapshot_id / "project"

    staged_patch = (snapshot_dir / "staged.patch").read_bytes()
    unstaged_patch = (snapshot_dir / "unstaged.patch").read_bytes()
    assert b"staged" in staged_patch
    assert b"unstaged" in unstaged_patch

    with tarfile.open(snapshot_dir / "untracked.tar", "r") as archive:
        names = sorted(archive.getnames())
        assert names == ["notes.txt", "payload.bin"]
        assert archive.extractfile("notes.txt").read() == b"keep me\n"
        assert archive.extractfile("payload.bin").read() == b"\x00\x10\x20\xff"

    assert manifest.untracked_files == ["notes.txt", "payload.bin"]
    assert manifest.file_hashes["notes.txt"]
    assert manifest.file_hashes["payload.bin"]


def test_snapshot_keeps_binary_tracked_changes_in_git_patches(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    init_repo(project)
    (project / "binary.bin").write_bytes(b"\x00\x01changed\xfe")

    manifest = service(project, tmp_path / "state").create("project")
    snapshot_dir = tmp_path / "state" / manifest.snapshot_id / "project"
    patch = (snapshot_dir / "unstaged.patch").read_bytes()

    assert manifest.unstaged_patch_bytes == len(patch)
    assert b"GIT binary patch" in patch or b"Binary files" in patch
