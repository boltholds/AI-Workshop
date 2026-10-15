"""Shared, deliberately bounded Cargo preparation helpers.

The prefetch container may use the network. The analysis worker never does.
Only committed-looking manifest inputs are fingerprinted; source files are
snapshotted independently and may change without invalidating dependency cache.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

PROJECT_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
_SKIPPED_DIRS = frozenset({
    '.git', '.ssh', '.workshop', '.workshop-server', '.venv',
    'target', 'node_modules', '__pycache__', '.idea',
})
_SKIPPED_FILES = frozenset({
    '.env', '.env.local', 'credentials', 'credentials.toml',
})
_MAX_MANIFEST_SIZE = 1_048_576


def validate_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise ValueError('invalid Cargo project id')
    return project_id


def manifest_relative_path(path: str) -> Path:
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('invalid manifest path')
    relative = Path(path)
    if relative.is_absolute() or '..' in relative.parts or relative.name != 'Cargo.toml':
        raise ValueError('manifest must be a project-relative Cargo.toml')
    if any(part in _SKIPPED_DIRS or part in _SKIPPED_FILES for part in relative.parts):
        raise ValueError('manifest resides in a protected location')
    return relative


def _input_files(root: Path) -> list[Path]:
    collected: list[Path] = []
    for folder, dirs, files in os.walk(root, followlinks=False):
        parent = Path(folder)
        dirs[:] = sorted(
            name for name in dirs
            if name not in _SKIPPED_DIRS and not (parent / name).is_symlink()
        )
        for name in sorted(files):
            entry = parent / name
            if entry.is_symlink():
                raise ValueError('Cargo input symlinks are not supported')
            if name in ('Cargo.toml', 'Cargo.lock') or (
                name in ('config', 'config.toml') and parent.name == '.cargo'
            ):
                collected.append(entry)
    return sorted(collected)


def dependency_fingerprint(root: Path, manifest_path: str) -> str:
    relative = manifest_relative_path(manifest_path)
    manifest = root / relative
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError('Cargo.toml missing or symlinked')
    digest = hashlib.sha256()
    digest.update(relative.as_posix().encode('utf-8') + b'\x00')
    files = _input_files(root)
    if not files:
        raise ValueError('no Cargo manifests')
    for entry in files:
        if entry.stat().st_size > _MAX_MANIFEST_SIZE:
            raise ValueError('Cargo manifest/configuration exceeds limit')
        digest.update(entry.relative_to(root).as_posix().encode('utf-8') + b'\x00')
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def snapshot_project(root: Path, destination: Path) -> None:
    """Copy read-only project data to private scratch, without following symlinks.

    Deliberately excludes Git internals, build outputs and private local settings.
    A project with remaining symlinks is rejected rather than escaping a mount.
    """
    if destination.exists():
        raise ValueError('snapshot destination already exists')

    def ignored(directory: str, names: list[str]) -> set[str]:
        return {
            name for name in names
            if name in _SKIPPED_DIRS or name in _SKIPPED_FILES
        }

    for folder, dirs, files in os.walk(root, followlinks=False):
        parent = Path(folder)
        dirs[:] = [d for d in dirs if d not in _SKIPPED_DIRS]
        for entry_name in dirs + files:
            if (parent / entry_name).is_symlink() and (
                entry_name not in _SKIPPED_DIRS and entry_name not in _SKIPPED_FILES
            ):
                raise ValueError('project symlinks are not supported in Cargo snapshots')

    shutil.copytree(root, destination, ignore=ignored, symlinks=False)
    for folder, dirs, files in os.walk(destination):
        # Source files created by a restrictive atomic writer may still be 0600.
        # A private scratch copy is owned by this process and never changes source.
        for name in files:
            dest = Path(folder) / name
            dest.chmod(stat.S_IMODE(dest.stat().st_mode) | 0o600)
        for name in dirs:
            dest = Path(folder) / name
            dest.chmod(stat.S_IMODE(dest.stat().st_mode) | 0o700)


def prepared_directory(locks_root: Path, project_id: str, fingerprint: str) -> Path:
    validate_project_id(project_id)
    if not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
        raise ValueError('invalid Cargo fingerprint')
    return locks_root / project_id / fingerprint


def read_prepared_lock(
    locks_root: Path, project_id: str, fingerprint: str, manifest_path: str,
) -> tuple[Path, Path]:
    root = prepared_directory(locks_root, project_id, fingerprint)
    metadata = json.loads((root / 'metadata.json').read_text(encoding='utf-8'))
    if metadata.get('fingerprint') != fingerprint or metadata.get('manifest') != manifest_path:
        raise ValueError('Cargo prefetch does not match this manifest')
    lock_relative = Path(metadata['lock_path'])
    if (lock_relative.is_absolute() or '..' in lock_relative.parts
            or lock_relative.name != 'Cargo.lock'):
        raise ValueError('invalid prepared Cargo.lock path')
    lock_file = root / lock_relative
    if lock_file.is_symlink() or not lock_file.is_file():
        raise ValueError('prepared Cargo.lock is missing')
    if hashlib.sha256(lock_file.read_bytes()).hexdigest() != metadata.get('sha256'):
        raise ValueError('prepared Cargo.lock checksum mismatch')
    return lock_relative, lock_file


def stage_readonly_cache(cache_root: Path, cargo_home: Path) -> None:
    """Keep registry and git data private to each test process.

    Copying prevents Cargo from writing to or poisoning the shared cache and
    permits its local index locks to be created even with an offline RO mount.
    """
    cargo_home.mkdir(mode=0o700)
    for name in ('registry', 'git'):
        source = cache_root / name
        if source.exists():
            if source.is_symlink() or not source.is_dir():
                raise ValueError('invalid prepared Cargo cache directory')
            shutil.copytree(source, cargo_home / name, symlinks=False)
