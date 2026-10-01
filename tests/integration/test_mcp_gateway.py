import asyncio
import importlib.util

import httpx
import pytest

from ai_workshop.gateway.client import WorkspaceClient
from ai_workshop.gateway.errors import WorkspaceGatewayError


def test_gateway_sanitizes_workspace_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": "INTERNAL_ERROR", "message": "internal error"}})

    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://workspace") as http:
            client = WorkspaceClient("http://workspace", http=http)
            with pytest.raises(WorkspaceGatewayError) as exc:
                await client.filesystem_read("app", "x.txt")
            assert exc.value.code == "INTERNAL_ERROR"
            assert str(exc.value) == "internal error"
            assert "Traceback" not in str(exc.value)

    asyncio.run(scenario())


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="mcp v2 SDK unavailable in execution sandbox")
def test_mcp_server_registers_expected_tools() -> None:
    from ai_workshop.gateway.server import build_mcp_server
    from ai_workshop.gateway.client import WorkspaceClient

    server = build_mcp_server(WorkspaceClient("http://127.0.0.1:8766"))
    assert server is not None
