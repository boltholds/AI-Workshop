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
