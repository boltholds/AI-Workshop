from pathlib import Path

import pytest

from ai_workshop.server.config import ServerModeConfig


def test_server_storage_root_must_be_absolute(tmp_path: Path):
    config = tmp_path / "server.yaml"
    config.write_text("storage_root: relative/storage\n", encoding="utf-8")

    with pytest.raises(ValueError, match="storage_root"):
        ServerModeConfig.load(config)


def test_runtime_socket_is_not_configurable_from_server_yaml(tmp_path: Path):
    config = tmp_path / "server.yaml"
    config.write_text(
        "storage_root: /srv/ai-workshop\nruntime_socket: /var/run/docker.sock\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        ServerModeConfig.load(config)


def test_server_config_loads_absolute_storage_root(tmp_path: Path):
    config = tmp_path / "server.yaml"
    config.write_text("storage_root: /srv/ai-workshop\n", encoding="utf-8")

    loaded = ServerModeConfig.load(config)

    assert loaded.storage_root == Path("/srv/ai-workshop")


def test_server_config_has_private_endpoint_defaults(tmp_path: Path):
    config = tmp_path / "server.yaml"
    config.write_text("storage_root: /srv/ai-workshop\n", encoding="utf-8")

    loaded = ServerModeConfig.load(config)

    assert loaded.private_endpoint_host == "rootless-runtime"
    assert loaded.private_endpoint_start_port == 41000
    assert loaded.private_endpoint_end_port == 41999
