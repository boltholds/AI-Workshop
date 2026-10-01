from __future__ import annotations

import json
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.controller.registry import ServiceRegistry
from ai_workshop.controller.runner import ComposeController
from ai_workshop.services.config import ServiceConfig
from ai_workshop.services.render import render_service_override


pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required")


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    try:
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def wait_health(port: int, *, minimum_count: int = 1) -> dict[str, object]:
    deadline = time.time() + 60
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                payload = json.loads(response.read())
            if int(payload["start_count"]) >= minimum_count:
                return payload
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(f"service did not become healthy: {last_error}")


def test_generic_service_rebuild_preserves_named_volume(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    project = tmp_path / "fixture-project"
    shutil.copytree(repo_root / "tests" / "fixtures" / "service-project", project)
    port = free_port()

    projects = WorkshopConfig(projects=[
        ProjectMount(
            project_id="fixture",
            host=project,
            container="/workspace/fixture",
            mode="rw",
        )
    ])
    services = ServiceConfig.model_validate({
        "profiles": {"dev": {"services": ["fixture"]}},
        "services": {
            "fixture": {
                "source": {
                    "kind": "build",
                    "project_id": "fixture",
                    "context": ".",
                },
                "ports": [{"container": 8080, "host": port}],
                "volumes": [{"name": "data", "target": "/data"}],
            }
        },
    })
    services.validate(projects)

    compose_path = tmp_path / ".workshop" / "compose.services.yaml"
    registry_path = tmp_path / ".workshop" / "service-registry.yaml"
    render_service_override(
        services,
        projects,
        compose_path=compose_path,
        registry_path=registry_path,
    )

    network_created = False
    inspect = subprocess.run(
        ["docker", "network", "inspect", "ai-workshop"],
        capture_output=True,
        check=False,
    )
    if inspect.returncode != 0:
        subprocess.run(["docker", "network", "create", "ai-workshop"], check=True)
        network_created = True

    controller = ComposeController(
        ServiceRegistry.load(registry_path),
        timeout_seconds=180,
    )
    cleanup = [
        "docker", "compose", "-p", "ai-workshop-services",
        "-f", str(compose_path), "down", "-v", "--remove-orphans",
    ]
    try:
        controller.up("fixture")
        first = wait_health(port)
        assert first["start_count"] == 1
        assert "started 1" in controller.logs("fixture", tail=50)
        assert "fixture" in controller.status("fixture").stdout

        with (project / "server.py").open("a", encoding="utf-8") as handle:
            handle.write("\n# force image rebuild\n")
        controller.rebuild("fixture")
        second = wait_health(port, minimum_count=2)
        assert int(second["start_count"]) >= 2
    finally:
        subprocess.run(cleanup, check=False, capture_output=True)
        if network_created:
            subprocess.run(["docker", "network", "rm", "ai-workshop"], check=False, capture_output=True)
