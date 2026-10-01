import asyncio
from pathlib import Path

import pytest

from ai_workshop.controller.registry import RegisteredService, ServiceRegistry
from ai_workshop.controller.runner import CommandResult, ComposeController
from ai_workshop.gateway.server import build_server
from ai_workshop.gateway.service_tools import register_service_tools


class CapturingExecutor:
    def __init__(self):
        self.calls = []

    def run(self, argv, *, cwd, timeout_seconds):
        self.calls.append((argv, cwd, timeout_seconds))
        return CommandResult(exit_code=0, stdout="ok", stderr="")


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


def controller(tmp_path: Path):
    compose = tmp_path / "compose.services.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    registry = ServiceRegistry([
        RegisteredService(
            service_id="web",
            compose_project="workshop-dev",
            working_dir=tmp_path,
            compose_files=(compose,),
            compose_service="web",
            allowed_operations=frozenset({"status", "logs", "restart", "rebuild", "up"}),
        )
    ], profiles={"dev": frozenset({"web"})})
    executor = CapturingExecutor()
    return ComposeController(registry, executor=executor), executor


def test_mcp_server_registers_service_tools_when_controller_is_configured(tmp_path: Path):
    ctl, _ = controller(tmp_path)
    server = build_server(
        "http://127.0.0.1:8766",
        token="workspace-token",
        service_controller=ctl,
    )
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {
        "services_list", "services_status", "services_logs",
        "services_restart", "services_rebuild", "services_up",
    } <= names


def test_service_list_can_filter_by_profile(tmp_path: Path):
    ctl, _ = controller(tmp_path)
    server = FakeServer()
    register_service_tools(server, ctl)
    assert server.tools["services_list"]("dev") == ["web"]


def test_service_tools_do_not_expose_compose_paths_or_cli_fragments(tmp_path: Path):
    ctl, executor = controller(tmp_path)
    server = FakeServer()
    register_service_tools(server, ctl)

    with pytest.raises(RuntimeError, match="unregistered service"):
        server.tools["services_restart"]("--project-directory=/")

    assert executor.calls == []
    assert set(server.tools["services_restart"].__annotations__) <= {"service_id", "return"}


def test_service_restart_is_scoped_to_requested_service(tmp_path: Path):
    ctl, executor = controller(tmp_path)
    server = FakeServer()
    register_service_tools(server, ctl)
    server.tools["services_restart"]("web")
    argv = executor.calls[-1][0]
    assert argv[-2:] == ["restart", "web"]
    assert "browser" not in argv
    assert "database" not in argv
