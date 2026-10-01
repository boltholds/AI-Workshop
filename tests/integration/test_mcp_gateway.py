import httpx

from ai_workshop.gateway.client import WorkspaceClient
from ai_workshop.gateway.errors import GatewayError, sanitize_workspace_error


def test_workspace_client_calls_private_api():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/projects":
            return httpx.Response(200, json={"projects": ["p"]})
        return httpx.Response(404)

    client = WorkspaceClient("http://workspace", token="test-token", transport=httpx.MockTransport(handler))
    assert client.projects() == ["p"]


def test_gateway_sanitizes_workspace_failure():
    response = httpx.Response(500, json={"error": {"code": "INTERNAL", "message": "Traceback: secret"}})
    error = sanitize_workspace_error(response)
    assert isinstance(error, GatewayError)
    assert error.code == "WORKSPACE_UNAVAILABLE"
    assert "Traceback" not in error.message


def test_workspace_client_sends_bearer_token():
    seen = {}

    def handler(request: httpx.Request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"projects": []})

    client = WorkspaceClient("http://workspace", token="secret", transport=httpx.MockTransport(handler))
    assert client.projects() == []
    assert seen["authorization"] == "Bearer secret"


def test_workspace_network_failure_is_sanitized():
    def handler(_request: httpx.Request):
        raise httpx.ConnectError("internal socket details")

    client = WorkspaceClient("http://workspace", token="secret", transport=httpx.MockTransport(handler))
    try:
        client.projects()
    except GatewayError as exc:
        assert exc.code == "WORKSPACE_UNAVAILABLE"
        assert "socket" not in exc.message
    else:
        raise AssertionError("expected GatewayError")
