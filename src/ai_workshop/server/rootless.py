from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Protocol

from ai_workshop.server.endpoints import RuntimeEndpointRegistry
from ai_workshop.server.models import (
    RuntimeEndpoint,
    RuntimeWorkloadSpec,
    RuntimeWorkloadState,
    RuntimeWorkloadStatus,
)


DEFAULT_RUNTIME_SOCKET = "/run/ai-workshop-runtime/docker.sock"


@dataclass(frozen=True, slots=True)
class RuntimeCommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class RuntimeControllerError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class RuntimeExecutor(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        timeout_seconds: float,
    ) -> RuntimeCommandResult: ...


class SubprocessRuntimeExecutor:
    def run(
        self,
        argv: list[str],
        *,
        timeout_seconds: float,
    ) -> RuntimeCommandResult:
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeControllerError(
                "RUNTIME_TIMEOUT",
                "Runtime operation timed out",
            ) from exc
        return RuntimeCommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class RootlessDockerController:
    def __init__(
        self,
        *,
        policy: RuntimeWorkloadPolicy,
        network_policy: RuntimeNetworkPolicyProtocol,
        endpoint_registry: RuntimeEndpointRegistry,
        executor: RuntimeExecutor | None = None,
        timeout_seconds: float = 60.0,
    ):
        self.policy = policy
        self.network_policy = network_policy
        self.endpoint_registry = endpoint_registry
        self.executor = executor or SubprocessRuntimeExecutor()
        self.timeout_seconds = timeout_seconds

    def create(self, spec: RuntimeWorkloadSpec) -> RuntimeWorkloadStatus:
        self.policy.validate(spec)
        network_grants = self.network_policy.allowed_networks(spec)
        endpoints = [
            self.endpoint_registry.allocate(spec.workload_id, port)
            for port in spec.container_ports
        ]
        argv = self._base() + ["create", "--name", spec.workload_id]
        if network_grants:
            argv.extend(["--network", network_grants[0].network_name])
        for endpoint in endpoints:
            argv.extend(
                [
                    "--publish",
                    f"{endpoint.host_port}:{endpoint.container_port}",
                ]
            )
        for variable in spec.environment:
            argv.extend(["--env", f"{variable.name}={variable.value}"])
        argv.extend(["--", spec.image, *spec.command])

        created = False
        try:
            self._execute(argv)
            created = True
            for grant in network_grants[1:]:
                self._execute(
                    self._base()
                    + ["network", "connect", grant.network_name, spec.workload_id]
                )
        except Exception:
            if created:
                try:
                    self._execute(
                        self._base() + ["rm", "--force", "--", spec.workload_id]
                    )
                except Exception:
                    pass
            self.endpoint_registry.release(spec.workload_id)
            raise

        return RuntimeWorkloadStatus(
            workload_id=spec.workload_id,
            state=RuntimeWorkloadState.CREATED,
        )

    def start(self, workload_id: str) -> RuntimeWorkloadStatus:
        self._validated_id(workload_id)
        self._execute(self._base() + ["start", workload_id])
        return RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.RUNNING,
        )

    def stop(self, workload_id: str) -> RuntimeWorkloadStatus:
        self._validated_id(workload_id)
        self._execute(self._base() + ["stop", workload_id])
        return RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.STOPPED,
        )

    def remove(self, workload_id: str) -> None:
        self._validated_id(workload_id)
        self._execute(self._base() + ["rm", "--", workload_id])
        self.endpoint_registry.release(workload_id)

    def status(self, workload_id: str) -> RuntimeWorkloadStatus:
        self._validated_id(workload_id)
        result = self._execute(
            self._base()
            + [
                "inspect",
                "--format",
                "{{.State.Status}}",
                "--",
                workload_id,
            ]
        )
        raw_state = result.stdout.strip()
        try:
            state = RuntimeWorkloadState(raw_state)
        except ValueError:
            state = RuntimeWorkloadState.UNKNOWN
        return RuntimeWorkloadStatus(workload_id=workload_id, state=state)

    def logs(self, workload_id: str, *, tail: int = 200) -> str:
        self._validated_id(workload_id)
        if tail < 1 or tail > 1000:
            raise ValueError("tail must be between 1 and 1000")
        result = self._execute(
            self._base() + ["logs", "--tail", str(tail), "--", workload_id]
        )
        return result.stdout

    def publish_private_endpoint(
        self,
        workload_id: str,
        container_port: int,
    ) -> RuntimeEndpoint:
        self._validated_id(workload_id)
        return self.endpoint_registry.require(workload_id, container_port)

    def _execute(self, argv: list[str]) -> RuntimeCommandResult:
        result = self.executor.run(argv, timeout_seconds=self.timeout_seconds)
        if result.exit_code != 0:
            raise RuntimeControllerError(
                "RUNTIME_COMMAND_FAILED",
                "Runtime operation failed",
            )
        return result

    @staticmethod
    def _base() -> list[str]:
        return [
            "docker",
            "--host",
            f"unix://{DEFAULT_RUNTIME_SOCKET}",
        ]

    @staticmethod
    def _validated_id(workload_id: str) -> str:
        RuntimeWorkloadStatus(
            workload_id=workload_id,
            state=RuntimeWorkloadState.UNKNOWN,
        )
        return workload_id
