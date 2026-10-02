from __future__ import annotations

from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.registry import McpRegistryStore
from ai_workshop.recovery.server_mcp import McpRegistryRecovery
from ai_workshop.recovery.store import SnapshotStore


def registration(server_id: str, state=McpServerState.RUNNING):
    return McpRegistration(
        server_id=server_id,
        display_name=server_id,
        transport=McpTransportKind.HTTP,
        scope=McpRegistrationScope.PROJECT,
        scope_id="demo",
        owner_principal_id="alice",
        state=state,
    )


def test_mcp_registry_restore_returns_servers_stopped(tmp_path):
    registry=McpRegistryStore(tmp_path/"mcp.json")
    registry.register(registration("docs", McpServerState.RUNNING))
    recovery=McpRegistryRecovery(
        registry,
        SnapshotStore(tmp_path/"snapshots"),
    )
    snapshot=recovery.snapshot()

    registry.set_state("docs", McpServerState.FAILED)

    confirmation=recovery.prepare_restore(snapshot["snapshot_id"])
    recovery.restore(snapshot["snapshot_id"], confirmation.token)

    assert registry.get("docs").registration.state is McpServerState.STOPPED


def test_mcp_registry_metadata_round_trip(tmp_path):
    registry=McpRegistryStore(tmp_path/"mcp.json")
    registry.register(registration("docs"))
    recovery=McpRegistryRecovery(
        registry,
        SnapshotStore(tmp_path/"snapshots"),
    )
    snapshot=recovery.snapshot()

    registry.remove("docs", actor_principal_id="alice")
    assert registry.list() == []

    confirmation=recovery.prepare_restore(snapshot["snapshot_id"])
    recovery.restore(snapshot["snapshot_id"], confirmation.token)

    assert [r.registration.server_id for r in registry.list()] == ["docs"]
