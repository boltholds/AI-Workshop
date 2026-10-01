from pathlib import Path

import pytest

from ai_workshop.controller.registry import RegisteredService, ServiceRegistry


def sample_service(tmp_path: Path, service_id: str = "web") -> RegisteredService:
    compose = tmp_path / "compose.services.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    return RegisteredService(
        service_id=service_id,
        compose_project="ai-workshop-services",
        working_dir=tmp_path,
        compose_files=(compose,),
        compose_service=service_id,
        allowed_operations=frozenset({"status", "logs", "restart", "rebuild", "up"}),
    )


def test_registry_lists_services_deterministically(tmp_path: Path):
    registry = ServiceRegistry([sample_service(tmp_path, "worker"), sample_service(tmp_path, "web")])
    assert registry.list_ids() == ["web", "worker"]


def test_rejects_unregistered_service(tmp_path: Path):
    registry = ServiceRegistry([sample_service(tmp_path)])
    with pytest.raises(KeyError, match="unregistered service"):
        registry.require("missing")


def test_registry_rejects_duplicate_service_id(tmp_path: Path):
    with pytest.raises(ValueError, match="duplicate service"):
        ServiceRegistry([sample_service(tmp_path, "web"), sample_service(tmp_path, "web")])


def test_registry_loads_generated_yaml(tmp_path: Path):
    registry_path = tmp_path / "registry.yaml"
    compose = tmp_path / "compose.services.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    registry_path.write_text(f"""
profiles:
  dev: [web]
services:
  web:
    compose_project: workshop-dev
    working_dir: {tmp_path}
    compose_files:
      - {compose}
    compose_service: web
    allowed_operations: [status, logs, restart]
""", encoding="utf-8")
    registry = ServiceRegistry.load(registry_path)
    assert registry.list_ids() == ["web"]
    assert registry.require("web").compose_files == (compose.resolve(),)
    assert registry.list_ids("dev") == ["web"]
    with pytest.raises(KeyError, match="unknown service profile"):
        registry.list_ids("missing")


def test_registry_rejects_option_like_compose_service(tmp_path: Path):
    compose = tmp_path / "compose.services.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="compose_service"):
        RegisteredService(
            service_id="safe-id",
            compose_project="workshop-dev",
            working_dir=tmp_path,
            compose_files=(compose,),
            compose_service="--project-directory=/",
            allowed_operations=frozenset({"status"}),
        )
