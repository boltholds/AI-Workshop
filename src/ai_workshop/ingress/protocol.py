from __future__ import annotations

from typing import Protocol

from ai_workshop.ingress.models import IngressRoute
from ai_workshop.server.models import RuntimeEndpoint


class RuntimeEndpointAuthority(Protocol):
    def require(
        self,
        workload_id: str,
        container_port: int,
    ) -> RuntimeEndpoint: ...


class IngressService(Protocol):
    def publish(
        self,
        route_id: str,
        *,
        hostname: str,
        endpoint: RuntimeEndpoint,
    ) -> IngressRoute: ...

    def unpublish(self, route_id: str) -> None: ...

    def get(self, route_id: str) -> IngressRoute: ...

    def list(self) -> list[IngressRoute]: ...
