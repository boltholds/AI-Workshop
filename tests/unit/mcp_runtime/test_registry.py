from __future__ import annotations

from ai_workshop.mcp_runtime.models import (
    McpDiscoveredCapabilities,
    McpRegistration,
    McpRegistrationScope,
    McpServerState,
    McpToolDescriptor,
    McpTransportKind,
)
from ai_workshop.mcp_runtime.registry import McpRegistryStore


def _registration(server_id: str, *, owner: str = "alice", scope=McpRegistrationScope.PROJECT, scope_id="demo"):
    return McpRegistration(
        server_id=server_id,
        display_name=server_id,
        transport=McpTransportKind.HTTP,
        scope=scope,
        scope_id=scope_id,
        owner_principal_id=owner,
        permissions=frozenset({"filesystem.read"}),
    )


def test_registry_round_trip_and_state(tmp_path):
    path = tmp_path / "mcp.json"
    registry = McpRegistryStore(path)
    registry.register(_registration("docs"))
    registry.set_state("docs", McpServerState.RUNNING)
    registry.update_capabilities(
        "docs",
        McpDiscoveredCapabilities(
            server_id="docs",
            revision=1,
            tools=(McpToolDescriptor(name="search"),),
        ),
    )

    loaded = McpRegistryStore(path).get("docs")

    assert loaded.registration.state is McpServerState.RUNNING
    assert loaded.capabilities.revision == 1
    assert loaded.capabilities.tools[0].name == "search"


def test_registry_rejects_duplicate_server_id(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(_registration("docs"))

    try:
        registry.register(_registration("docs"))
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration accepted")


def test_registration_removal_requires_owner(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(_registration("docs", owner="alice"))

    try:
        registry.remove("docs", actor_principal_id="mallory")
    except PermissionError as exc:
        assert "owner required" in str(exc)
    else:
        raise AssertionError("non-owner removed registration")

    assert registry.get("docs").registration.owner_principal_id == "alice"


def test_run_scope_cleanup_removes_only_matching_run(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(_registration("run-a", scope=McpRegistrationScope.RUN, scope_id="run-1"))
    registry.register(_registration("run-b", scope=McpRegistrationScope.RUN, scope_id="run-2"))
    registry.register(_registration("project", scope=McpRegistrationScope.PROJECT, scope_id="demo"))

    removed = registry.remove_scope("run", "run-1")

    assert removed == ("run-a",)
    assert [item.registration.server_id for item in registry.list()] == ["project", "run-b"]


def test_capability_revision_must_increase(tmp_path):
    registry = McpRegistryStore(tmp_path / "mcp.json")
    registry.register(_registration("docs"))
    registry.update_capabilities(
        "docs",
        McpDiscoveredCapabilities(server_id="docs", revision=1),
    )

    try:
        registry.update_capabilities(
            "docs",
            McpDiscoveredCapabilities(server_id="docs", revision=1),
        )
    except ValueError as exc:
        assert "must increase" in str(exc)
    else:
        raise AssertionError("stale capability revision accepted")


def test_global_scope_requires_global_scope_id():
    try:
        _registration("global", scope=McpRegistrationScope.GLOBAL, scope_id="anything")
    except ValueError as exc:
        assert "scope_id must be global" in str(exc)
    else:
        raise AssertionError("invalid global scope accepted")
