import httpx
from ai_workshop.gateway.browser_client import BrowserClient

def test_browser_client_fetches_screenshot_and_artifact_bytes():
    def handler(request):
        if request.url.path=="/v1/screenshot":
            return httpx.Response(200,json={"artifact":{"id":"s1","media_type":"image/png","path":"s1/screenshot.png","width":100,"height":50}})
        if request.url.path=="/v1/artifacts/s1/screenshot.png": return httpx.Response(200,content=b"PNGDATA")
        return httpx.Response(404)
    client=BrowserClient("http://browser",transport=httpx.MockTransport(handler))
    artifact=client.screenshot({"kind":"page","full_page":False})
    assert client.artifact_bytes(artifact)==b"PNGDATA"

def test_browser_client_diagnostics_preserves_artifact_list():
    def handler(request):
        if request.url.path=="/v1/diagnostics":
            return httpx.Response(200,json={"session_id":"r1","artifacts":[{"id":"r1","media_type":"video/webm","path":"r1/recording.webm"},{"id":"r1","media_type":"image/png","path":"r1/composite-neutral.png"},{"id":"r1","media_type":"application/json","path":"r1/metadata.json"}]})
        return httpx.Response(404)
    result=BrowserClient("http://browser",transport=httpx.MockTransport(handler)).capture_diagnostics("r1",variants="neutral")
    assert [a["media_type"] for a in result["artifacts"]]==["video/webm","image/png","application/json"]
