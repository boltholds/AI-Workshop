from __future__ import annotations

from typing import Any

from ai_workshop.gateway.client import WorkspaceClient
from ai_workshop.gateway.errors import WorkspaceGatewayError


def build_mcp_server(client: WorkspaceClient):
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("AI Workshop")

    async def call(coro):
        try:
            return await coro
        except WorkspaceGatewayError as exc:
            raise RuntimeError(f"{exc.code}: {exc}") from None

    @mcp.tool(name="workspace_projects")
    async def workspace_projects() -> list[dict[str, Any]]:
        """List projects explicitly mounted in AI Workshop."""
        return await call(client.projects())

    @mcp.tool(name="filesystem_list")
    async def filesystem_list(project_id: str, path: str = ".") -> list[dict[str, Any]]:
        """List files inside a configured project."""
        return await call(client.filesystem_list(project_id, path))

    @mcp.tool(name="filesystem_read")
    async def filesystem_read(project_id: str, path: str, max_bytes: int = 1_048_576) -> dict[str, Any]:
        """Read UTF-8 text from a configured project."""
        return await call(client.filesystem_read(project_id, path, max_bytes))

    @mcp.tool(name="filesystem_write")
    async def filesystem_write(project_id: str, path: str, content: str) -> dict[str, Any]:
        """Write UTF-8 text inside a writable configured project."""
        return await call(client.filesystem_write(project_id, path, content))

    @mcp.tool(name="filesystem_patch")
    async def filesystem_patch(project_id: str, path: str, expected: str, replacement: str, occurrence: int | None = None) -> dict[str, Any]:
        """Replace exact text in a configured project with optimistic matching."""
        return await call(client.filesystem_patch(project_id, path, expected, replacement, occurrence))

    @mcp.tool(name="filesystem_search")
    async def filesystem_search(project_id: str, query: str, path: str = ".") -> list[dict[str, Any]]:
        """Search UTF-8 project files recursively."""
        return await call(client.filesystem_search(project_id, query, path))

    @mcp.tool(name="shell_exec")
    async def shell_exec(project_id: str, argv: list[str] | None = None, shell: str | None = None, cwd: str = ".", env: dict[str, str] | None = None, timeout_seconds: float = 120.0) -> dict[str, Any]:
        """Execute a command inside a configured project root."""
        return await call(client.shell_exec({"project_id": project_id, "argv": argv, "shell": shell, "cwd": cwd, "env": env or {}, "timeout_seconds": timeout_seconds}))

    @mcp.tool(name="shell_cancel")
    async def shell_cancel(run_id: str) -> dict[str, Any]:
        """Cancel a running shell command by run ID."""
        return await call(client.shell_cancel(run_id))

    @mcp.tool(name="git_status")
    async def git_status(project_id: str) -> dict[str, Any]:
        """Read Git status for a configured project."""
        return await call(client.git_status(project_id))

    @mcp.tool(name="git_diff")
    async def git_diff(project_id: str, staged: bool = False) -> dict[str, Any]:
        """Read staged or unstaged Git diff for a configured project."""
        return await call(client.git_diff(project_id, staged))

    return mcp
