from __future__ import annotations

from ai_workshop.mcp_runtime.transports.container import ContainerMcpTransport


class StdioMcpTransport(ContainerMcpTransport):
    """Runs stdio MCP servers inside managed MCP workloads, never on the host."""

    def __init__(
        self,
        runtime,
        *,
        image_for,
        command_for,
        client_factory,
    ):
        super().__init__(
            runtime,
            image_for=image_for,
            command_for=command_for,
            port_for=lambda registration: 8765,
            client_factory=client_factory,
            allow_internet=False,
        )
