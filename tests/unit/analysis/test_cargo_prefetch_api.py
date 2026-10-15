"""Isolated authenticated prefetch sidecar and constrained MCP client tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CalledProcessError
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_workshop.analysis.cargo_prefetch_app import create_cargo_prefetch_app
from ai_workshop.gateway.cargo_prefetch_client import CargoPrefetchClient
from ai_workshop.gateway.project_workspace_tools import register_project_workspace_tools

TOKEN = "test-cargo-prefetch-token-00000000"


def project_paths(tmp_path: Path):
    projects = tmp_path / "projects"
    source = projects / "demo"
    source.mkdir(parents=True)
    (source / "Cargo.toml").write_text('[package]\nname="demo"\nversion="0.1.0"\n')
    (source / "src").mkdir()
    (source / "src/lib.rs").write_text("pub fn answer() -> u64 {42}\n")
    cache = tmp_path / "cache"
    locks = tmp_path / "locks"
    cache.mkdir()
    locks.mkdir()
    return projects, cache, locks


def create_app(tmp_path: Path, preparer):
    projects, cache, locks = project_paths(tmp_path)
    app = create_cargo_prefetch_app(
        token=TOKEN, projects_root=projects, cache_root=cache,
        locks_root=locks, preparer=preparer,
    )
    return TestClient(app), projects


def headers():
    return {"Authorization": "Bearer " + TOKEN}


def test_prefetch_requires_token_and_never_exposes_source_paths(tmp_path):
    calls = []

    def prepare(project_id, manifest_path, **kwargs):
        calls.append((project_id, manifest_path, kwargs))
        return kwargs["locks_root"] / "prepared"

    client, projects = create_app(tmp_path, prepare)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/v1/cargo/prefetch", json={"project_id": "demo"}).status_code == 401
    assert client.post(
        "/v1/cargo/prefetch",
        headers={"Authorization": "Bearer wrong"}, json={"project_id": "demo"},
    ).status_code == 401
    response = client.post("/v1/cargo/prefetch", headers=headers(),
                           json={"project_id": "demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["prepared"] is True
    assert len(body["dependency_fingerprint"]) == 64
    assert body["project_id"] == "demo"
    assert str(tmp_path) not in response.text
    assert len(calls) == 1
    assert calls[0][2]["projects_root"] == projects
    assert not (projects / "demo" / "Cargo.lock").exists()


@pytest.mark.parametrize("bad_project, bad_manifest", [
    ("../secret", "Cargo.toml"),
    ("bad project", "Cargo.toml"),
    ("demo", "../Cargo.toml"),
    ("demo", "/tmp/Cargo.toml"),
    ("demo", ".git/Cargo.toml"),
])
def test_prefetch_rejects_project_and_manifest_escape(tmp_path, bad_project, bad_manifest):
    client, _ = create_app(tmp_path, lambda *args, **kwargs: pytest.fail("prefetch called"))
    response = client.post("/v1/cargo/prefetch", headers=headers(),
                           json={"project_id": bad_project,
                                 "manifest_path": bad_manifest})
    assert response.status_code == 400


def test_prefetch_serializes_concurrent_calls(tmp_path):
    started, release = Event(), Event()

    def prepare(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return Path("/dummy")

    client, _ = create_app(tmp_path, prepare)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, "/v1/cargo/prefetch",
                            headers=headers(), json={"project_id": "demo"})
        assert started.wait(2)
        second = client.post("/v1/cargo/prefetch",
                             headers=headers(), json={"project_id": "demo"})
        assert second.status_code == 429
        assert second.json()["error"] == "prefetch_busy"
        release.set()
        assert first.result(timeout=5).status_code == 200


def test_prefetch_errors_are_redacted_and_lock_released(tmp_path):
    attempts = []

    def prepare(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise CalledProcessError(1, ["cargo", "fetch"],
                                     stderr="secret-or-registry-url")
        return Path("/dummy")

    client, _ = create_app(tmp_path, prepare)
    first = client.post("/v1/cargo/prefetch", headers=headers(),
                        json={"project_id": "demo"})
    assert first.status_code == 502
    assert "secret-or-registry-url" not in first.text
    second = client.post("/v1/cargo/prefetch", headers=headers(),
                         json={"project_id": "demo"})
    assert second.status_code == 200


def test_empty_or_short_service_token_fails_closed(tmp_path):
    projects, cache, locks = project_paths(tmp_path)
    for token in ("", "short"):
        with pytest.raises(ValueError, match="token"):
            create_cargo_prefetch_app(
                token=token, projects_root=projects, cache_root=cache,
                locks_root=locks,
            )


def test_gateway_prefetch_client_validates_identity_and_authorization():
    def responder(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert request.url.path == "/v1/cargo/prefetch"
        assert request.method == "POST"
        assert request.read().decode().find('"project_id":"demo"') >= 0
        return httpx.Response(200, json={
            "prepared": True, "project_id": "demo", "manifest_path": "Cargo.toml",
            "dependency_fingerprint": "a" * 64,
        })

    client = CargoPrefetchClient(
        "http://cargo-prefetch-api:8796", token=TOKEN,
        transport=httpx.MockTransport(responder),
    )
    result = client.prepare("demo")
    assert result == {
        "prepared": True, "project_id": "demo", "manifest_path": "Cargo.toml",
        "dependency_fingerprint": "a" * 64,
    }


@pytest.mark.parametrize("status,message", [
    (400, "Invalid"),
    (401, "UNAUTHORIZED"),
    (429, "BUSY"),
    (502, "FAILED"),
])
def test_gateway_prefetch_client_sanitizes_errors(status, message):
    client = CargoPrefetchClient(
        "http://prefetch.internal", token=TOKEN,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, json={"error": "secret-leak-should-not-escape"}
            )
        ),
    )
    with pytest.raises((ValueError, RuntimeError), match=message) as exc:
        client.prepare("demo")
    assert "secret-leak" not in str(exc.value)


def test_gateway_prefetch_client_rejects_untrusted_response():
    client = CargoPrefetchClient(
        "http://prefetch.internal", token=TOKEN,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "prepared": True, "project_id": "other", "manifest_path": "Cargo.toml",
                "dependency_fingerprint": "a" * 64,
            })
        ),
    )
    with pytest.raises(RuntimeError, match="INVALID_RESPONSE"):
        client.prepare("demo")


def test_mcp_surface_checks_registered_project_and_avoids_shell_or_docker():
    class FakeServer:
        def __init__(self):
            self.tools = {}

        def tool(self):
            def register(fn):
                self.tools[fn.__name__] = fn
                return fn
            return register

    class FakeFiles:
        def __init__(self):
            self.lookups = []

        def _root(self, project_id):
            self.lookups.append(project_id)
            if project_id != "demo":
                raise KeyError("unregistered project")

        def read(self, *args):
            return "ok"

        def write(self, *args):
            return None

    class FakePrefetch:
        def __init__(self):
            self.calls = []

        def prepare(self, project_id, manifest_path):
            self.calls.append((project_id, manifest_path))
            return {"prepared": True}

    server, files, prefetch = FakeServer(), FakeFiles(), FakePrefetch()
    register_project_workspace_tools(
        server, files, analysis=None, cargo_prefetch_service=prefetch,
    )
    assert "cargo_prefetch" in server.tools
    assert "cargo_test" not in server.tools
    assert server.tools["cargo_prefetch"]("demo") == {"prepared": True}
    assert files.lookups == ["demo"]
    assert prefetch.calls == [("demo", "Cargo.toml")]
    with pytest.raises(RuntimeError, match="unregistered"):
        server.tools["cargo_prefetch"]("missing")
    assert prefetch.calls == [("demo", "Cargo.toml")]
