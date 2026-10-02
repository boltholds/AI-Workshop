from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from ai_workshop.server.endpoints import PrivateEndpointRegistry


def registry(tmp_path: Path) -> PrivateEndpointRegistry:
    return PrivateEndpointRegistry(
        host="rootless-runtime",
        start_port=41000,
        end_port=41002,
        state_path=tmp_path / "endpoints.json",
    )


def test_private_endpoint_uses_configured_internal_host(tmp_path: Path):
    endpoints = registry(tmp_path)

    endpoint = endpoints.allocate("service-1", 8080)

    assert endpoint.host == "rootless-runtime"
    assert endpoint.host_port == 41000
    assert endpoint.container_port == 8080


def test_private_endpoint_ports_are_unique_and_not_caller_selected(tmp_path: Path):
    endpoints = registry(tmp_path)

    first = endpoints.allocate("service-1", 8080)
    second = endpoints.allocate("service-2", 8080)

    assert first.host_port != second.host_port
    assert "host_port" not in inspect.signature(endpoints.allocate).parameters


def test_endpoint_allocation_is_idempotent_for_same_workload_port(tmp_path: Path):
    endpoints = registry(tmp_path)

    first = endpoints.allocate("service-1", 8080)
    second = endpoints.allocate("service-1", 8080)

    assert first == second


def test_endpoint_registry_persists_allocations_across_instances(tmp_path: Path):
    state = tmp_path / "endpoints.json"
    first_registry = PrivateEndpointRegistry(
        host="rootless-runtime",
        start_port=41000,
        end_port=41002,
        state_path=state,
    )
    allocated = first_registry.allocate("service-1", 8080)

    second_registry = PrivateEndpointRegistry(
        host="rootless-runtime",
        start_port=41000,
        end_port=41002,
        state_path=state,
    )

    assert second_registry.require("service-1", 8080) == allocated


def test_release_removes_all_workload_endpoints(tmp_path: Path):
    endpoints = registry(tmp_path)
    endpoints.allocate("service-1", 8080)
    endpoints.allocate("service-1", 8081)

    endpoints.release("service-1")

    with pytest.raises(KeyError):
        endpoints.require("service-1", 8080)
    with pytest.raises(KeyError):
        endpoints.require("service-1", 8081)


def test_endpoint_pool_exhaustion_is_explicit(tmp_path: Path):
    endpoints = PrivateEndpointRegistry(
        host="rootless-runtime",
        start_port=41000,
        end_port=41000,
        state_path=tmp_path / "endpoints.json",
    )
    endpoints.allocate("service-1", 8080)

    with pytest.raises(RuntimeError, match="exhausted"):
        endpoints.allocate("service-2", 8080)
