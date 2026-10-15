"""One-shot *networked* Cargo fetch job; never execute build scripts or tests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from ai_workshop.analysis.cargo_cache import (
    dependency_fingerprint,
    manifest_relative_path,
    prepared_directory,
    read_prepared_lock,
    snapshot_project,
    validate_project_id,
)


def _cargo(argv: list[str], *, cwd: Path, cargo_home: Path, capture: bool = False):
    env = {
        'PATH': os.environ.get('PATH', '/usr/local/cargo/bin:/usr/local/bin:/usr/bin:/bin'),
        'HOME': '/tmp',
        'TMPDIR': '/tmp',
        'CARGO_HOME': str(cargo_home),
        'RUSTUP_HOME': os.environ.get('RUSTUP_HOME', '/usr/local/rustup'),
        'CARGO_NET_OFFLINE': 'false',
        'GIT_TERMINAL_PROMPT': '0',
    }
    return subprocess.run(
        ['cargo', *argv], cwd=cwd, env=env,
        text=True, capture_output=capture, check=True, timeout=600,
    )


def prefetch(
    project_id: str, manifest_path: str, *,
    projects_root: Path, cache_root: Path, locks_root: Path,
) -> Path:
    validate_project_id(project_id)
    manifest = manifest_relative_path(manifest_path)
    projects_root = projects_root.resolve(strict=True)
    source = (projects_root / project_id).resolve(strict=True)
    if not source.is_relative_to(projects_root) or not source.is_dir():
        raise ValueError('project path escapes registered project storage')
    if not (source / manifest).is_file():
        raise ValueError('project Cargo.toml does not exist')
    fingerprint = dependency_fingerprint(source, manifest_path)
    cache_root = cache_root.resolve(strict=True)
    locks_root = locks_root.resolve(strict=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    # Run only Cargo metadata, generate-lockfile, and fetch in disposable scratch.
    # The original checkout (including its Git index) is never modified.
    with tempfile.TemporaryDirectory(prefix='wai-cargo-prefetch-') as temporary:
        scratch = Path(temporary) / 'project'
        snapshot_project(source, scratch, manifest_path)
        prepared_manifest = scratch / manifest
        details = _cargo([
            'metadata', '--format-version', '1', '--no-deps',
            '--manifest-path', str(prepared_manifest),
        ], cwd=scratch, cargo_home=cache_root, capture=True)
        workspace_root = Path(json.loads(details.stdout)['workspace_root']).resolve(strict=True)
        if not workspace_root.is_relative_to(scratch):
            raise ValueError('Cargo workspace root escapes project snapshot')
        lock = workspace_root / 'Cargo.lock'
        if not lock.is_file():
            _cargo(['generate-lockfile', '--manifest-path', str(prepared_manifest)],
                   cwd=scratch, cargo_home=cache_root)
        if not lock.is_file():
            raise ValueError('Cargo.lock generation failed')
        lock_relative = lock.relative_to(scratch)
        _cargo([
            'fetch', '--locked', '--manifest-path', str(prepared_manifest),
        ], cwd=scratch, cargo_home=cache_root)

        # Detect concurrent manifest edits before publishing a misleading cache.
        if dependency_fingerprint(source, manifest_path) != fingerprint:
            raise ValueError('project Cargo manifests changed during prefetch; retry')

        destination = prepared_directory(locks_root, project_id, fingerprint)
        digest = hashlib.sha256(lock.read_bytes()).hexdigest()
        if destination.exists():
            _, prior = read_prepared_lock(locks_root, project_id, fingerprint, manifest_path)
            if hashlib.sha256(prior.read_bytes()).hexdigest() != digest:
                raise ValueError('prepared Cargo.lock differs; commit a Cargo.lock for reproducibility')
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.wai-lock-', dir=destination.parent))
        try:
            target = stage / lock_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lock, target)
            (stage / 'metadata.json').write_text(json.dumps({
                'project_id': project_id,
                'manifest': manifest_path,
                'fingerprint': fingerprint,
                'lock_path': lock_relative.as_posix(),
                'sha256': digest,
            }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            os.replace(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return destination


def main() -> None:
    parser = argparse.ArgumentParser(description='Prepare offline Cargo dependencies')
    parser.add_argument('project_id')
    parser.add_argument('--manifest-path', default='Cargo.toml')
    parser.add_argument('--projects-root', type=Path, default=Path('/workspace/projects'))
    parser.add_argument('--cache-root', type=Path, default=Path('/cargo-cache'))
    parser.add_argument('--locks-root', type=Path, default=Path('/cargo-lockfiles'))
    args = parser.parse_args()
    result = prefetch(
        args.project_id, args.manifest_path,
        projects_root=args.projects_root,
        cache_root=args.cache_root,
        locks_root=args.locks_root,
    )
    print(f'Cargo dependencies prepared: {result}')


if __name__ == '__main__':
    main()
