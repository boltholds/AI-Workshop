from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from ai_workshop.mcp_runtime.discovery import McpDiscoveryService
from ai_workshop.mcp_runtime.lifecycle import RunScopedMcpCleaner
from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.proxy import McpProxyService
from ai_workshop.mcp_runtime.registry import McpRegistryStore
from ai_workshop.projects.store import ProjectStore
from ai_workshop.runs.workspaces import RunWorkspaceManager
from ai_workshop.server.storage import ServerStorage


class TinyMcp:
    def __init__(self):
        self.closed = False

    def list_tools(self):
        return [{"name": "echo"}]

    def list_resources(self):
        return []

    def list_prompts(self):
        return []

    def call_tool(self, name, arguments):
        return {"echo": arguments["value"]}

    def read_resource(self, uri):
        raise KeyError(uri)

    def get_prompt(self, name, arguments):
        raise KeyError(name)

    def close(self):
        self.closed = True


class Clients:
    def __init__(self, handle):
        self.handle = handle

    def client_for(self, server_id):
        return self.handle


class Transports:
    def __init__(self, handle):
        self.handle = handle
        self.stopped = []

    def stop(self, server_id):
        self.stopped.append(server_id)
        self.handle.close()


def git(cwd: Path, *args: str):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_full_server_mode_parallel_runs_dynamic_mcp_and_host_isolation(tmp_path):
    outside = tmp_path / "outside-host-file.txt"
    outside.write_text("protected")
    outside_hash = hashlib.sha256(outside.read_bytes()).hexdigest()

    storage = ServerStorage(tmp_path / "server-storage")
    projects = ProjectStore(
        storage=storage,
        state_path=tmp_path / "projects.json",
    )
    project = projects.register_git(
        "demo",
        remote_url="https://example.invalid/demo.git",
    )
    project.path.mkdir(parents=True, exist_ok=True)
    git(project.path, "init")
    git(project.path, "config", "user.email", "e2e@example.invalid")
    git(project.path, "config", "user.name", "Server E2E")
    (project.path / "app.py").write_text("VALUE = 1\n")
    git(project.path, "add", ".")
    git(project.path, "commit", "-m", "initial")

    workspaces = RunWorkspaceManager(projects, storage)
    run_a = workspaces.create("demo", "run-a", "HEAD", True)
    run_b = workspaces.create("demo", "run-b", "HEAD", True)

    assert run_a.path != run_b.path
    (run_a.path / "app.py").write_text("VALUE = 2\n")
    assert (run_b.path / "app.py").read_text() == "VALUE = 1\n"
    assert (project.path / "app.py").read_text() == "VALUE = 1\n"

    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(
        McpRegistration(
            server_id="run-a-tools",
            display_name="Run A tools",
            transport=McpTransportKind.CONTAINER,
            scope=McpRegistrationScope.RUN,
            scope_id="run-a",
            owner_principal_id="agent-a",
            state=McpServerState.RUNNING,
        )
    )
    handle = TinyMcp()
    clients = Clients(handle)
    McpDiscoveryService(registry, clients).refresh("run-a-tools")
    result = McpProxyService(registry, clients).tool_call(
        "agent-a",
        "run-a-tools",
        "echo",
        {"value": "hot-plugged"},
    )
    assert result == {"echo": "hot-plugged"}

    cleaner = RunScopedMcpCleaner(registry, Transports(handle))
    cleaner.cleanup_run("run-a")
    assert registry.list() == []

    workspaces.remove("run-a")
    workspaces.remove("run-b")

    assert hashlib.sha256(outside.read_bytes()).hexdigest() == outside_hash


def test_server_e2e_does_not_touch_unmounted_host_file(tmp_path):
    outside = tmp_path / "not-mounted.txt"
    outside.write_text("unchanged")
    before = outside.read_bytes()

    storage = ServerStorage(tmp_path / "owned")
    storage.project_root("demo").joinpath("inside.txt").write_text("changed")

    assert outside.read_bytes() == before
