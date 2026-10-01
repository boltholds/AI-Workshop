import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def test_compose_keeps_workspace_api_loopback_and_no_docker_socket() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    agent = compose["services"]["agent-workspace"]
    assert "127.0.0.1:8766:8766" in agent["ports"]
    serialized = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "docker.sock" not in serialized
    dockerfile = (ROOT / "agent/Dockerfile").read_text(encoding="utf-8")
    assert "USER workshop" in dockerfile


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker unavailable in execution sandbox")
def test_core_compose_config_is_valid() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "config"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
