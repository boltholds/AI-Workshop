from pathlib import Path

import yaml

from ai_workshop.compose.render import render_project_override
from ai_workshop.config import WorkshopConfig


def test_render_project_override_mounts_only_configured_projects(tmp_path: Path) -> None:
    cfg = tmp_path / "projects.yaml"
    cfg.write_text(
        "projects:\n"
        "  alpha:\n    host: /host/alpha\n    container: /workspace/alpha\n    mode: rw\n"
        "  beta:\n    host: /host/beta\n    container: /workspace/beta\n    mode: ro\n",
        encoding="utf-8",
    )
    config = WorkshopConfig.load(cfg)
    out = tmp_path / "override.yaml"
    assert render_project_override(config, out) == out
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["services"]["agent-workspace"]["volumes"] == [
        {"type": "bind", "source": "/host/alpha", "target": "/workspace/alpha", "read_only": False},
        {"type": "bind", "source": "/host/beta", "target": "/workspace/beta", "read_only": True},
    ]
    rendered = out.read_text(encoding="utf-8")
    assert "/home" not in rendered
    assert "docker.sock" not in rendered
