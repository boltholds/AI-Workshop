from __future__ import annotations

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

import httpx
import pytest

from ai_workshop.ingress.models import IngressRoute
from ai_workshop.ingress.proxy import ProxyAdapter
from ai_workshop.server.models import RuntimeEndpoint


class FixtureHandler(BaseHTTPRequestHandler):
    label = "fixture"

    def do_GET(self):
        body = f"{self.label}:{self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("X-Fixture", self.label)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


@contextmanager
def fixture_server(label: str):
    handler = type(
        f"{label.title()}Handler",
        (FixtureHandler,),
        {"label": label},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def route(route_id: str, hostname: str, port: int) -> IngressRoute:
    return IngressRoute(
        route_id=route_id,
        hostname=hostname,
        endpoint=RuntimeEndpoint(
            workload_id=route_id,
            host="127.0.0.1",
            host_port=port,
            container_port=8080,
        ),
    )


async def request(adapter: ProxyAdapter, hostname: str, path: str = "/"):
    transport = httpx.ASGITransport(app=adapter.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://ingress.test",
    ) as client:
        return await client.get(path, headers={"Host": hostname})


def test_proxy_routes_two_private_services_by_hostname():
    with fixture_server("one") as one_port, fixture_server("two") as two_port:
        adapter = ProxyAdapter(
            allowed_target_hosts=frozenset({"127.0.0.1"}),
        )
        adapter.apply(
            [
                route("one", "one.workshop.local", one_port),
                route("two", "two.workshop.local", two_port),
            ],
            certificates={},
        )

        one = asyncio.run(request(adapter, "one.workshop.local", "/hello?x=1"))
        two = asyncio.run(request(adapter, "two.workshop.local", "/world"))

    assert one.status_code == 200
    assert one.text == "one:/hello?x=1"
    assert one.headers["x-fixture"] == "one"
    assert "connection" not in one.headers
    assert two.text == "two:/world"


def test_proxy_apply_dynamically_unpublishes_removed_route():
    with fixture_server("one") as one_port, fixture_server("two") as two_port:
        adapter = ProxyAdapter(
            allowed_target_hosts=frozenset({"127.0.0.1"}),
        )
        one_route = route("one", "one.workshop.local", one_port)
        two_route = route("two", "two.workshop.local", two_port)
        adapter.apply([one_route, two_route], certificates={})
        assert asyncio.run(request(adapter, "one.workshop.local")).status_code == 200

        adapter.apply([two_route], certificates={})

        missing = asyncio.run(request(adapter, "one.workshop.local"))
        remaining = asyncio.run(request(adapter, "two.workshop.local"))

    assert missing.status_code == 421
    assert remaining.status_code == 200


def test_proxy_rejects_target_host_outside_infrastructure_allowlist():
    adapter = ProxyAdapter()
    unsafe = IngressRoute(
        route_id="unsafe",
        hostname="unsafe.workshop.local",
        endpoint=RuntimeEndpoint(
            workload_id="unsafe",
            host="169.254.169.254",
            host_port=80,
            container_port=8080,
        ),
    )

    with pytest.raises(ValueError, match="target host"):
        adapter.apply([unsafe], certificates={})


def test_proxy_rejects_duplicate_hostname_even_if_registry_is_bypassed():
    with fixture_server("one") as one_port, fixture_server("two") as two_port:
        adapter = ProxyAdapter(
            allowed_target_hosts=frozenset({"127.0.0.1"}),
        )
        first = route("one", "same.workshop.local", one_port)
        second = route("two", "same.workshop.local", two_port)

        with pytest.raises(ValueError, match="duplicate hostname"):
            adapter.apply([first, second], certificates={})


def test_unknown_hostname_returns_misdirected_request():
    adapter = ProxyAdapter(
        allowed_target_hosts=frozenset({"127.0.0.1"}),
    )
    adapter.apply([], certificates={})

    response = asyncio.run(request(adapter, "unknown.workshop.local"))

    assert response.status_code == 421


class FakeIngressAuthenticator:
    def __init__(self):
        self.calls = []

    def authenticate(self, token: str, *, required_scope: str | None):
        self.calls.append((token, required_scope))
        if token != "valid-token":
            raise PermissionError("invalid token")
        if required_scope not in {None, "mcp.call"}:
            raise PermissionError("scope denied")
        return "principal-service"


def test_authenticated_route_rejects_missing_bearer_token(monkeypatch):
    from fastapi.testclient import TestClient
    from ai_workshop.ingress.models import IngressAuthPolicy

    adapter = ProxyAdapter(
        authenticator=FakeIngressAuthenticator(),
    )
    route = route_for("protected", "workshop.local", 41010).model_copy(
        update={
            "auth_policy": IngressAuthPolicy.AUTHENTICATED,
            "required_scope": "mcp.call",
        }
    )
    adapter.apply([route], {})

    response = TestClient(adapter.app).get(
        "/mcp",
        headers={"host": "workshop.local"},
    )

    assert response.status_code == 401


def test_authenticated_route_forwards_verified_principal_and_strips_spoofed_header(
    monkeypatch,
):
    from fastapi.testclient import TestClient
    from ai_workshop.ingress.models import IngressAuthPolicy

    captured = {}

    async def fake_request(self, method, target, headers, content):
        captured["headers"] = dict(headers)
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    authenticator = FakeIngressAuthenticator()
    adapter = ProxyAdapter(authenticator=authenticator)
    route = route_for("protected", "workshop.local", 41010).model_copy(
        update={
            "auth_policy": IngressAuthPolicy.AUTHENTICATED,
            "required_scope": "mcp.call",
        }
    )
    adapter.apply([route], {})

    response = TestClient(adapter.app).get(
        "/mcp",
        headers={
            "host": "workshop.local",
            "authorization": "Bearer valid-token",
            "x-workshop-principal-id": "spoofed",
        },
    )

    assert response.status_code == 200
    assert authenticator.calls == [("valid-token", "mcp.call")]
    assert captured["headers"]["x-workshop-principal-id"] == "principal-service"
    assert "authorization" not in captured["headers"]


def test_public_route_does_not_require_authenticator(monkeypatch):
    from fastapi.testclient import TestClient

    async def fake_request(self, method, target, headers, content):
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    adapter = ProxyAdapter()
    adapter.apply([route_for("public", "app.workshop.local", 41011)], {})

    response = TestClient(adapter.app).get(
        "/",
        headers={"host": "app.workshop.local"},
    )

    assert response.status_code == 200
