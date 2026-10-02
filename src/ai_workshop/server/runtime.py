from __future__ import annotations

from typing import Protocol

DEFAULT_RUNTIME_SOCKET = "/run/ai-workshop-runtime/1000/docker.sock"


from ai_workshop.server.models import (
    RuntimeEndpoint,
    RuntimeWorkloadSpec,
    RuntimeWorkloadStatus,
)


class RuntimeController(Protocol):
    def ensure_image(self, image: str) -> None: ...

    def create(self, spec: RuntimeWorkloadSpec) -> RuntimeWorkloadStatus: ...

    def start(self, workload_id: str) -> RuntimeWorkloadStatus: ...

    def stop(self, workload_id: str) -> RuntimeWorkloadStatus: ...

    def remove(self, workload_id: str) -> None: ...

    def status(self, workload_id: str) -> RuntimeWorkloadStatus: ...

    def logs(self, workload_id: str, *, tail: int = 200) -> str: ...

    def publish_private_endpoint(
        self,
        workload_id: str,
        container_port: int,
    ) -> RuntimeEndpoint: ...
