from pathlib import Path

import yaml
import pytest

from ai_workshop.bootstrap import (
    ensure_env_file,
    ensure_project_config,
    ensure_recovery_config,
)


def test_env_file_is_created_with_random_tokens_and_is_idempotent(tmp_path: Path):
    env_path = tmp_path / ".env.local"

    first = ensure_env_file(env_path)
    first_text = env_path.read_text(encoding="utf-8")
    second = ensure_env_file(env_path)

    assert first == second
    assert env_path.read_text(encoding="utf-8") == first_text
    assert len(first["AI_WORKSHOP_WORKSPACE_TOKEN"]) >= 64
    assert len(first["AI_WORKSHOP_BROWSER_TOKEN"]) >= 64
    assert first["AI_WORKSHOP_WORKSPACE_TOKEN"] != first["AI_WORKSHOP_BROWSER_TOKEN"]
    assert first["AI_WORKSHOP_WORKSPACE_URL"] == "http://127.0.0.1:8766"
    assert first["AI_WORKSHOP_BROWSER_URL"] == "http://127.0.0.1:8767"


def test_env_file_preserves_existing_secrets_and_adds_missing_defaults(tmp_path: Path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "AI_WORKSHOP_WORKSPACE_TOKEN=keep-me\nCUSTOM_VALUE=untouched\n",
        encoding="utf-8",
    )

    values = ensure_env_file(env_path)
    text = env_path.read_text(encoding="utf-8")

    assert values["AI_WORKSHOP_WORKSPACE_TOKEN"] == "keep-me"
    assert "CUSTOM_VALUE=untouched" in text
    assert values["AI_WORKSHOP_BROWSER_TOKEN"]
    assert "AI_WORKSHOP_MCP_PORT=8765" in text


def test_project_config_is_created_for_real_folder_and_not_overwritten(tmp_path: Path):
    project = tmp_path / "My Project"
    project.mkdir()
    config_path = tmp_path / "config" / "projects.local.yaml"

    created = ensure_project_config(config_path, project, project_id="demo-app")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert created is True
    assert payload == {
        "projects": {
            "demo-app": {
                "host": str(project.resolve()),
                "container": "/workspace/demo-app",
                "mode": "rw",
            }
        }
    }

    config_path.write_text("projects: {custom: {host: custom, container: /workspace/custom, mode: ro}}\n", encoding="utf-8")
    assert ensure_project_config(config_path, project, project_id="ignored") is False
    assert "custom" in config_path.read_text(encoding="utf-8")


def test_project_config_requires_project_on_first_run(tmp_path: Path):
    with pytest.raises(ValueError, match="project path is required"):
        ensure_project_config(tmp_path / "projects.local.yaml", None)


def test_project_config_rejects_missing_project(tmp_path: Path):
    with pytest.raises(ValueError, match="does not exist"):
        ensure_project_config(
            tmp_path / "projects.local.yaml",
            tmp_path / "missing",
        )


def test_recovery_config_copies_example_once(tmp_path: Path):
    example = tmp_path / "recovery.example.yaml"
    example.write_text("state_adapters: {}\n", encoding="utf-8")
    target = tmp_path / "recovery.local.yaml"

    assert ensure_recovery_config(target, example) is True
    assert target.read_text(encoding="utf-8") == "state_adapters: {}\n"

    target.write_text("custom: true\n", encoding="utf-8")
    assert ensure_recovery_config(target, example) is False
    assert target.read_text(encoding="utf-8") == "custom: true\n"
