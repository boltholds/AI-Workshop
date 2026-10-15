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


def _manifest_closure(root: Path, manifest_path: str) -> list[Path]:
    """Discover only Cargo manifests in the selected package/workspace graph.

    Arbitrary nested fixture projects are not dependencies. In particular, a
    top-level crate must not read an unrelated validation/Cargo.toml.
    """
    import fnmatch
    import glob
    import tomllib

    root = root.resolve(strict=True)
    pending = [root / manifest_relative_path(manifest_path)]
    manifests: set[Path] = set()

    def bounded(candidate: Path) -> Path:
        if candidate.is_symlink():
            raise ValueError('Cargo manifest symlinks are not supported')
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise ValueError('Cargo path dependency escapes project checkout')
        return resolved

    def dependency_paths(table: object, base: Path) -> list[Path]:
        if not isinstance(table, dict):
            return []
        return [
            base / dependency['path'] / 'Cargo.toml'
            for dependency in table.values()
            if isinstance(dependency, dict) and isinstance(dependency.get('path'), str)
        ]

    while pending:
        manifest = bounded(pending.pop())
        if manifest in manifests:
            continue
        if not manifest.is_file() or manifest.name != 'Cargo.toml':
            raise ValueError('Cargo dependency manifest missing')
        if manifest.stat().st_size > _MAX_MANIFEST_SIZE:
            raise ValueError('Cargo manifest exceeds limit')
        data = tomllib.loads(manifest.read_text(encoding='utf-8'))
        manifests.add(manifest)
        base = manifest.parent

        for key in ('dependencies', 'dev-dependencies', 'build-dependencies'):
            pending.extend(dependency_paths(data.get(key), base))

        for target in data.get('target', {}).values():
            if isinstance(target, dict):
                for key in ('dependencies', 'dev-dependencies', 'build-dependencies'):
                    pending.extend(dependency_paths(target.get(key), base))

        for section in ('patch', 'replace'):
            tables = data.get(section, {})
            if section == 'replace':
                pending.extend(dependency_paths(tables, base))
            elif isinstance(tables, dict):
                for dependencies in tables.values():
                    pending.extend(dependency_paths(dependencies, base))

        workspace = data.get('workspace')
        if isinstance(workspace, dict):
            pending.extend(dependency_paths(workspace.get('dependencies'), base))
            exclusions = workspace.get('exclude', [])
            for pattern in workspace.get('members', []):
                if not isinstance(pattern, str):
                    raise ValueError('invalid Cargo workspace member pattern')
                for matched in glob.glob(str(base / pattern), recursive=True):
                    candidate = bounded(Path(matched))
                    if not candidate.is_dir() or not (candidate / 'Cargo.toml').is_file():
                        continue
                    relative = candidate.relative_to(base).as_posix()
                    if any(fnmatch.fnmatchcase(relative, exclude) for exclude in exclusions):
                        continue
                    pending.append(candidate / 'Cargo.toml')

        package = data.get('package')
        if isinstance(package, dict) and isinstance(package.get('workspace'), str):
            pending.append(base / package['workspace'] / 'Cargo.toml')

        # Cargo infers workspace membership from ancestor [workspace] tables.
        # A parent [package] alone does not make a nested validation crate a
        # workspace member.
        ancestor = base.parent
        while ancestor.is_relative_to(root):
            parent_manifest = ancestor / 'Cargo.toml'
            if parent_manifest.is_file() and parent_manifest not in manifests:
                if parent_manifest.stat().st_size > _MAX_MANIFEST_SIZE:
                    raise ValueError('Cargo ancestor manifest exceeds limit')
                parent_data = tomllib.loads(parent_manifest.read_text(encoding='utf-8'))
                if isinstance(parent_data.get('workspace'), dict):
                    pending.append(parent_manifest)
                    break
            if ancestor == root:
                break
            ancestor = ancestor.parent

    return sorted(manifests)


def _input_files(root: Path, manifest_path: str) -> list[Path]:
    """Fingerprint only dependency-relevant manifests, locks and config."""
    root = root.resolve(strict=True)
    found: set[Path] = set()
    for manifest in _manifest_closure(root, manifest_path):
        found.add(manifest)
        lock = manifest.parent / 'Cargo.lock'
        if lock.is_file():
            found.add(lock)

        # Cargo config can affect dependency sources and index resolution.
        folder = manifest.parent
        while folder.is_relative_to(root):
            for config_name in ('config', 'config.toml'):
                config = folder / '.cargo' / config_name
                if config.is_file():
                    found.add(config)
            if folder == root:
                break
            folder = folder.parent

    for entry in found:
        if entry.is_symlink():
            raise ValueError('Cargo input symlinks are not supported')
    return sorted(found)


def dependency_fingerprint(root: Path, manifest_path: str) -> str:
    relative = manifest_relative_path(manifest_path)
    manifest = root / relative
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError('Cargo.toml missing or symlinked')
    digest = hashlib.sha256()
    digest.update(relative.as_posix().encode('utf-8') + b'\x00')
    files = _input_files(root, manifest_path)
    for entry in files:
        if entry.stat().st_size > _MAX_MANIFEST_SIZE:
            raise ValueError('Cargo manifest/configuration exceeds limit')
        digest.update(entry.relative_to(root).as_posix().encode('utf-8') + b'\x00')
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def snapshot_project(
    root: Path, destination: Path, manifest_path: str = 'Cargo.toml',
) -> None:
    """Copy the selected crate's source, excluding unrelated nested projects.

    Cargo tests run against a private snapshot. The original project is
    untouched and standalone validation crates are prepared separately.
    """
    if destination.exists():
        raise ValueError('snapshot destination already exists')
    root = root.resolve(strict=True)
    participating = {m.parent for m in _manifest_closure(root, manifest_path)}

    def ignored(directory: str, names: list[str]) -> set[str]:
        parent = Path(directory)
        excluded: set[str] = set()
        for name in names:
            entry = parent / name
            if name in _SKIPPED_DIRS or name in _SKIPPED_FILES:
                excluded.add(name)
                continue
            if entry.is_symlink():
                raise ValueError('project symlinks are not supported in Cargo snapshots')
            if entry.is_dir() and (entry / 'Cargo.toml').is_file():
                # Keep declared path dependencies and workspace members,
                # including any ancestors needed to reach a nested member.
                if not any(
                    package_dir == entry or package_dir.is_relative_to(entry)
                    for package_dir in participating
                ):
                    excluded.add(name)
        return excluded

    shutil.copytree(root, destination, ignore=ignored, symlinks=False)
    for folder, dirs, files in os.walk(destination):
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
