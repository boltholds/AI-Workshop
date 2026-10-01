from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.recovery.config import RecoveryConfig, build_recovery_runtime


def projects(tmp_path: Path) -> WorkshopConfig:
    project = tmp_path / "project"
    project.mkdir()
    return WorkshopConfig(projects=[
        ProjectMount(project_id="app", host=project, container="/workspace/app", mode="rw")
    ])


def test_recovery_config_builds_named_postgres_adapter_from_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APP_DB_PASSWORD", "db-secret")
    path = tmp_path / "recovery.yaml"
    path.write_text("""
state_adapters:
  app-db:
    kind: postgres
    targets:
      primary:
        host: 127.0.0.1
        port: 5432
        database: app
        user: workshop
        password_env: APP_DB_PASSWORD
reset:
  cache_paths:
    - .workshop/cache
  browser_artifact_paths:
    - .workshop/browser-artifacts
""", encoding="utf-8")

    config = RecoveryConfig.load(path)
    runtime = build_recovery_runtime(
        config,
        state_root=tmp_path / ".workshop" / "state",
        projects=projects(tmp_path),
    )

    assert runtime.state_service is not None
    adapter = runtime.state_service.registry.require("app-db")
    target = adapter.targets["primary"]
    assert target.password == "db-secret"
    assert runtime.reset_service is not None
    assert runtime.reset_service.plan("cache").filesystem_paths == [
        str((tmp_path / ".workshop" / "cache").resolve())
    ]


def test_recovery_config_never_accepts_inline_postgres_password(tmp_path: Path):
    path = tmp_path / "recovery.yaml"
    path.write_text("""
state_adapters:
  app-db:
    kind: postgres
    targets:
      primary:
        host: 127.0.0.1
        port: 5432
        database: app
        user: workshop
        password: should-not-be-allowed
""", encoding="utf-8")
    with pytest.raises(ValueError):
        RecoveryConfig.load(path)


def test_missing_referenced_password_env_is_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MISSING_DB_PASSWORD", raising=False)
    path = tmp_path / "recovery.yaml"
    path.write_text("""
state_adapters:
  app-db:
    kind: postgres
    targets:
      primary:
        host: 127.0.0.1
        port: 5432
        database: app
        user: workshop
        password_env: MISSING_DB_PASSWORD
""", encoding="utf-8")
    config = RecoveryConfig.load(path)
    with pytest.raises(ValueError, match="MISSING_DB_PASSWORD"):
        build_recovery_runtime(
            config,
            state_root=tmp_path / "state",
            projects=projects(tmp_path),
        )


def test_reset_path_overlapping_project_is_rejected(tmp_path: Path):
    project_cfg = projects(tmp_path)
    path = tmp_path / "recovery.yaml"
    path.write_text("""
reset:
  cache_paths:
    - project/cache
""", encoding="utf-8")
    config = RecoveryConfig.load(path)
    with pytest.raises(ValueError, match="overlaps project root"):
        build_recovery_runtime(
            config,
            state_root=tmp_path / "state",
            projects=project_cfg,
        )
