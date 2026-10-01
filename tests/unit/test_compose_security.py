from pathlib import Path

import yaml


def test_compose_only_publishes_workspace_to_loopback_and_has_no_docker_socket():
    doc = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service = doc["services"]["agent-workspace"]
    assert service["ports"] == ["127.0.0.1:8766:8766"]
    text = Path("compose.yaml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in text
    assert "0.0.0.0:8766" not in text
    entrypoint = Path("agent/entrypoint.sh").read_text(encoding="utf-8")
    assert "exec gosu" in entrypoint


def test_compose_command_does_not_repeat_image_entrypoint():
    doc = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    command = doc["services"]["agent-workspace"]["command"]
    assert command[0] == "workspace"


def test_compose_requires_workspace_token():
    doc = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    value = doc["services"]["agent-workspace"]["environment"]["AI_WORKSHOP_WORKSPACE_TOKEN"]
    assert "AI_WORKSHOP_WORKSPACE_TOKEN" in value
    assert ":?" in value


def test_agent_image_contains_expected_dev_toolchain():
    dockerfile = Path("agent/Dockerfile").read_text(encoding="utf-8")
    for token in ["node:24", "npm", "pnpm", "uv", "poetry", "pytest", "fd-find", "wget"]:
        assert token in dockerfile


def test_agent_uses_dynamic_non_root_uid_gid_mapping():
    doc = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service = doc["services"]["agent-workspace"]
    assert "user" not in service
    env = service["environment"]
    assert "AI_WORKSHOP_UID" in env and "AI_WORKSHOP_GID" in env
    entrypoint = Path("agent/entrypoint.sh").read_text(encoding="utf-8")
    assert "gosu" in entrypoint
    assert '"$AI_WORKSHOP_UID" = "0"' in entrypoint
