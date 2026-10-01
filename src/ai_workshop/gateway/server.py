from __future__ import annotations

from ai_workshop.gateway.client import WorkspaceClient
from ai_workshop.gateway.errors import GatewayError


def build_server(workspace_url: str, *, token: str):
    from mcp.server.mcpserver import MCPServer

    client = WorkspaceClient(workspace_url, token=token)
    server = MCPServer("AI Workshop")

    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except GatewayError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from None

    @server.tool()
    def workspace_projects() -> list[str]:
        return safe(client.projects)

    @server.tool()
    def filesystem_list(project_id: str, path: str = ".") -> list[str]:
        return safe(client.file_list, project_id, path)

    @server.tool()
    def filesystem_read(project_id: str, path: str) -> str:
        return safe(client.file_read, project_id, path)

    @server.tool()
    def filesystem_write(project_id: str, path: str, content: str) -> dict[str, bool]:
        safe(client.file_write, project_id, path, content)
        return {"ok": True}

    @server.tool()
    def filesystem_patch(project_id: str, path: str, old: str, new: str, occurrence: int | None = None) -> dict[str, bool]:
        safe(client.file_patch, project_id, path, old, new, occurrence)
        return {"ok": True}

    @server.tool()
    def filesystem_search(project_id: str, needle: str, path: str = ".") -> list[dict[str, object]]:
        return safe(client.file_search, project_id, needle, path)

    @server.tool()
    def shell_exec(project_id: str, argv: list[str], cwd: str = ".", env: dict[str, str] | None = None, timeout_seconds: float = 60.0) -> dict[str, object]:
        return safe(client.shell_exec, project_id, argv, cwd=cwd, env=env, timeout_seconds=timeout_seconds)

    @server.tool()
    def shell_cancel(run_id: str) -> bool:
        return safe(client.shell_cancel, run_id)

    @server.tool()
    def git_status(project_id: str) -> str:
        return safe(client.git_status, project_id)

    @server.tool()
    def git_diff(project_id: str, staged: bool = False) -> str:
        return safe(client.git_diff, project_id, staged=staged)

    return server


def run_gateway(workspace_url: str, *, token: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = build_server(workspace_url, token=token)
    server.run(
        transport="streamable-http",
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
    )
