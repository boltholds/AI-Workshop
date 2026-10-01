from pathlib import Path

import pytest

from ai_workshop.gateway.recovery_tools import register_recovery_tools


class FakeServer:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorate(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorate


class FakeWorkspaceRecoveryClient:
    def snapshot_create(self, project_id: str):
        return {"snapshot_id": "s1", "project_id": project_id}

    def snapshot_preview_restore(self, snapshot_id: str):
        return {"snapshot_id": snapshot_id, "reset_paths": ["a.txt"], "digest": "d"}

    def snapshot_prepare_restore(self, snapshot_id: str, ttl_seconds: float = 300.0):
        return {"token": "token-1", "snapshot_id": snapshot_id, "expires_at": 123.0}

    def snapshot_restore(self, snapshot_id: str, confirmation_token: str):
        assert confirmation_token == "token-1"
        return {"snapshot_id": snapshot_id, "restored": True}


class FakeStateService:
    def create(self, adapter_id: str, target_id: str):
        return type("Artifact", (), {"model_dump": lambda self: {
            "snapshot_id": "state-1", "adapter_id": adapter_id,
            "target_id": target_id, "sha256": "abc", "size_bytes": 3,
        }})()

    def prepare_restore(self, snapshot_id: str, ttl_seconds: float = 300.0):
        return type("Token", (), {"model_dump": lambda self: {
            "token": "state-token", "snapshot_id": snapshot_id,
            "preview_digest": "d", "expires_at": 123.0,
        }})()

    def restore(self, snapshot_id: str, token: str):
        assert token == "state-token"
        return type("Result", (), {"model_dump": lambda self: {
            "snapshot_id": snapshot_id, "adapter_id": "memory",
            "target_id": "primary", "restored": True,
        }})()


def test_recovery_tools_expose_snapshot_confirmation_flow():
    server = FakeServer()
    register_recovery_tools(server, FakeWorkspaceRecoveryClient())

    assert server.tools["workspace_snapshot_create"]("project")["snapshot_id"] == "s1"
    assert server.tools["workspace_snapshot_preview_restore"]("s1")["digest"] == "d"
    confirmation = server.tools["workspace_snapshot_prepare_restore"]("s1", 300)
    assert confirmation["token"] == "token-1"
    result = server.tools["workspace_snapshot_restore"]("s1", "token-1")
    assert result["restored"] is True


def test_destructive_workspace_restore_has_no_boolean_confirm_shortcut():
    server = FakeServer()
    register_recovery_tools(server, FakeWorkspaceRecoveryClient())
    annotations = server.tools["workspace_snapshot_restore"].__annotations__
    assert "confirmation_token" in annotations
    assert "confirm" not in annotations
    with pytest.raises(TypeError):
        server.tools["workspace_snapshot_restore"]("s1", confirm=True)


def test_generic_state_snapshot_tools_are_optional_and_token_gated():
    server = FakeServer()
    register_recovery_tools(
        server,
        FakeWorkspaceRecoveryClient(),
        state_service=FakeStateService(),
    )
    artifact = server.tools["state_snapshot_create"]("memory", "primary")
    assert artifact["adapter_id"] == "memory"
    token = server.tools["state_snapshot_prepare_restore"]("state-1", 300)
    assert token["token"] == "state-token"
    result = server.tools["state_snapshot_restore"]("state-1", "state-token")
    assert result["restored"] is True
    assert "confirm" not in server.tools["state_snapshot_restore"].__annotations__
