from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol

from ai_workshop.controller.registry import RegisteredService, ServiceRegistry
from ai_workshop.models.services import ServiceStatus


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class ControllerError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class Executor(Protocol):
    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> CommandResult: ...


class SubprocessExecutor:
    def run(self, argv: list[str], *, cwd: Path, timeout_seconds: float) -> CommandResult:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class ComposeController:
    def __init__(
        self,
        registry: ServiceRegistry,
        *,
        executor: Executor | None = None,
        timeout_seconds: float = 60.0,
    ):
        self.registry = registry
        self.executor = executor or SubprocessExecutor()
        self.timeout_seconds = timeout_seconds

    def list_services(self, profile_id: str | None = None) -> list[str]:
        return self.registry.list_ids(profile_id)

    def status(self, service_id: str) -> ServiceStatus:
        result = self._execute(service_id, "status", ["ps"])
        return ServiceStatus(service_id=service_id, stdout=result.stdout)

    def logs(self, service_id: str, *, tail: int = 200) -> str:
        if tail < 1 or tail > 1000:
            raise ValueError("tail must be between 1 and 1000")
        result = self._execute(
            service_id,
            "logs",
            ["logs", "--no-color", "--tail", str(tail)],
        )
        return result.stdout

    def restart(self, service_id: str) -> None:
        self._execute(service_id, "restart", ["restart"])

    def rebuild(self, service_id: str) -> None:
        self._execute(service_id, "rebuild", ["up", "-d", "--build"])

    def up(self, service_id: str) -> None:
        self._execute(service_id, "up", ["up", "-d"])

    def _execute(self, service_id: str, operation: str, operation_argv: list[str]) -> CommandResult:
        service = self.registry.require(service_id)
        if operation not in service.allowed_operations:
            raise ControllerError("OPERATION_NOT_ALLOWED", "Service operation is not allowed")
        argv = self._base_argv(service) + operation_argv + [service.compose_service]
        try:
            result = self.executor.run(
                argv,
                cwd=service.working_dir,
                timeout_seconds=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise ControllerError("COMMAND_TIMEOUT", "Service operation timed out") from exc
        if result.exit_code != 0:
            raise ControllerError("COMMAND_FAILED", "Service operation failed")
        return result

    @staticmethod
    def _base_argv(service: RegisteredService) -> list[str]:
        argv = ["docker", "compose", "-p", service.compose_project]
        for compose_file in service.compose_files:
            argv.extend(["-f", str(compose_file)])
        return argv
