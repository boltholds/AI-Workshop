import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.models.process import ExecRequest
from ai_workshop.workspace.paths import PathPolicy
from ai_workshop.workspace.processes import ProcessService


def make_service(root: Path) -> ProcessService:
    cfg = WorkshopConfig(projects={
        "app": ProjectMount(project_id="app", host=root, container=root.as_posix(), mode="rw")
    })
    return ProcessService(PathPolicy(cfg))


def test_exec_captures_stdout_stderr_exit_code_and_env(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    svc = make_service(root)
    req = ExecRequest(project_id="app", argv=[sys.executable, "-c", "import os,sys; print(os.getenv('HELLO')); print('err', file=sys.stderr); raise SystemExit(3)"], env={"HELLO": "world"})
    result = asyncio.run(svc.exec(req))
    assert result.exit_code == 3
    assert result.stdout.strip() == "world"
    assert result.stderr.strip() == "err"
    assert result.timed_out is False


def test_shell_rejects_unknown_project(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    with pytest.raises(KeyError, match="unknown project"):
        asyncio.run(svc.exec(ExecRequest(project_id="missing", argv=["echo", "x"])))


def test_shell_rejects_cwd_escape(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    svc = make_service(root)
    with pytest.raises(ValueError, match="escapes project root"):
        asyncio.run(svc.exec(ExecRequest(project_id="app", argv=["echo", "x"], cwd="..")))


def test_shell_timeout_terminates_child(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    svc = make_service(root)
    script = ("import subprocess,time,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(p.pid, flush=True); time.sleep(30)")
    result = asyncio.run(svc.exec(ExecRequest(project_id="app", argv=[sys.executable, "-c", script], timeout_seconds=1.0)))
    assert result.timed_out is True
    child_pid = int(result.stdout.strip().splitlines()[0])
    deadline = time.monotonic() + 1.0
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail("child process survived timeout termination")
        time.sleep(0.05)


def test_shell_can_be_cancelled(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    svc = make_service(root)

    async def scenario():
        task = asyncio.create_task(svc.exec(ExecRequest(project_id="app", argv=[sys.executable, "-c", "import time; time.sleep(30)"], timeout_seconds=10)))
        for _ in range(100):
            if svc.running_ids:
                break
            await asyncio.sleep(0.01)
        assert svc.running_ids
        run_id = next(iter(svc.running_ids))
        assert await svc.cancel(run_id) is True
        return await task

    result = asyncio.run(scenario())
    assert result.cancelled is True
