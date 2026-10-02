from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from ai_workshop.gateway.recovery_tools import register_recovery_tools
from ai_workshop.recovery.reset import ResetService
from ai_workshop.recovery.server_domains import ServerRecoveryRegistry


class FakeServer:
    def __init__(self):
        self.tools={}

    def tool(self,*args,**kwargs):
        def decorate(fn):
            self.tools[fn.__name__]=fn
            return fn
        return decorate


class Workspace:
    def snapshot_create(self,*args,**kwargs): return {}
    def snapshot_preview_restore(self,*args,**kwargs): return {}
    def snapshot_prepare_restore(self,*args,**kwargs): return {}
    def snapshot_restore(self,*args,**kwargs): return {}


class Domain:
    domain_id="identity-config"

    def preview_snapshot(self,target_id): return {"target_id":target_id}
    def snapshot(self,target_id): return {"snapshot_id":"s1","target_id":target_id}
    def preview_restore(self,snapshot_id): return {"snapshot_id":snapshot_id}
    def prepare_restore(self,snapshot_id,ttl_seconds=300.0):
        class Token:
            def model_dump(self): return {"token":"confirm"}
        return Token()
    def restore(self,snapshot_id,confirmation_token):
        if confirmation_token != "confirm":
            raise PermissionError("confirmation required")
        return {"snapshot_id":snapshot_id}


def test_reset_scopes_exclude_secret_and_ca_state(tmp_path):
    project=tmp_path/"projects"/"demo"
    cache=tmp_path/"cache"
    runtime=tmp_path/"runs-runtime"
    secrets=tmp_path/"state"/"credentials"
    ca=tmp_path/"state"/"ca-private"
    for path in (project,cache,runtime,secrets,ca):
        path.mkdir(parents=True)

    service=ResetService(
        cache_paths=[cache],
        browser_artifact_paths=[],
        state_resetters={},
        infrastructure_resetter=None,
        project_roots=[project],
        run_runtime_paths=[runtime],
        protected_paths=[secrets,ca],
    )

    assert service.allowed_scopes() == ("cache","browser-artifacts","run-runtime")
    for scope in service.allowed_scopes():
        plan=service.plan(scope)
        assert str(secrets.resolve()) not in plan.filesystem_paths
        assert str(ca.resolve()) not in plan.filesystem_paths


def test_reset_rejects_configured_path_overlapping_protected_state(tmp_path):
    protected=tmp_path/"state"/"ca-private"
    protected.mkdir(parents=True)

    with pytest.raises(ValueError, match="protected state"):
        ResetService(
            cache_paths=[protected],
            browser_artifact_paths=[],
            state_resetters={},
            infrastructure_resetter=None,
            project_roots=[],
            protected_paths=[protected],
        )


def test_server_recovery_restore_requires_confirmation_argument():
    server=FakeServer()
    register_recovery_tools(
        server,
        Workspace(),
        server_recovery_registry=ServerRecoveryRegistry((Domain(),)),
    )

    params=inspect.signature(server.tools["server_recovery_restore"]).parameters
    assert "confirmation_token" in params
    assert "confirm" not in params
    assert "force" not in params

    with pytest.raises(RuntimeError, match="confirmation required"):
        server.tools["server_recovery_restore"](
            "identity-config",
            "s1",
            "wrong",
        )
