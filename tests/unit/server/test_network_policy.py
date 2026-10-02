from __future__ import annotations

import inspect

import pytest

from ai_workshop.server.models import (
    RuntimeOutboundAccess,
    RuntimeWorkloadKind,
    RuntimeWorkloadSpec,
)
from ai_workshop.server.network import (
    NetworkGrantPurpose,
    RuntimeNetworkPolicy,
)


def test_agent_run_never_receives_control_plane_or_rootless_network():
    policy = RuntimeNetworkPolicy(
        allowed_outbound_kinds=frozenset({RuntimeWorkloadKind.AGENT_RUN}),
    )
    spec = RuntimeWorkloadSpec(
        workload_id="run-1",
        image="python:3.12-slim",
        kind=RuntimeWorkloadKind.AGENT_RUN,
    )

    grants = policy.allowed_networks(spec)

    names = {grant.network_name for grant in grants}
    assert "ai-workshop-control-plane" not in names
    assert "ai-workshop-rootless-control" not in names


def test_mcp_runtime_never_receives_control_plane_or_rootless_network():
    policy = RuntimeNetworkPolicy()
    spec = RuntimeWorkloadSpec(
        workload_id="mcp-1",
        image="example/mcp:latest",
        kind=RuntimeWorkloadKind.MCP,
    )

    grants = policy.allowed_networks(spec)

    names = {grant.network_name for grant in grants}
    assert "ai-workshop-control-plane" not in names
    assert "ai-workshop-rootless-control" not in names


def test_outbound_access_can_be_restricted_by_deployment_policy():
    policy = RuntimeNetworkPolicy(
        allowed_outbound_kinds=frozenset({RuntimeWorkloadKind.AGENT_RUN}),
    )

    agent_grants = policy.allowed_networks(
        RuntimeWorkloadSpec(
            workload_id="run-1",
            image="python:3.12-slim",
            kind=RuntimeWorkloadKind.AGENT_RUN,
            outbound=RuntimeOutboundAccess.INTERNET,
        )
    )
    assert any(
        grant.purpose is NetworkGrantPurpose.EGRESS
        for grant in agent_grants
    )

    with pytest.raises(ValueError, match="outbound"):
        policy.allowed_networks(
            RuntimeWorkloadSpec(
                workload_id="mcp-1",
                image="example/mcp:latest",
                kind=RuntimeWorkloadKind.MCP,
                outbound=RuntimeOutboundAccess.INTERNET,
            )
        )


def test_project_service_is_private_until_endpoint_publication():
    policy = RuntimeNetworkPolicy()
    spec = RuntimeWorkloadSpec(
        workload_id="service-1",
        image="nginx:latest",
        kind=RuntimeWorkloadKind.PROJECT_SERVICE,
        container_ports=(8080,),
    )

    grants = policy.allowed_networks(spec)

    assert all(
        grant.purpose is not NetworkGrantPurpose.INGRESS
        for grant in grants
    )


def test_runtime_workload_spec_has_no_raw_docker_network_name_input():
    forbidden = {
        "network",
        "networks",
        "network_name",
        "network_names",
        "docker_network",
    }
    assert forbidden.isdisjoint(RuntimeWorkloadSpec.model_fields)


def test_runtime_network_policy_api_accepts_workload_not_network_names():
    parameters = inspect.signature(
        RuntimeNetworkPolicy.allowed_networks
    ).parameters
    assert list(parameters) == ["self", "workload"]


def test_private_network_grant_is_internal_and_egress_is_not():
    policy = RuntimeNetworkPolicy(
        allowed_outbound_kinds=frozenset({RuntimeWorkloadKind.AGENT_RUN}),
    )
    grants = policy.allowed_networks(
        RuntimeWorkloadSpec(
            workload_id="run-1",
            image="python:3.12-slim",
            kind=RuntimeWorkloadKind.AGENT_RUN,
            outbound=RuntimeOutboundAccess.INTERNET,
        )
    )

    private = next(item for item in grants if item.purpose is NetworkGrantPurpose.PRIVATE)
    egress = next(item for item in grants if item.purpose is NetworkGrantPurpose.EGRESS)
    assert private.internal is True
    assert egress.internal is False
