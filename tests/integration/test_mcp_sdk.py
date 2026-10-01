from ai_workshop.gateway.server import build_server


def test_mcp_v2_server_builds_with_registered_tools():
    server = build_server("http://127.0.0.1:8766")
    assert server is not None
