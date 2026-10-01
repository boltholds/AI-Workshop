from pathlib import Path

import yaml

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.services.config import ServiceConfig
from ai_workshop.services.render import render_service_override


def test_render_build_image_ports_volumes_and_registry(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    cfg = WorkshopConfig(projects=[
        ProjectMount(project_id="app", host=app, container="/workspace/app", mode="rw"),
    ])
    services_path = tmp_path / "services.yaml"
    services_path.write_text("""
profiles:
  dev:
    services: [web, state]
services:
  web:
    source:
      kind: build
      project_id: app
      context: .
    environment:
      APP_MODE: test
    env_files:
      - .workshop/secrets/web.env
    ports:
      - container: 8000
        host: 18000
    depends_on: [state]
  state:
    source:
      kind: image
      image: "example/state:1"
    volumes:
      - name: data
        target: /var/lib/state
""", encoding="utf-8")
    services = ServiceConfig.load(services_path)
    services.validate(cfg)

    secrets = tmp_path / ".workshop" / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "web.env").write_text("TOKEN=test-only\n", encoding="utf-8")
    compose_path = tmp_path / ".workshop" / "compose.services.yaml"
    registry_path = tmp_path / ".workshop" / "service-registry.yaml"
    render_service_override(services, cfg, compose_path=compose_path, registry_path=registry_path)

    doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert doc["services"]["web"]["build"]["context"] == str(app.resolve())
    assert doc["services"]["web"]["ports"] == ["127.0.0.1:18000:8000"]
    assert doc["services"]["web"]["depends_on"] == ["state"]
    assert doc["services"]["web"]["environment"] == {"APP_MODE": "test"}
    assert doc["services"]["web"]["env_file"] == [str((tmp_path / ".workshop" / "secrets" / "web.env").resolve())]
    assert doc["services"]["state"]["image"] == "example/state:1"
    assert doc["services"]["state"]["volumes"] == ["state-data:/var/lib/state"]
    assert doc["volumes"]["state-data"]["name"] == "ai-workshop-state-data"
    assert doc["networks"]["ai-workshop"] == {"external": True}
    rendered = compose_path.read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in rendered

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert sorted(registry["services"]) == ["state", "web"]
    assert registry["profiles"]["dev"] == ["web", "state"]
    assert registry["services"]["web"]["compose_service"] == "web"
    assert registry["services"]["web"]["compose_files"] == [str(compose_path.resolve())]
