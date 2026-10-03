from __future__ import annotations

from ai_workshop.gateway.client import WorkspaceClient
from ai_workshop.gateway.errors import GatewayError


def build_server(
    workspace_url: str | None,
    *,
    token: str | None,
    browser_url: str | None = None,
    browser_token: str | None = None,
    service_controller=None,
    state_snapshot_service=None,
    reset_service=None,
    server_recovery_registry=None,
    project_service=None,
    git_service=None,
    git_destructive_service=None,
    credential_service=None,
    agent_service=None,
    run_service=None,
    authorization_service=None,
    principal_resolver=None,
    mcp_proxy_service=None,
    mcp_promotion_registry=None,
):
    from mcp.server.mcpserver import MCPServer

    client = (
        WorkspaceClient(workspace_url, token=token)
        if workspace_url is not None and token is not None
        else None
    )
    server = MCPServer("AI Workshop")

    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except GatewayError as exc:
            raise RuntimeError(f"{exc.code}: {exc.message}") from None

    if client is not None:
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

    if git_service is None and client is not None:
        @server.tool()
        def git_status(project_id: str) -> str:
            return safe(client.git_status, project_id)

        @server.tool()
        def git_diff(project_id: str, staged: bool = False) -> str:
            return safe(client.git_diff, project_id, staged=staged)
    elif git_service is not None:
        from ai_workshop.gateway.git_tools import register_git_tools

        register_git_tools(
            server,
            git_service,
            destructive=git_destructive_service,
        )

    if project_service is not None:
        from ai_workshop.gateway.project_tools import register_project_tools

        register_project_tools(server, project_service)

    if credential_service is not None:
        from ai_workshop.gateway.credential_tools import register_credential_tools

        register_credential_tools(server, credential_service)

    if agent_service is not None or run_service is not None:
        if authorization_service is None or principal_resolver is None:
            raise ValueError(
                "authorization service and principal resolver are required "
                "for agent/run tools"
            )

    if agent_service is not None:
        from ai_workshop.gateway.agent_tools import register_agent_tools

        register_agent_tools(
            server,
            agent_service,
            authorization_service,
            principal_resolver,
        )

    if run_service is not None:
        from ai_workshop.gateway.run_tools import register_run_tools

        register_run_tools(
            server,
            run_service,
            authorization_service,
            principal_resolver,
        )

    if mcp_proxy_service is not None:
        if principal_resolver is None:
            raise ValueError(
                "principal resolver is required for dynamic MCP tools"
            )
        from ai_workshop.gateway.mcp_runtime_tools import register_mcp_runtime_tools
        register_mcp_runtime_tools(
            server,
            mcp_proxy_service,
            principal_resolver,
            promotion_registry=mcp_promotion_registry,
        )

    from ai_workshop.gateway.recovery_tools import register_recovery_tools
    register_recovery_tools(
        server,
        client,
        state_service=state_snapshot_service,
        reset_service=reset_service,
        server_recovery_registry=server_recovery_registry,
    )

    if service_controller is not None:
        from ai_workshop.gateway.service_tools import register_service_tools

        register_service_tools(server, service_controller)

    if browser_url:
        from ai_workshop.gateway.browser_client import BrowserClient
        from ai_workshop.gateway.browser_tools import register_browser_tools

        if not browser_token:
            raise ValueError("browser token is required when browser_url is configured")
        register_browser_tools(server, BrowserClient(browser_url, token=browser_token))

    return server


def run_gateway(
    workspace_url: str | None,
    *,
    token: str | None,
    host: str = "127.0.0.1",
    port: int = 8765,
    browser_url: str | None = None,
    browser_token: str | None = None,
    service_controller=None,
    state_snapshot_service=None,
    reset_service=None,
    server_recovery_registry=None,
    project_service=None,
    git_service=None,
    git_destructive_service=None,
    credential_service=None,
    agent_service=None,
    run_service=None,
    authorization_service=None,
    principal_resolver=None,
    mcp_proxy_service=None,
    mcp_promotion_registry=None,
) -> None:
    server = build_server(
        workspace_url,
        token=token,
        browser_url=browser_url,
        browser_token=browser_token,
        service_controller=service_controller,
        state_snapshot_service=state_snapshot_service,
        reset_service=reset_service,
        server_recovery_registry=server_recovery_registry,
        project_service=project_service,
        git_service=git_service,
        git_destructive_service=git_destructive_service,
        credential_service=credential_service,
        agent_service=agent_service,
        run_service=run_service,
        authorization_service=authorization_service,
        principal_resolver=principal_resolver,
        mcp_proxy_service=mcp_proxy_service,
        mcp_promotion_registry=mcp_promotion_registry,
    )
    server.run(
        transport="streamable-http",
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
    )
