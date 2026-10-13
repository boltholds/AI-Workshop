from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from uuid import uuid4

from ai_workshop.analysis.project_files import resolve_relative


_PROJECT_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
_ANALYSIS_ID = re.compile(r'^[0-9a-f]{32}$')
_MAX_OUTPUT = 262_144
_ALLOWED_FLAGS = {
    'file': {'-b', '--brief'},
    'readelf': {'-h', '-S', '-s', '-r', '-W', '--dyn-syms'},
    'objdump': {'-p', '-x', '-t', '-d', '-C'},
    'nm': {'-D', '-g', '-C', '-n'},
    'strings': {'-a'},
    'sha256sum': set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisEngine:
    """Worker-side inspection of read-only registered project checkouts."""

    def __init__(
        self,
        *,
        projects_root: Path,
        results_root: Path,
        ghidra_home: Path = Path('/opt/ghidra'),
        script_path: Path = Path('/opt/ai-workshop/ghidra_scripts'),
    ):
        self.projects_root = Path(projects_root).resolve(strict=True)
        self.results_root = Path(results_root).resolve(strict=True)
        self.ghidra_home = Path(ghidra_home)
        self.script_path = Path(script_path)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ghidra')
        self._jobs: set[str] = set()

    def project_root(self, project_id: str) -> Path:
        if not _PROJECT_ID.fullmatch(project_id):
            raise ValueError('invalid project id')
        root = (self.projects_root / project_id).resolve(strict=False)
        if not root.is_relative_to(self.projects_root) or not root.is_dir():
            raise ValueError('unknown or unavailable project')
        return root

    def binary_path(self, project_id: str, path: str) -> Path:
        target = resolve_relative(self.project_root(project_id), path)
        if not target.is_file():
            raise ValueError('file does not exist')
        return target

    def _run(
        self, argv: list[str], *, cwd: Path,
        timeout_seconds: float, abort_on_output_limit: bool = True,
    ) -> dict[str, object]:
        if not 1 <= timeout_seconds <= 900:
            raise ValueError('timeout must be between 1 and 900 seconds')
        env = {
            'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
            'HOME': '/tmp',
            'TMPDIR': '/tmp',
            'LANG': 'C.UTF-8',
            'CARGO_HOME': '/tmp/wai-cargo',
            'RUSTUP_HOME': '/usr/local/rustup',
            'CARGO_NET_OFFLINE': 'true',
            'GIT_TERMINAL_PROMPT': '0',
        }
        exe = shutil.which(argv[0], path=env['PATH']) if not argv[0].startswith('/') else argv[0]
        if not exe or not Path(exe).is_file():
            raise ValueError('requested tool is not installed')
        proc = subprocess.Popen(
            [exe, *argv[1:]], cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        output = bytearray()
        truncated = False
        timed_out = False
        started = time.monotonic()
        selector = selectors.DefaultSelector()
        assert proc.stdout is not None
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                if time.monotonic() - started > timeout_seconds:
                    timed_out = True
                    break
                ready = selector.select(timeout=0.2)
                for key, _ in ready:
                    block = os.read(key.fd, 8192)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    remain = _MAX_OUTPUT - len(output)
                    output.extend(block[:max(remain, 0)])
                    if len(block) > remain:
                        truncated = True
                        if abort_on_output_limit:
                            break
                if truncated and abort_on_output_limit:
                    break
        finally:
            selector.close()
            if timed_out or truncated and abort_on_output_limit or proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait(timeout=5)
            proc.stdout.close()
        return {
            'exit_code': proc.returncode,
            'stdout': output.decode('utf-8', errors='replace'),
            'timed_out': timed_out,
            'truncated': truncated,
        }

    def shell_exec(
        self, project_id: str, argv: list[str], timeout_seconds: float = 30,
    ) -> dict[str, object]:
        if not isinstance(argv, list) or len(argv) < 2 or len(argv) > 32:
            raise ValueError('expected command, options and project-relative file path')
        command, *raw = argv
        if command not in _ALLOWED_FLAGS:
            raise ValueError('command is not in the read-only binary inspection allowlist')
        options, files = [], []
        for part in raw:
            if (not isinstance(part, str) or not part or len(part) > 512
                    or any(ord(c) < 32 for c in part)):
                raise ValueError('invalid argument')
            if part.startswith('-'):
                if part not in _ALLOWED_FLAGS[command]:
                    raise ValueError('unsupported option')
                options.append(part)
            else:
                files.append(str(self.binary_path(project_id, part)))
        if not files:
            raise ValueError('at least one project-relative file path is required')
        return self._run(
            [command, *options, *files],
            cwd=self.project_root(project_id), timeout_seconds=timeout_seconds,
        )

    def cargo_test(
        self, project_id: str, manifest_path: str = 'Cargo.toml',
        timeout_seconds: float = 300,
    ) -> dict[str, object]:
        if Path(manifest_path).name != 'Cargo.toml':
            raise ValueError('manifest must be named Cargo.toml')
        manifest = self.binary_path(project_id, manifest_path)
        with tempfile.TemporaryDirectory(prefix='wai-target-') as target:
            return self._run(
                ['cargo', 'test', '--offline', '--locked',
                 '--manifest-path', str(manifest), '--target-dir', target],
                cwd=self.project_root(project_id), timeout_seconds=timeout_seconds,
            )

    def _result_dir(self, project_id: str, analysis_id: str) -> Path:
        self.project_root(project_id)
        if not _ANALYSIS_ID.fullmatch(analysis_id):
            raise ValueError('invalid analysis id')
        dest = (self.results_root / project_id / analysis_id).resolve(strict=False)
        if not dest.is_relative_to(self.results_root):
            raise ValueError('analysis path escapes results storage')
        return dest

    @staticmethod
    def _persist_status(folder: Path, payload: dict[str, object]) -> None:
        path = folder / 'status.json'
        temp = folder / 'status.json.tmp'
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
        temp.replace(path)

    def binary_analyze(self, project_id: str, path: str) -> dict[str, object]:
        binary = self.binary_path(project_id, path)
        if binary.suffix.lower() not in ('.dll', '.exe', '.ocx', '.sys'):
            raise ValueError('only PE executable images are supported')
        with binary.open('rb') as stream:
            header = stream.read(64)
            if len(header) < 64 or header[:2] != b'MZ':
                raise ValueError('not a Windows PE image')
            pe_offset = int.from_bytes(header[0x3c:0x40], 'little')
            if pe_offset < 64 or pe_offset > 1_048_576:
                raise ValueError('invalid PE header offset')
            stream.seek(pe_offset)
            if stream.read(4) != b'PE\x00\x00':
                raise ValueError('not a Windows PE image')
        headless = self.ghidra_home / 'support' / 'analyzeHeadless'
        script = self.script_path / 'ExportSummary.py'
        if not headless.is_file() or not script.is_file():
            raise ValueError('Ghidra headless or ExportSummary.py is not installed')
        with binary.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        analysis_id = uuid4().hex
        folder = self._result_dir(project_id, analysis_id)
        folder.mkdir(parents=True, exist_ok=False)
        metadata = {
            'analysis_id': analysis_id, 'project_id': project_id,
            'binary_path': path, 'sha256': sha,
            'status': 'queued', 'updated_at': _now(),
        }
        self._persist_status(folder, metadata)
        self._jobs.add(analysis_id)
        self._executor.submit(self._analyze, binary, folder, metadata)
        return metadata

    def _analyze(
        self, binary: Path, folder: Path, meta: dict[str, object],
    ) -> None:
        analysis_id = str(meta['analysis_id'])
        try:
            meta = {**meta, 'status': 'running', 'updated_at': _now()}
            self._persist_status(folder, meta)
            with tempfile.TemporaryDirectory(prefix='wai-ghidra-') as scratch:
                result = self._run([
                    str(self.ghidra_home / 'support' / 'analyzeHeadless'),
                    scratch, 'WAIAnalysis', '-import', str(binary),
                    '-scriptPath', str(self.script_path),
                    '-postScript', 'ExportSummary.py', str(folder / 'summary.json'),
                    '-analysisTimeoutPerFile', '600', '-deleteProject',
                ], cwd=self.project_root(str(meta['project_id'])),
                   timeout_seconds=720, abort_on_output_limit=False)
            (folder / 'headless.log').write_text(
                str(result['stdout'])[-_MAX_OUTPUT:], encoding='utf-8',
            )
            success = result['exit_code'] == 0 and (folder / 'summary.json').is_file()
            meta = {
                **meta, 'status': 'completed' if success else 'failed',
                'exit_code': result['exit_code'],
                'timed_out': result['timed_out'],
                'truncated': result['truncated'],
                'updated_at': _now(),
            }
            self._persist_status(folder, meta)
        except Exception:
            self._persist_status(
                folder, {**meta, 'status': 'failed',
                         'error': 'analysis worker failed', 'updated_at': _now()},
            )
        finally:
            self._jobs.discard(analysis_id)

    def analysis_get_results(
        self, project_id: str, analysis_id: str,
    ) -> dict[str, object]:
        folder = self._result_dir(project_id, analysis_id)
        status_path = folder / 'status.json'
        if not status_path.is_file():
            raise ValueError('analysis not found')
        meta = json.loads(status_path.read_text(encoding='utf-8'))
        if meta.get('status') in ('queued', 'running') and analysis_id not in self._jobs:
            meta = {**meta, 'status': 'interrupted'}
        path = folder / 'summary.json'
        if meta['status'] == 'completed' and path.is_file():
            if path.stat().st_size > 8_388_608:
                raise ValueError('analysis result is too large')
            meta['summary'] = json.loads(path.read_text(encoding='utf-8'))
        return meta
