from __future__ import annotations

import os
import signal
import subprocess
import threading
from uuid import UUID

from ai_workshop.models.process import ExecRequest, ExecResult
from ai_workshop.workspace.paths import PathPolicy


class ProcessService:
    def __init__(self, policy: PathPolicy):
        self.policy = policy
        self._active: dict[UUID, subprocess.Popen[str]] = {}
        self._cancelled: set[UUID] = set()
        self._lock = threading.Lock()

    def active_run_ids(self) -> list[UUID]:
        with self._lock:
            return list(self._active)

    def cancel(self, run_id: UUID) -> bool:
        with self._lock:
            proc = self._active.get(run_id)
            if proc is None:
                return False
            self._cancelled.add(run_id)
        self._terminate_process_group(proc)
        return True

    def exec(self, request: ExecRequest, *, allow_read_only: bool = False) -> ExecResult:
        if not allow_read_only:
            self.policy.require_writable(request.project_id)
        cwd = self.policy.resolve(request.project_id, request.cwd)
        env = os.environ.copy()
        env.update(request.env)
        env.pop("AI_WORKSHOP_WORKSPACE_TOKEN", None)
        proc = subprocess.Popen(
            request.argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        with self._lock:
            self._active[request.run_id] = proc
        timed_out = False
        try:
            try:
                stdout, stderr = proc.communicate(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate_process_group(proc)
                stdout, stderr = proc.communicate()
            with self._lock:
                cancelled = request.run_id in self._cancelled
            return ExecResult(
                run_id=request.run_id,
                exit_code=None if timed_out or cancelled else proc.returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                cancelled=cancelled,
            )
        finally:
            with self._lock:
                self._active.pop(request.run_id, None)
                self._cancelled.discard(request.run_id)

    @staticmethod
    def _terminate_process_group(proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=0.5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
