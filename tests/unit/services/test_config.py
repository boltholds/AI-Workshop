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
    environment:
      APP_MODE: test
    env_files:
      - .workshop/secrets/web.env
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
    assert config.services["web"].environment == {"APP_MODE": "test"}
    assert config.services["web"].env_files == [".workshop/secrets/web.env"]
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


def test_env_file_must_live_under_workshop_secrets(tmp_path: Path):
    with pytest.raises(ValueError, match="workshop/secrets"):
        ServiceConfig.load(write_services(tmp_path, """
services:
  bad:
    source:
      kind: image
      image: example/app:1
    env_files:
      - ../host-secret.env
"""))


def test_unknown_service_field_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="extra"):
        ServiceConfig.load(write_services(tmp_path, """
services:
  bad:
    source:
      kind: image
      image: example/app:1
    arbitrary_host_access: true
"""))
