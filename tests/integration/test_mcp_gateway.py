import httpx

from ai_workshop.gateway.client import WorkspaceClient
from ai_workshop.gateway.errors import GatewayError, sanitize_workspace_error


def test_workspace_client_calls_private_api():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/projects":
            return httpx.Response(200, json={"projects": ["p"]})
        return httpx.Response(404)

    client = WorkspaceClient("http://workspace", transport=httpx.MockTransport(handler))
    assert client.projects() == ["p"]


def test_gateway_sanitizes_workspace_failure():
    response = httpx.Response(500, json={"error": {"code": "INTERNAL", "message": "Traceback: secret"}})
    error = sanitize_workspace_error(response)
    assert isinstance(error, GatewayError)
    assert error.code == "WORKSPACE_UNAVAILABLE"
    assert "Traceback" not in error.message
