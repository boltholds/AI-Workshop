from __future__ import annotations

from ai_workshop.mcp_runtime.models import (
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.registry import McpRegistryStore
from ai_workshop.recovery.server_identity import IdentityConfigurationRecovery
from ai_workshop.recovery.server_mcp import McpRegistryRecovery
from ai_workshop.recovery.store import SnapshotStore


def test_scoped_server_backup_restore_preserves_unselected_state(tmp_path):
    snapshots=SnapshotStore(tmp_path/"snapshots")

    identity=tmp_path/"state"/"identity.json"
    config=tmp_path/"state"/"server.json"
    project=tmp_path/"projects"/"demo"/"source.py"
    browser=tmp_path/"browser"/"trace.json"
    identity.parent.mkdir(parents=True)
    project.parent.mkdir(parents=True)
    browser.parent.mkdir(parents=True)

    identity.write_text('{"principal":"before"}')
    config.write_text('{"mode":"before"}')
    project.write_text("project-before")
    browser.write_text("browser-before")

    identity_recovery=IdentityConfigurationRecovery(
        files={"identity":identity,"config":config},
        store=snapshots,
        forbidden_roots=(tmp_path/"secrets",tmp_path/"ca"),
    )

    registry=McpRegistryStore(tmp_path/"mcp.json")
    registry.register(
        McpRegistration(
            server_id="docs",
            display_name="Docs",
            transport=McpTransportKind.HTTP,
            scope=McpRegistrationScope.PROJECT,
            scope_id="demo",
            owner_principal_id="alice",
            state=McpServerState.RUNNING,
        )
    )
    mcp_recovery=McpRegistryRecovery(registry,snapshots)

    identity_snapshot=identity_recovery.snapshot()
    mcp_snapshot=mcp_recovery.snapshot()

    identity.write_text('{"principal":"after"}')
    config.write_text('{"mode":"after"}')
    project.write_text("project-after")
    browser.write_text("browser-after")
    registry.set_state("docs",McpServerState.FAILED)

    identity_token=identity_recovery.prepare_restore(
        identity_snapshot["snapshot_id"]
    )
    identity_recovery.restore(
        identity_snapshot["snapshot_id"],
        identity_token.token,
    )

    mcp_token=mcp_recovery.prepare_restore(
        mcp_snapshot["snapshot_id"]
    )
    mcp_recovery.restore(
        mcp_snapshot["snapshot_id"],
        mcp_token.token,
    )

    assert '"before"' in identity.read_text()
    assert '"before"' in config.read_text()
    assert registry.get("docs").registration.state is McpServerState.STOPPED

    # Unselected/protected domains are not rolled back by identity/MCP restore.
    assert project.read_text() == "project-after"
    assert browser.read_text() == "browser-after"
