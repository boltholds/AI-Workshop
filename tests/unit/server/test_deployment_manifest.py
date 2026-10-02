from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def load_yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_server_manifest_has_rootless_runtime_and_persistent_storage():
    compose = load_yaml("compose.server.yaml")
    services = compose["services"]
    volumes = compose["volumes"]

    assert {"server-control", "rootless-runtime"} <= set(services)
    assert {
        "server-runtime-data",
        "server-runtime-socket",
        "server-storage",
        "server-state",
    } <= set(volumes)

    image = services["rootless-runtime"]["image"]
    assert image.startswith("docker:")
    assert "@sha256:" in image
    assert len(image.partition("@sha256:")[2]) == 64


def test_only_runtime_and_control_plane_receive_private_runtime_socket():
    compose = load_yaml("compose.server.yaml")
    consumers = set()
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            serialized = str(volume)
            if "server-runtime-socket" in serialized:
                consumers.add(name)

    assert consumers == {"rootless-runtime", "server-control"}


def test_server_manifest_never_mounts_host_docker_socket():
    text = (ROOT / "compose.server.yaml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in text


def test_only_rootless_runtime_has_outer_privileged_mode():
    compose = load_yaml("compose.server.yaml")
    privileged = {
        name
        for name, service in compose["services"].items()
        if service.get("privileged") is True
    }
    assert privileged == {"rootless-runtime"}


def test_control_plane_and_runtime_do_not_publish_lan_ports():
    compose = load_yaml("compose.server.yaml")

    assert "ports" not in compose["services"]["server-control"]
    assert "ports" not in compose["services"]["rootless-runtime"]


def test_desktop_compose_does_not_include_server_runtime():
    compose = load_yaml("compose.yaml")

    assert "server-control" not in compose["services"]
    assert "rootless-runtime" not in compose["services"]
    assert "server-runtime-socket" not in (compose.get("volumes") or {})


def test_server_runtime_uses_pinned_rootless_dind_image():
    compose = load_yaml(ROOT / "compose.server.yaml")
    runtime = compose["services"]["rootless-runtime"]
    image = runtime["image"]

    assert "dind-rootless@sha256:" in image
    assert image.startswith("docker:29.8.1-dind-rootless@sha256:")


def test_server_control_image_installs_git_and_ssh_client():
    dockerfile = (ROOT / "server" / "Dockerfile").read_text(encoding="utf-8")

    assert "apt-get install" in dockerfile
    assert "git" in dockerfile
    assert "openssh-client" in dockerfile


def test_final_server_deployment_contains_required_outer_services():
    compose = load_yaml("deploy/server/compose.yaml")
    services = compose["services"]
    assert {"server-control", "browser", "ingress"} <= set(services)
    assert "rootless-runtime" not in services


def test_final_server_deployment_never_mounts_host_docker_socket():
    text = (ROOT / "deploy/server/compose.yaml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in text


def test_final_server_deployment_only_ingress_publishes_host_port():
    compose = load_yaml("deploy/server/compose.yaml")
    services = compose["services"]
    published = {name for name, spec in services.items() if spec.get("ports")}
    assert published == {"ingress"}


def test_final_server_deployment_runtime_socket_is_host_bind_and_control_plane_only():
    compose = load_yaml("deploy/server/compose.yaml")
    consumers = []
    for name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            serialized = str(volume)
            if "docker.sock" in serialized:
                consumers.append((name, serialized))
    assert len(consumers) == 1
    name, mount = consumers[0]
    assert name == "server-control"
    assert "AI_WORKSHOP_RUNTIME_SOCKET" in mount
    assert "/run/ai-workshop-runtime/1000/docker.sock" in mount
    assert "/var/run/docker.sock" not in mount


def test_final_server_deployment_persists_required_domains():
    compose = load_yaml("deploy/server/compose.yaml")
    volumes = set(compose["volumes"])
    assert {
        "server-state",
        "server-ca",
        "browser-profile",
        "browser-artifacts",
    } <= volumes
    assert "server-runtime-data" not in volumes
    assert "server-storage" not in volumes

    control_mounts = [
        str(item)
        for item in compose["services"]["server-control"]["volumes"]
    ]
    assert any("AI_WORKSHOP_STORAGE_ROOT" in item for item in control_mounts)




def test_final_server_config_uses_host_runtime_endpoint():
    config = load_yaml("deploy/server/config/server.yaml")
    assert config["storage_root"] == "/var/lib/ai-workshop/storage"
    assert config["private_endpoint_host"] == "host.docker.internal"


def test_final_server_control_maps_host_gateway():
    compose = load_yaml("deploy/server/compose.yaml")
    extra_hosts = compose["services"]["server-control"]["extra_hosts"]
    assert "host.docker.internal:host-gateway" in extra_hosts
