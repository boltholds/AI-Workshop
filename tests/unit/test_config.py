from pathlib import Path

import pytest

from ai_workshop.config import WorkshopConfig


def test_loads_projects_from_yaml(tmp_path: Path) -> None:
    cfg = tmp_path / "projects.yaml"
    cfg.write_text(
        "projects:\n"
        "  plc-web:\n"
        "    host: /tmp/plc-web\n"
        "    container: /workspace/plc-web\n"
        "    mode: rw\n",
        encoding="utf-8",
    )
    config = WorkshopConfig.load(cfg)
    assert config.projects["plc-web"].container.as_posix() == "/workspace/plc-web"
    assert config.projects["plc-web"].mode == "rw"


def test_rejects_invalid_mode(tmp_path: Path) -> None:
    cfg = tmp_path / "projects.yaml"
    cfg.write_text(
        "projects:\n  app:\n    host: /tmp/app\n    container: /workspace/app\n    mode: write-everywhere\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="mode"):
        WorkshopConfig.load(cfg)


def test_rejects_duplicate_project_ids(tmp_path: Path) -> None:
    cfg = tmp_path / "projects.yaml"
    cfg.write_text(
        "projects:\n"
        "  app:\n    host: /tmp/a\n    container: /workspace/a\n"
        "  app:\n    host: /tmp/b\n    container: /workspace/b\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        WorkshopConfig.load(cfg)


def test_missing_config_is_clear(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        WorkshopConfig.load(tmp_path / "missing.yaml")
