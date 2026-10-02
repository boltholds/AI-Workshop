from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Protocol

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
        executor: RuntimeExecutor | None = None,
        timeout_seconds: float = 60.0,
    ):
        self.policy = policy
        self.executor = executor or SubprocessRuntimeExecutor()
        self.timeout_seconds = timeout_seconds

    def create(self, spec: RuntimeWorkloadSpec) -> RuntimeWorkloadStatus:
        self.policy.validate(spec)
        argv = self._base() + ["create", "--name", spec.workload_id]
        for variable in spec.environment:
            argv.extend(["--env", f"{variable.name}={variable.value}"])
        argv.extend(["--", spec.image, *spec.command])
        self._execute(argv)
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
        raise RuntimeControllerError(
            "ENDPOINT_REGISTRY_UNAVAILABLE",
            "Private endpoint registry is not configured",
        )

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
