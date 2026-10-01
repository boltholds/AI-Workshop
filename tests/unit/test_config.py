from pathlib import Path

import pytest

from ai_workshop.config import WorkshopConfig


def write_cfg(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "projects.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_multiple_projects(tmp_path: Path):
    path = write_cfg(tmp_path, """
projects:
  plc-web:
    host: /tmp/plc-web
    container: /workspace/plc-web
    mode: rw
  titan:
    host: /tmp/titan
    container: /workspace/titan
    mode: ro
""")
    cfg = WorkshopConfig.load(path)
    assert [p.project_id for p in cfg.projects] == ["plc-web", "titan"]
    assert cfg.projects[0].mode == "rw"
    assert str(cfg.projects[1].container) == "/workspace/titan"


def test_rejects_invalid_mode(tmp_path: Path):
    path = write_cfg(tmp_path, """
projects:
  bad:
    host: /tmp/bad
    container: /workspace/bad
    mode: write
""")
    with pytest.raises(ValueError, match="mode"):
        WorkshopConfig.load(path)


def test_requires_host_path(tmp_path: Path):
    path = write_cfg(tmp_path, """
projects:
  bad:
    container: /workspace/bad
    mode: rw
""")
    with pytest.raises(ValueError):
        WorkshopConfig.load(path)


def test_missing_config_is_clear(tmp_path: Path):
    path = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        WorkshopConfig.load(path)
