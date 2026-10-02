from __future__ import annotations

import asyncio
from pathlib import Path

from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.gateway import build_server_gateway_runtime


def test_server_gateway_exposes_server_native_project_and_git_tools(tmp_path: Path):
    config = ServerModeConfig(storage_root=tmp_path / "storage")
    runtime = build_server_gateway_runtime(
        config,
        state_root=tmp_path / "state",
    )

    tools = asyncio.run(runtime.server.list_tools())
    names = {tool.name for tool in tools}

    assert "projects_list" in names
    assert "projects_get" in names
    assert "git_clone" in names
    assert "git_status" in names
    assert "git_diff" in names
    assert "git_commit" in names
    assert "git_hard_reset_preview" in names
    assert "git_hard_reset_prepare" in names
    assert "git_hard_reset" in names

    assert "workspace_projects" not in names
    assert "filesystem_write" not in names
    assert "shell_exec" not in names
