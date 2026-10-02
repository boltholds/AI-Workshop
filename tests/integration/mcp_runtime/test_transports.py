from __future__ import annotations

import socket

import pytest

from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.transports.container import ContainerMcpTransport
from ai_workshop.mcp_runtime.transports.http import McpHttpEndpointPolicy
from ai_workshop.server.models import RuntimeWorkloadKind


def registration(kind=McpTransportKind.CONTAINER):
    return McpRegistration(
        server_id="mcp-demo",
        display_name="Demo",
        transport=kind,
        scope=McpRegistrationScope.PROJECT,
        scope_id="demo",
        owner_principal_id="alice",
    )


def test_http_transport_rejects_protected_endpoint(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))
        ],
    )

    with pytest.raises(ValueError, match="protected"):
        McpHttpEndpointPolicy().validate("http://metadata.example/mcp")


class FakeRuntime:
    def __init__(self):
        self.created = None
        self.started = []
        self.stopped = []
        self.removed = []

    def ensure_image(self, image):
        self.image = image

    def create(self, spec):
        self.created = spec

    def start(self, workload_id):
        self.started.append(workload_id)

    def publish_private_endpoint(self, workload_id, port):
        return (workload_id, port)

    def stop(self, workload_id):
        self.stopped.append(workload_id)

    def remove(self, workload_id):
        self.removed.append(workload_id)


class Handle:
    def close(self):
        self.closed = True


def test_container_transport_uses_mcp_runtime_kind_and_no_socket_mount():
    runtime = FakeRuntime()
    transport = ContainerMcpTransport(
        runtime,
        image_for=lambda _: "example/mcp:1",
        command_for=lambda _: ("serve",),
        port_for=lambda _: 8765,
        client_factory=lambda endpoint: Handle(),
    )

    transport.start(registration())

    assert runtime.created.kind is RuntimeWorkloadKind.MCP
    assert runtime.created.mounts == ()
    assert runtime.created.privileged is False
    assert runtime.created.devices == ()
    assert runtime.created.container_ports == (8765,)
