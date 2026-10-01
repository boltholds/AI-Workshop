from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from uuid import uuid4

from ai_workshop.recovery.models import SnapshotManifest
from ai_workshop.recovery.store import SnapshotStore
from ai_workshop.workspace.paths import PathPolicy


class GitSnapshotService:
    def __init__(self, policy: PathPolicy, store: SnapshotStore):
        self.policy = policy
        self.store = store

    def create(self, project_id: str) -> SnapshotManifest:
        root = self.policy.project_root(project_id)
        self._ensure_git_repository(root)

        snapshot_id = uuid4().hex
        snapshot_dir = self.store.project_dir(snapshot_id, project_id)

        head = self._git(root, "rev-parse", "HEAD").decode().strip()
        branch_raw = self._git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        branch = branch_raw.decode().strip() or None
        repository_id = self._repository_id(root)

        staged_patch = self._git(root, "diff", "--binary", "--cached")
        unstaged_patch = self._git(root, "diff", "--binary")
        (snapshot_dir / "staged.patch").write_bytes(staged_patch)
        (snapshot_dir / "unstaged.patch").write_bytes(unstaged_patch)

        untracked_files = self._untracked_files(root)
        self._write_untracked_archive(root, untracked_files, snapshot_dir / "untracked.tar")

        file_hashes = self._hash_worktree(root)
        manifest = SnapshotManifest(
            snapshot_id=snapshot_id,
            project_id=project_id,
            repository_id=repository_id,
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
    def _ensure_git_repository(root: Path) -> None:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            raise ValueError("project is not a Git working tree")

    @staticmethod
    def _git(root: Path, *args: str, check: bool = True) -> bytes:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError("Git snapshot operation failed")
        return result.stdout

    def _repository_id(self, root: Path) -> str:
        roots = self._git(root, "rev-list", "--max-parents=0", "HEAD").decode().splitlines()
        remote = self._git(root, "config", "--get", "remote.origin.url", check=False).decode().strip()
        material = "\n".join(sorted(roots)) + "\n" + remote
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _untracked_files(self, root: Path) -> list[str]:
        raw = self._git(root, "ls-files", "--others", "--exclude-standard", "-z")
        paths = [part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\x00") if part]
        return sorted(paths)

    @staticmethod
    def _write_untracked_archive(root: Path, paths: list[str], output: Path) -> None:
        with tarfile.open(output, "w", dereference=False) as archive:
            for relative in paths:
                path = (root / relative)
                # Git only reports paths under the worktree. Preserve symlinks as
                # links rather than following them outside the project boundary.
                archive.add(path, arcname=relative, recursive=False)

    @staticmethod
    def _hash_worktree(root: Path) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if ".git" in relative.parts:
                continue
            key = relative.as_posix()
            if path.is_symlink():
                target = path.readlink().as_posix()
                hashes[key] = hashlib.sha256(
                    ("symlink:" + target).encode("utf-8", errors="surrogateescape")
                ).hexdigest()
                continue
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[key] = digest.hexdigest()
        return hashes
