from __future__ import annotations

from dataclasses import dataclass
import socket
import subprocess
from typing import Callable
import urllib.request

from ai_workshop.config import WorkshopConfig


Probe = Callable[[], tuple[bool, str]]


@dataclass(frozen=True, slots=True)
class CheckSpec:
    name: str
    required: bool
    probe: Probe
    remediation: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    required: bool
    healthy: bool
    message: str
    remediation: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: list[CheckResult]

    @property
    def healthy(self) -> bool:
        return all(item.healthy for item in self.checks if item.required)

    @property
    def exit_code(self) -> int:
        return 0 if self.healthy else 1

    def by_name(self, name: str) -> CheckResult:
        for item in self.checks:
            if item.name == name:
                return item
        raise KeyError(name)


class Doctor:
    def __init__(self, checks: list[CheckSpec]):
        self.checks = list(checks)

    def run(self) -> DoctorReport:
        results: list[CheckResult] = []
        for check in self.checks:
            try:
                healthy, message = check.probe()
            except Exception as exc:
                healthy = False
                message = f"probe failed: {type(exc).__name__}"
            results.append(CheckResult(
                name=check.name,
                required=check.required,
                healthy=bool(healthy),
                message=str(message),
                remediation=check.remediation,
            ))
        return DoctorReport(results)


def project_paths_check(config: WorkshopConfig) -> CheckSpec:
    def probe() -> tuple[bool, str]:
        missing = [
            project.project_id
            for project in config.projects
            if not project.host.exists() or not project.host.is_dir()
        ]
        if missing:
            return False, "missing project paths: " + ", ".join(sorted(missing))
        return True, f"{len(config.projects)} project path(s) available"

    return CheckSpec(
        "projects",
        required=True,
        probe=probe,
        remediation="fix host paths in projects.local.yaml",
    )


def docker_check() -> CheckSpec:
    def probe() -> tuple[bool, str]:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return False, "Docker daemon is unavailable"
        return True, "Docker " + result.stdout.strip()

    return CheckSpec(
        "docker",
        required=True,
        probe=probe,
        remediation="start Docker or Docker Desktop",
    )


def http_health_check(
    name: str,
    base_url: str,
    *,
    required: bool,
    remediation: str,
) -> CheckSpec:
    url = base_url.rstrip("/") + "/health"

    def probe() -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return True, f"{name} healthy"
                return False, f"{name} returned HTTP {response.status}"
        except Exception:
            return False, f"{name} is unreachable"

    return CheckSpec(name, required, probe, remediation)


def tcp_check(
    name: str,
    host: str,
    port: int,
    *,
    required: bool,
    remediation: str,
) -> CheckSpec:
    def probe() -> tuple[bool, str]:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True, f"{name} reachable"
        except OSError:
            return False, f"{name} is unreachable"

    return CheckSpec(name, required, probe, remediation)
