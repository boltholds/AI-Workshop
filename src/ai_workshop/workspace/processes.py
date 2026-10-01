from __future__ import annotations

import asyncio
import os
import re
import signal
import sys
from uuid import UUID, uuid4

from ai_workshop.models.process import ExecRequest, ExecResult
from ai_workshop.workspace.paths import PathPolicy

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ProcessService:
    def __init__(self, paths: PathPolicy) -> None:
        self._paths = paths
        self._running: dict[UUID, asyncio.subprocess.Process] = {}
        self._cancel_requested: set[UUID] = set()

    @property
    def running_ids(self) -> frozenset[UUID]:
        return frozenset(self._running)

    async def exec(self, request: ExecRequest) -> ExecResult:
        cwd = self._paths.resolve(request.project_id, request.cwd)
        if not cwd.exists() or not cwd.is_dir():
            raise ValueError(f"working directory does not exist: {request.cwd}")
        env = os.environ.copy()
        for key, value in request.env.items():
            if not _ENV_NAME.fullmatch(key):
                raise ValueError(f"invalid environment variable name: {key}")
            env[key] = value

        run_id = uuid4()
        kwargs: dict[str, object] = {
            "cwd": str(cwd),
            "env": env,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if sys.platform == "win32":
            import subprocess
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True

        if request.argv is not None:
            proc = await asyncio.create_subprocess_exec(*request.argv, **kwargs)
        else:
            proc = await asyncio.create_subprocess_shell(request.shell or "", **kwargs)

        self._running[run_id] = proc
        communicate = asyncio.create_task(proc.communicate())
        timed_out = False
        try:
            try:
                stdout_b, stderr_b = await asyncio.wait_for(asyncio.shield(communicate), request.timeout_seconds)
            except TimeoutError:
                timed_out = True
                await self._terminate_process_tree(proc)
                stdout_b, stderr_b = await communicate
            cancelled = run_id in self._cancel_requested
            return ExecResult(
                run_id=run_id,
                exit_code=proc.returncode,
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
                timed_out=timed_out,
                cancelled=cancelled,
            )
        finally:
            self._running.pop(run_id, None)
            self._cancel_requested.discard(run_id)

    async def cancel(self, run_id: UUID) -> bool:
        proc = self._running.get(run_id)
        if proc is None:
            return False
        self._cancel_requested.add(run_id)
        await self._terminate_process_tree(proc)
        return True

    async def _terminate_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=0.5)
        except (ProcessLookupError, TimeoutError):
            if proc.returncode is None:
                try:
                    if sys.platform == "win32":
                        proc.kill()
                    else:
                        os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
