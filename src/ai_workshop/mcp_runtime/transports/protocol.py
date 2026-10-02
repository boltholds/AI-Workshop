from __future__ import annotations

from typing import Mapping, Protocol

from ai_workshop.mcp_runtime.models import McpRegistration


class McpTransportHandle(Protocol):
    server_id: str

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> dict[str, object]: ...

    def list_tools(self) -> list[dict[str, object]]: ...
    def list_resources(self) -> list[dict[str, object]]: ...
    def list_prompts(self) -> list[dict[str, object]]: ...
    def read_resource(self, uri: str) -> dict[str, object]: ...
    def get_prompt(
        self,
        name: str,
        arguments: Mapping[str, str],
    ) -> dict[str, object]: ...
    def close(self) -> None: ...


class McpTransport(Protocol):
    def start(self, registration: McpRegistration) -> McpTransportHandle: ...
    def stop(self, server_id: str) -> None: ...
