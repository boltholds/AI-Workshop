from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Protocol

from ai_workshop.server.models import RuntimeEndpoint, RuntimeWorkloadStatus, RuntimeWorkloadState


class RuntimeEndpointRegistry(Protocol):
    def allocate(self, workload_id: str, container_port: int) -> RuntimeEndpoint: ...

    def require(self, workload_id: str, container_port: int) -> RuntimeEndpoint: ...

    def release(self, workload_id: str) -> None: ...


class PrivateEndpointRegistry:
    def __init__(
        self,
        *,
        host: str,
        start_port: int,
        end_port: int,
        state_path: Path,
    ):
        RuntimeEndpoint(
            workload_id="validation",
            host=host,
            host_port=start_port,
            container_port=1,
        )
        if end_port < start_port or end_port > 65535:
            raise ValueError("invalid private endpoint port range")
        self.host = host
        self.start_port = start_port
        self.end_port = end_port
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._allocations: dict[tuple[str, int], RuntimeEndpoint] = {}
        self._load()

    def allocate(self, workload_id: str, container_port: int) -> RuntimeEndpoint:
        self._validate_key(workload_id, container_port)
        key = (workload_id, container_port)
        with self._lock:
            existing = self._allocations.get(key)
            if existing is not None:
                return existing

            used = {endpoint.host_port for endpoint in self._allocations.values()}
            host_port = next(
                (
                    port
                    for port in range(self.start_port, self.end_port + 1)
                    if port not in used
                ),
                None,
            )
            if host_port is None:
                raise RuntimeError("private endpoint port pool exhausted")

            endpoint = RuntimeEndpoint(
                workload_id=workload_id,
                host=self.host,
                host_port=host_port,
                container_port=container_port,
            )
            self._allocations[key] = endpoint
            self._persist()
            return endpoint

    def require(self, workload_id: str, container_port: int) -> RuntimeEndpoint:
        self._validate_key(workload_id, container_port)
        with self._lock:
            endpoint = self._allocations.get((workload_id, container_port))
            if endpoint is None:
                raise KeyError(
                    f"private endpoint not allocated: {workload_id}:{container_port}"
                )
            return endpoint

    def release(self, workload_id: str) -> None:
        self._validate_workload_id(workload_id)
        with self._lock:
            keys = [
                key for key in self._allocations
                if key[0] == workload_id
            ]
            if not keys:
                return
            for key in keys:
                self._allocations.pop(key)
            self._persist()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported private endpoint registry version")
        for item in payload.get("allocations", []):
            endpoint = RuntimeEndpoint.model_validate(
                {**item, "host": self.host}
            )
            if not (self.start_port <= endpoint.host_port <= self.end_port):
                raise ValueError("persisted endpoint is outside configured port range")
            key = (endpoint.workload_id, endpoint.container_port)
            if key in self._allocations:
                raise ValueError("duplicate persisted endpoint allocation")
            self._allocations[key] = endpoint
        host_ports = [item.host_port for item in self._allocations.values()]
        if len(host_ports) != len(set(host_ports)):
            raise ValueError("duplicate persisted private host port")

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "allocations": [
                {
                    "workload_id": endpoint.workload_id,
                    "host_port": endpoint.host_port,
                    "container_port": endpoint.container_port,
                }
                for endpoint in sorted(
                    self._allocations.values(),
                    key=lambda item: (item.workload_id, item.container_port),
                )
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    @staticmethod
    def _validate_workload_id(workload_id: str) -> None:
        RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.UNKNOWN,
        )

    @classmethod
    def _validate_key(cls, workload_id: str, container_port: int) -> None:
        cls._validate_workload_id(workload_id)
        RuntimeEndpoint(
            workload_id=workload_id,
            host="validation",
            host_port=1,
            container_port=container_port,
        )
