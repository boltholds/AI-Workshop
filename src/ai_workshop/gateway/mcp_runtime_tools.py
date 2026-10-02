from __future__ import annotations


def register_mcp_runtime_tools(server, proxy, principal_resolver) -> None:
    def actor() -> str:
        principal_id = principal_resolver.current_principal_id()
        if not principal_id:
            raise RuntimeError("AUTHENTICATION_REQUIRED")
        return principal_id

    def safe(callable_, *args, **kwargs):
        try:
            return callable_(*args, **kwargs)
        except (KeyError, ValueError, PermissionError) as exc:
            raise RuntimeError(str(exc).strip("'")) from None
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError(
                "MCP_RUNTIME_OPERATION_FAILED: downstream MCP operation failed"
            ) from None

    @server.tool(name="mcp.servers_list")
    def mcp_servers_list() -> list[dict[str, object]]:
        return [
            item.model_dump(mode="json")
            for item in safe(proxy.servers_list, actor())
        ]

    @server.tool(name="mcp.server_get")
    def mcp_server_get(server_id: str) -> dict[str, object]:
        return safe(proxy.server_get, actor(), server_id).model_dump(mode="json")

    @server.tool(name="mcp.tools_list")
    def mcp_tools_list(server_id: str) -> list[dict[str, object]]:
        return [
            item.model_dump(mode="json")
            for item in safe(proxy.tools_list, actor(), server_id)
        ]

    @server.tool(name="mcp.tool_call")
    def mcp_tool_call(
        server_id: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        return safe(
            proxy.tool_call,
            actor(),
            server_id,
            tool_name,
            arguments,
        )

    @server.tool(name="mcp.resources_list")
    def mcp_resources_list(server_id: str) -> list[dict[str, object]]:
        return [
            item.model_dump(mode="json")
            for item in safe(proxy.resources_list, actor(), server_id)
        ]

    @server.tool(name="mcp.resource_read")
    def mcp_resource_read(server_id: str, uri: str) -> dict[str, object]:
        return safe(proxy.resource_read, actor(), server_id, uri)

    @server.tool(name="mcp.prompts_list")
    def mcp_prompts_list(server_id: str) -> list[dict[str, object]]:
        return [
            item.model_dump(mode="json")
            for item in safe(proxy.prompts_list, actor(), server_id)
        ]

    @server.tool(name="mcp.prompt_get")
    def mcp_prompt_get(
        server_id: str,
        prompt_name: str,
        arguments: dict[str, str],
    ) -> dict[str, object]:
        return safe(
            proxy.prompt_get,
            actor(),
            server_id,
            prompt_name,
            arguments,
        )
