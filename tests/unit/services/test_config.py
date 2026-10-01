from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.services.config import ServiceConfig


def projects(tmp_path: Path) -> WorkshopConfig:
    app = tmp_path / "app"
    app.mkdir()
    (app / "frontend").mkdir()
    return WorkshopConfig(projects=[
        ProjectMount(project_id="app", host=app, container="/workspace/app", mode="rw"),
    ])


def write_services(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "services.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_build_and_image_services(tmp_path: Path):
    config = ServiceConfig.load(write_services(tmp_path, """
profiles:
  dev:
    services: [web, cache]
services:
  web:
    source:
      kind: build
      project_id: app
      context: frontend
    command: ["python", "-m", "http.server", "8080"]
    ports:
      - container: 8080
        host: 18080
  cache:
    source:
      kind: image
      image: "example/cache:1"
    volumes:
      - name: data
        target: /data
"""))
    config.validate(projects(tmp_path))
    assert config.profiles["dev"].services == ["web", "cache"]
    assert config.services["web"].source.kind == "build"
    assert config.services["cache"].source.kind == "image"


def test_service_build_context_must_be_registered_project(tmp_path: Path):
    config = ServiceConfig.load(write_services(tmp_path, """
services:
  bad:
    source:
      kind: build
      project_id: missing
      context: .
"""))
    with pytest.raises(ValueError, match="registered project"):
        config.validate(projects(tmp_path))


def test_build_context_cannot_escape_project(tmp_path: Path):
    config = ServiceConfig.load(write_services(tmp_path, """
services:
  bad:
    source:
      kind: build
      project_id: app
      context: ../outside
"""))
    with pytest.raises(ValueError, match="outside project root"):
        config.validate(projects(tmp_path))


def test_profile_rejects_unknown_service(tmp_path: Path):
    config = ServiceConfig.load(write_services(tmp_path, """
profiles:
  bad:
    services: [missing]
services: {}
"""))
    with pytest.raises(ValueError, match="unknown service"):
        config.validate(projects(tmp_path))
