from pathlib import Path

from fastapi.testclient import TestClient

from ai_workshop.browser.app import create_browser_app
from ai_workshop.browser.models import ArtifactRef


class FakeWorker:
    def __init__(self):
        self.calls=[]; self.started=False; self.stopped=False
    def start(self): self.started=True
    def stop(self): self.stopped=True
    def call(self, method, *args, **kwargs):
        self.calls.append((method,args,kwargs))
        if method == "navigate": return "https://example.test/"
        if method == "screenshot": return ArtifactRef(id="s1",media_type="image/png",path="s1/screenshot.png",width=800,height=600)
        if method == "recording_start": return "rec1"
        if method == "console_events": return [{"text":"hello"}]
        if method == "network_events": return [{"url":"https://example.test"}]
        return None


def test_browser_api_routes_commands_through_worker(tmp_path: Path):
    worker=FakeWorker()
    app=create_browser_app(tmp_path/"profile",tmp_path/"artifacts",worker=worker,browser_token="test-token")
    with TestClient(app, headers={"Authorization":"Bearer test-token"}) as client:
        assert client.get("/health").json() == {"status":"ok"}
        assert client.post("/v1/navigate",json={"url":"https://example.test"}).json()["url"].endswith("/")
        shot=client.post("/v1/screenshot",json={"region":{"kind":"page","full_page":False}}).json()["artifact"]
        assert shot["media_type"] == "image/png"
        assert client.post("/v1/record/start",json={"region":{"kind":"page"}}).json()["session_id"] == "rec1"
        assert client.get("/v1/console").json()["events"][0]["text"] == "hello"
    assert worker.started and worker.stopped


def test_artifact_endpoint_cannot_escape_root(tmp_path: Path):
    worker=FakeWorker(); root=tmp_path/"artifacts"; root.mkdir()
    app=create_browser_app(tmp_path/"profile",root,worker=worker,browser_token="test-token")
    with TestClient(app, headers={"Authorization":"Bearer test-token"}) as client:
        response=client.get("/v1/artifacts/..%2F../secret.txt/x")
        assert response.status_code in {400,404}


def test_browser_api_requires_token(tmp_path: Path):
    worker=FakeWorker()
    app=create_browser_app(tmp_path/"profile",tmp_path/"artifacts",worker=worker,browser_token="secret")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response=client.get("/v1/console")
        assert response.status_code == 401
        assert response.json() == {"error":{"code":"UNAUTHORIZED","message":"Valid browser token required"}}
