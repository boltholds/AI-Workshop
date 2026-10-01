from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from uuid import uuid4

from ai_workshop.recovery.env import safe_subprocess_env
from ai_workshop.recovery.models import SnapshotManifest
from ai_workshop.recovery.store import SnapshotStore
from ai_workshop.workspace.paths import PathPolicy


def git_bytes(root: Path, *args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=safe_subprocess_env(),
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError("Git recovery operation failed")
    return result.stdout


def ensure_git_repository(root: Path) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        env=safe_subprocess_env(),
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise ValueError("project is not a Git working tree")


def repository_identity(root: Path) -> str:
    ensure_git_repository(root)
    roots = git_bytes(root, "rev-list", "--max-parents=0", "HEAD").decode().splitlines()
    remote = git_bytes(root, "config", "--get", "remote.origin.url", check=False).decode().strip()
    material = "\n".join(sorted(roots)) + "\n" + remote
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def git_visible_files(root: Path) -> list[str]:
    raw = git_bytes(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted(
        part.decode("utf-8", errors="surrogateescape")
        for part in raw.split(b"\x00")
        if part
    )


def worktree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in git_visible_files(root):
        path = root / relative
        if path.is_symlink():
            target = path.readlink().as_posix()
            hashes[relative] = hashlib.sha256(
                ("symlink:" + target).encode("utf-8", errors="surrogateescape")
            ).hexdigest()
            continue
        if not path.is_file():
            # Deleted tracked files are intentionally absent.
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes[relative] = digest.hexdigest()
    return hashes


class GitSnapshotService:
    def __init__(self, policy: PathPolicy, store: SnapshotStore):
        self.policy = policy
        self.store = store

    def create(self, project_id: str) -> SnapshotManifest:
        root = self.policy.project_root(project_id)
        ensure_git_repository(root)

        snapshot_id = uuid4().hex
        snapshot_dir = self.store.project_dir(snapshot_id, project_id)

        head = git_bytes(root, "rev-parse", "HEAD").decode().strip()
        branch_raw = git_bytes(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        branch = branch_raw.decode().strip() or None
        repo_id = repository_identity(root)

        staged_patch = git_bytes(root, "diff", "--binary", "--cached")
        unstaged_patch = git_bytes(root, "diff", "--binary")
        (snapshot_dir / "staged.patch").write_bytes(staged_patch)
        (snapshot_dir / "unstaged.patch").write_bytes(unstaged_patch)

        untracked_files = self._untracked_files(root)
        self._write_untracked_archive(root, untracked_files, snapshot_dir / "untracked.tar")

        file_hashes = worktree_hashes(root)
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            project_id=project_id,
            repository_id=repo_id,
            head=head,
            branch=branch,
            staged_patch_bytes=len(staged_patch),
            unstaged_patch_bytes=len(unstaged_patch),
            untracked_files=untracked_files,
            file_hashes=file_hashes,
        )
        (snapshot_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def _untracked_files(root: Path) -> list[str]:
        raw = git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z")
        return sorted(
            part.decode("utf-8", errors="surrogateescape")
            for part in raw.split(b"\x00")
            if part
        )

    @staticmethod
    def _write_untracked_archive(root: Path, paths: list[str], output: Path) -> None:
        with tarfile.open(output, "w", dereference=False) as archive:
            for relative in paths:
                archive.add(root / relative, arcname=relative, recursive=False)
