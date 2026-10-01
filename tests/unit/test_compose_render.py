from pathlib import Path

import yaml

from ai_workshop.compose.render import render_project_override
from ai_workshop.config import WorkshopConfig


def test_renders_deterministic_agent_mounts(tmp_path: Path):
    cfg_path = tmp_path / "projects.yaml"
    cfg_path.write_text("""
projects:
  plc-web:
    host: /host/plc-web
    container: /workspace/plc-web
    mode: rw
  titan:
    host: /host/titan
    container: /workspace/titan
    mode: ro
""", encoding="utf-8")
    cfg = WorkshopConfig.load(cfg_path)
    out = tmp_path / ".workshop" / "compose.projects.yaml"
    result = render_project_override(cfg, out)
    assert result == out
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["services"]["agent-workspace"]["volumes"] == [
        {"type": "bind", "source": "/host/plc-web", "target": "/workspace/plc-web", "read_only": False},
        {"type": "bind", "source": "/host/titan", "target": "/workspace/titan", "read_only": True},
    ]
    rendered = out.read_text(encoding="utf-8")
    assert "/home/" not in rendered
    assert "/var/run/docker.sock" not in rendered
