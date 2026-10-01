from pathlib import Path
import yaml

def test_compose_only_publishes_workspace_to_loopback_and_has_no_docker_socket():
    doc=yaml.safe_load(Path("compose.yaml").read_text()); svc=doc["services"]["agent-workspace"]
    assert svc["ports"]==["127.0.0.1:8766:8766"]; assert "/var/run/docker.sock" not in Path("compose.yaml").read_text()

def test_compose_command_does_not_repeat_image_entrypoint():
    assert yaml.safe_load(Path("compose.yaml").read_text())["services"]["agent-workspace"]["command"][0]=="workspace"

def test_browser_service_is_loopback_only_and_persistent():
    doc=yaml.safe_load(Path("compose.yaml").read_text()); browser=doc["services"]["browser"]
    assert browser["ports"]==["127.0.0.1:8767:8767"]
    targets={v["target"] for v in browser["volumes"] if isinstance(v,dict)}
    assert {"/data/browser-profile","/data/artifacts"} <= targets
    assert "/var/run/docker.sock" not in Path("compose.yaml").read_text()
