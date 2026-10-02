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
    assert image.startswith("docker@sha256:")
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
