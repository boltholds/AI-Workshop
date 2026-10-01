from pathlib import Path
from threading import Thread
import time

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.models.process import ExecRequest
from ai_workshop.workspace.paths import PathPolicy
from ai_workshop.workspace.processes import ProcessService


def service(root: Path) -> ProcessService:
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=root, container="/workspace/p", mode="rw")])
    return ProcessService(PathPolicy(cfg, host_paths=True))


def test_exec_captures_output_and_exit_code(tmp_path: Path):
    result = service(tmp_path).exec(ExecRequest(project_id="p", argv=["python", "-c", 'import sys; print("ok"); print("bad", file=sys.stderr); sys.exit(3)']))
    assert result.exit_code == 3
    assert result.stdout.strip() == "ok"
    assert result.stderr.strip() == "bad"


def test_shell_rejects_unknown_project(tmp_path: Path):
    with pytest.raises(KeyError, match="unknown"):
        service(tmp_path).exec(ExecRequest(project_id="unknown", argv=["python", "-c", "print(1)"]))


def test_exec_uses_project_cwd(tmp_path: Path):
    result = service(tmp_path).exec(ExecRequest(project_id="p", argv=["python", "-c", "import os; print(os.getcwd())"]))
    assert Path(result.stdout.strip()) == tmp_path.resolve()


def test_exec_allows_explicit_env_additions(tmp_path: Path):
    result = service(tmp_path).exec(ExecRequest(project_id="p", argv=["python", "-c", 'import os; print(os.environ["HELLO"])'], env={"HELLO": "world"}))
    assert result.stdout.strip() == "world"


def test_shell_timeout_terminates_child(tmp_path: Path):
    result = service(tmp_path).exec(ExecRequest(project_id="p", argv=["python", "-c", "import time; time.sleep(5)"], timeout_seconds=0.1))
    assert result.timed_out is True
    assert result.exit_code is None


def test_explicit_cancel(tmp_path: Path):
    svc = service(tmp_path)
    box = {}
    req = ExecRequest(project_id="p", argv=["python", "-c", "import time; time.sleep(5)"], timeout_seconds=10)
    thread = Thread(target=lambda: box.setdefault("result", svc.exec(req)))
    thread.start()
    deadline = time.time() + 2
    run_id = None
    while time.time() < deadline:
        ids = svc.active_run_ids()
        if ids:
            run_id = ids[0]
            break
        time.sleep(0.01)
    assert run_id is not None
    assert svc.cancel(run_id) is True
    thread.join(timeout=2)
    assert box["result"].cancelled is True


def test_exec_uses_relative_cwd(tmp_path: Path):
    (tmp_path / "frontend").mkdir()
    result = service(tmp_path).exec(
        ExecRequest(project_id="p", cwd="frontend", argv=["python", "-c", "import os; print(os.getcwd())"])
    )
    assert Path(result.stdout.strip()) == (tmp_path / "frontend").resolve()


def test_exec_rejects_cwd_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="outside project root"):
        service(tmp_path).exec(
            ExecRequest(project_id="p", cwd="../escape", argv=["python", "-c", "print(1)"])
        )


def test_shell_rejects_read_only_project(tmp_path: Path):
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=tmp_path, container="/workspace/p", mode="ro")])
    svc = ProcessService(PathPolicy(cfg, host_paths=True))
    with pytest.raises(PermissionError, match="read-only"):
        svc.exec(ExecRequest(project_id="p", argv=["python", "-c", "from pathlib import Path; Path('x.txt').write_text('oops')"]))
    assert not (tmp_path / "x.txt").exists()


def test_shell_does_not_inherit_workspace_control_token(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_WORKSHOP_WORKSPACE_TOKEN", "super-secret-control-token")
    result = service(tmp_path).exec(
        ExecRequest(
            project_id="p",
            argv=["python", "-c", 'import os; print(os.environ.get("AI_WORKSHOP_WORKSPACE_TOKEN", "missing"))'],
        )
    )
    assert result.stdout.strip() == "missing"
