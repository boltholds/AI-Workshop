import httpx
import pytest

from ai_workshop.gateway.browser_client import BrowserClient
from ai_workshop.gateway.errors import GatewayError


def test_browser_client_fetches_screenshot_and_artifact_bytes():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/screenshot":
            return httpx.Response(200,json={"artifact":{"id":"s1","media_type":"image/png","path":"s1/screenshot.png","width":100,"height":50}})
        if request.url.path == "/v1/artifacts/s1/screenshot.png":
            return httpx.Response(200,content=b"PNGDATA",headers={"content-type":"image/png"})
        return httpx.Response(404)
    client=BrowserClient("http://browser",token="test-token",transport=httpx.MockTransport(handler))
    artifact=client.screenshot({"kind":"page","full_page":False})
    assert artifact["path"] == "s1/screenshot.png"
    assert client.artifact_bytes(artifact) == b"PNGDATA"


def test_browser_client_diagnostics_preserves_artifact_list():
    def handler(request: httpx.Request):
        if request.url.path == "/v1/diagnostics":
            return httpx.Response(200,json={"session_id":"r1","artifacts":[
                {"id":"r1","media_type":"video/webm","path":"r1/recording.webm"},
                {"id":"r1","media_type":"image/png","path":"r1/composite-neutral.png","width":10,"height":10},
                {"id":"r1","media_type":"application/json","path":"r1/metadata.json"},
            ]})
        return httpx.Response(404)
    client=BrowserClient("http://browser",token="test-token",transport=httpx.MockTransport(handler))
    result=client.capture_diagnostics("r1",variants="neutral")
    assert [a["media_type"] for a in result["artifacts"]] == ["video/webm","image/png","application/json"]


def test_browser_client_sends_bearer_token():
    seen={}
    def handler(request: httpx.Request):
        seen["auth"]=request.headers.get("authorization")
        return httpx.Response(200,json={"events":[]})
    client=BrowserClient("http://browser",token="secret",transport=httpx.MockTransport(handler))
    assert client.console_events() == []
    assert seen["auth"] == "Bearer secret"


def test_browser_client_sanitizes_network_failure():
    def handler(_request):
        raise httpx.ConnectError("socket secret")
    client=BrowserClient("http://browser",token="secret",transport=httpx.MockTransport(handler))
    try:
        client.console_events()
    except GatewayError as exc:
        assert exc.code == "BROWSER_UNAVAILABLE"
        assert "socket" not in exc.message
    else:
        raise AssertionError("expected GatewayError")


def test_browser_client_sanitizes_http_failure_without_workspace_label():
    def handler(_request):
        return httpx.Response(500,json={"detail":"Traceback: browser secret"})
    client=BrowserClient("http://browser",token="secret",transport=httpx.MockTransport(handler))
    try:
        client.console_events()
    except GatewayError as exc:
        assert exc.code == "BROWSER_UNAVAILABLE"
        assert "Traceback" not in exc.message
        assert "Workspace" not in exc.message
    else:
        raise AssertionError("expected GatewayError")


def test_browser_client_sanitizes_malformed_success_response():
    def handler(_request: httpx.Request):
        return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})
    client=BrowserClient("http://browser",token="secret",transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayError) as exc_info:
        client.console_events()
    assert exc_info.value.code == "BROWSER_PROTOCOL_ERROR"


def test_browser_client_sanitizes_missing_response_field():
    def handler(_request: httpx.Request):
        return httpx.Response(200, json={"unexpected": []})
    client=BrowserClient("http://browser",token="secret",transport=httpx.MockTransport(handler))
    with pytest.raises(GatewayError) as exc_info:
        client.console_events()
    assert exc_info.value.code == "BROWSER_PROTOCOL_ERROR"
