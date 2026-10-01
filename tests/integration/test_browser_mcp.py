import asyncio

from ai_workshop.gateway.server import build_server


def test_mcp_server_registers_browser_tools():
    server=build_server(
        "http://127.0.0.1:8766",
        token="workspace-token",
        browser_url="http://127.0.0.1:8767",
        browser_token="browser-token",
    )
    names={tool.name for tool in asyncio.run(server.list_tools())}
    assert {
        "browser_navigate","browser_screenshot","browser_record_start",
        "browser_record_stop","browser_capture_diagnostics"
    } <= names
