from pathlib import Path

import yaml


def test_compose_only_publishes_workspace_to_loopback_and_has_no_docker_socket():
    doc = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service = doc["services"]["agent-workspace"]
    assert service["ports"] == ["127.0.0.1:8766:8766"]
    text = Path("compose.yaml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in text
    assert "0.0.0.0:8766" not in text
    assert service["user"] != "root"
