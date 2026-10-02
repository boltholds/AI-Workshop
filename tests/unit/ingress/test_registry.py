from __future__ import annotations

from pathlib import Path

import pytest

from ai_workshop.ingress.registry import IngressRouteRegistry
from ai_workshop.server.models import RuntimeEndpoint


class FakeEndpointAuthority:
    def __init__(self, endpoints: tuple[RuntimeEndpoint, ...]):
        self.endpoints = {
            (item.workload_id, item.container_port): item
            for item in endpoints
        }

    def require(
        self,
        workload_id: str,
        container_port: int,
    ) -> RuntimeEndpoint:
        endpoint = self.endpoints.get((workload_id, container_port))
        if endpoint is None:
            raise KeyError("endpoint not issued")
        return endpoint


def issued_endpoint(
    workload_id: str = "service-one",
    *,
    host_port: int = 41001,
    container_port: int = 8080,
) -> RuntimeEndpoint:
    return RuntimeEndpoint(
        workload_id=workload_id,
        host="rootless-runtime",
        host_port=host_port,
        container_port=container_port,
    )


def registry(tmp_path: Path, *endpoints: RuntimeEndpoint) -> IngressRouteRegistry:
    return IngressRouteRegistry(
        endpoint_authority=FakeEndpointAuthority(tuple(endpoints)),
        state_path=tmp_path / "ingress-routes.json",
    )


def test_publish_get_list_and_unpublish_round_trip(tmp_path: Path):
    endpoint = issued_endpoint()
    routes = registry(tmp_path, endpoint)

    route = routes.publish(
        "app",
        hostname="app.workshop.local",
        endpoint=endpoint,
    )

    assert route.route_id == "app"
    assert route.hostname == "app.workshop.local"
    assert route.endpoint == endpoint
    assert routes.get("app") == route
    assert routes.list() == [route]

    routes.unpublish("app")
    with pytest.raises(KeyError, match="unknown ingress route"):
        routes.get("app")


def test_hostname_is_normalized_to_lowercase(tmp_path: Path):
    endpoint = issued_endpoint()
    routes = registry(tmp_path, endpoint)

    route = routes.publish(
        "app",
        hostname="App.Workshop.Local",
        endpoint=endpoint,
    )

    assert route.hostname == "app.workshop.local"


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "127.0.0.1",
        "::1",
        "app.workshop.local:8443",
        "https://app.workshop.local",
        "app_workshop.local",
        "*.workshop.local",
        "-app.workshop.local",
        "app-.workshop.local",
        "app..workshop.local",
    ],
)
def test_invalid_hostname_is_rejected(tmp_path: Path, hostname: str):
    endpoint = issued_endpoint()
    routes = registry(tmp_path, endpoint)

    with pytest.raises(ValueError, match="hostname"):
        routes.publish("app", hostname=hostname, endpoint=endpoint)


def test_duplicate_hostname_rejected(tmp_path: Path):
    first = issued_endpoint("service-one", host_port=41001)
    second = issued_endpoint("service-two", host_port=41002)
    routes = registry(tmp_path, first, second)
    routes.publish("first", hostname="app.workshop.local", endpoint=first)

    with pytest.raises(ValueError, match="hostname already published"):
        routes.publish(
            "second",
            hostname="APP.WORKSHOP.LOCAL",
            endpoint=second,
        )


def test_duplicate_route_id_rejected(tmp_path: Path):
    first = issued_endpoint("service-one", host_port=41001)
    second = issued_endpoint("service-two", host_port=41002)
    routes = registry(tmp_path, first, second)
    routes.publish("app", hostname="app.workshop.local", endpoint=first)

    with pytest.raises(ValueError, match="route already exists"):
        routes.publish(
            "app",
            hostname="other.workshop.local",
            endpoint=second,
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        RuntimeEndpoint(
            workload_id="service-one",
            host="127.0.0.1",
            host_port=41001,
            container_port=8080,
        ),
        RuntimeEndpoint(
            workload_id="service-one",
            host="169.254.169.254",
            host_port=80,
            container_port=8080,
        ),
        RuntimeEndpoint(
            workload_id="service-one",
            host="192.168.1.10",
            host_port=41001,
            container_port=8080,
        ),
        RuntimeEndpoint(
            workload_id="not-issued",
            host="rootless-runtime",
            host_port=41099,
            container_port=8080,
        ),
    ],
)
def test_route_target_must_be_controller_endpoint(
    tmp_path: Path,
    endpoint: RuntimeEndpoint,
):
    issued = issued_endpoint()
    routes = registry(tmp_path, issued)

    with pytest.raises(ValueError, match="controller-issued"):
        routes.publish(
            "app",
            hostname="app.workshop.local",
            endpoint=endpoint,
        )


def test_route_target_rejects_tampered_host_port(tmp_path: Path):
    issued = issued_endpoint()
    routes = registry(tmp_path, issued)
    tampered = issued.model_copy(update={"host_port": 41999})

    with pytest.raises(ValueError, match="controller-issued"):
        routes.publish(
            "app",
            hostname="app.workshop.local",
            endpoint=tampered,
        )


def test_registry_persists_routes_and_revalidates_endpoint_authority(tmp_path: Path):
    endpoint = issued_endpoint()
    state_path = tmp_path / "ingress-routes.json"
    authority = FakeEndpointAuthority((endpoint,))
    routes = IngressRouteRegistry(
        endpoint_authority=authority,
        state_path=state_path,
    )
    routes.publish("app", hostname="app.workshop.local", endpoint=endpoint)

    reloaded = IngressRouteRegistry(
        endpoint_authority=authority,
        state_path=state_path,
    )
    assert reloaded.get("app").endpoint == endpoint

    with pytest.raises(ValueError, match="controller-issued"):
        IngressRouteRegistry(
            endpoint_authority=FakeEndpointAuthority(()),
            state_path=state_path,
        )
