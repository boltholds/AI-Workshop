from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ai_workshop.server.models import (
    RuntimeNetworkNamespace,
    RuntimePidNamespace,
    RuntimeWorkloadKind,
    RuntimeWorkloadSpec,
)
from ai_workshop.server.runtime import DEFAULT_RUNTIME_SOCKET
from ai_workshop.server.storage import ServerStorage


class RuntimeWorkloadPolicy(Protocol):
    def validate(self, spec: RuntimeWorkloadSpec) -> None: ...


class RuntimePolicy:
    def __init__(self, storage: ServerStorage):
        self.storage = storage

    def validate(self, spec: RuntimeWorkloadSpec) -> None:
        if spec.privileged:
            raise ValueError("privileged runtime workloads are not allowed")
        if spec.pid_namespace is RuntimePidNamespace.HOST:
            raise ValueError("host PID namespace is not allowed")
        if spec.network_namespace is RuntimeNetworkNamespace.HOST:
            raise ValueError("host network namespace is not allowed")
        if spec.devices:
            raise ValueError("device mappings are not allowed")

        if len(set(spec.container_ports)) != len(spec.container_ports):
            raise ValueError("duplicate container port declaration")

        runtime_socket = Path(DEFAULT_RUNTIME_SOCKET).resolve(strict=False)
        storage_root = self.storage.root.resolve()
        assigned_root = (
            storage_root
            if spec.kind is RuntimeWorkloadKind.INFRASTRUCTURE
            else self.storage.run_root(spec.workload_id).resolve()
        )
        for mount in spec.mounts:
            source = mount.source.resolve(strict=False)
            if source == runtime_socket:
                raise ValueError("runtime socket cannot be mounted into nested workload")
            try:
                source.relative_to(storage_root)
            except ValueError as exc:
                raise ValueError("runtime mount source must stay inside server storage") from exc
            try:
                source.relative_to(assigned_root)
            except ValueError as exc:
                raise ValueError(
                    "runtime mount source must stay inside assigned workload storage"
                ) from exc
