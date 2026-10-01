import os

from ai_workshop.recovery.env import safe_subprocess_env


def test_recovery_subprocess_env_drops_workshop_control_secrets(monkeypatch):
    monkeypatch.setenv("AI_WORKSHOP_WORKSPACE_TOKEN", "workspace-secret")
    monkeypatch.setenv("AI_WORKSHOP_BROWSER_TOKEN", "browser-secret")
    monkeypatch.setenv("AI_WORKSHOP_MCP_TOKEN", "mcp-secret")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    env = safe_subprocess_env()

    assert "AI_WORKSHOP_WORKSPACE_TOKEN" not in env
    assert "AI_WORKSHOP_BROWSER_TOKEN" not in env
    assert "AI_WORKSHOP_MCP_TOKEN" not in env
    assert "PATH" in env


def test_recovery_subprocess_env_allows_explicit_adapter_secret(monkeypatch):
    monkeypatch.setenv("AI_WORKSHOP_WORKSPACE_TOKEN", "workspace-secret")
    env = safe_subprocess_env({"PGPASSWORD": "db-secret"})
    assert env["PGPASSWORD"] == "db-secret"
    assert "AI_WORKSHOP_WORKSPACE_TOKEN" not in env
