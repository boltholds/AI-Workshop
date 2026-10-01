from pathlib import Path
import subprocess

import pytest

from ai_workshop.controller.registry import RegisteredService, ServiceRegistry
from ai_workshop.controller.runner import CommandResult, ComposeController, ControllerError


class CapturingExecutor:
    def __init__(self):
        self.calls = []
        self.raise_timeout = False

    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> CommandResult:
        self.calls.append((argv, cwd, timeout_seconds))
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(argv, timeout_seconds)
        return CommandResult(exit_code=0, stdout="ok", stderr="")


def controller(tmp_path: Path):
    compose = tmp_path / "compose.services.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    service = RegisteredService(
        service_id="web",
        compose_project="workshop-dev",
        working_dir=tmp_path,
        compose_files=(compose,),
        compose_service="web",
        allowed_operations=frozenset({"status", "logs", "restart", "rebuild", "up"}),
    )
    executor = CapturingExecutor()
    return ComposeController(ServiceRegistry([service]), executor=executor), executor


def test_restart_uses_fixed_compose_argv(tmp_path: Path):
    ctl, executor = controller(tmp_path)
    ctl.restart("web")
    argv, cwd, _ = executor.calls[-1]
    assert argv == [
        "docker", "compose", "-p", "workshop-dev",
        "-f", str((tmp_path / "compose.services.yaml").resolve()),
        "restart", "web",
    ]
    assert cwd == tmp_path.resolve()


def test_rejects_caller_cli_fragments(tmp_path: Path):
    ctl, executor = controller(tmp_path)
    with pytest.raises(KeyError, match="unregistered service"):
        ctl.restart("--project-directory=/")
    assert executor.calls == []


def test_logs_tail_is_bounded(tmp_path: Path):
    ctl, executor = controller(tmp_path)
    with pytest.raises(ValueError, match="tail"):
        ctl.logs("web", tail=0)
    with pytest.raises(ValueError, match="tail"):
        ctl.logs("web", tail=1001)
    ctl.logs("web", tail=100)
    assert executor.calls[-1][0][-4:] == ["logs", "--no-color", "--tail", "100", "web"][-4:]


def test_timeout_maps_to_structured_controller_error(tmp_path: Path):
    ctl, executor = controller(tmp_path)
    executor.raise_timeout = True
    with pytest.raises(ControllerError) as exc_info:
        ctl.status("web")
    assert exc_info.value.code == "COMMAND_TIMEOUT"
    assert "docker" not in exc_info.value.message.lower()
