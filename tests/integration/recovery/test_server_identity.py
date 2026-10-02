from __future__ import annotations

import json

from ai_workshop.recovery.server_identity import IdentityConfigurationRecovery
from ai_workshop.recovery.store import SnapshotStore


def test_identity_restore_does_not_touch_projects(tmp_path):
    identity=tmp_path/"state"/"identity.json"
    config=tmp_path/"state"/"server.json"
    project=tmp_path/"projects"/"demo"/"file.txt"
    identity.parent.mkdir(parents=True)
    project.parent.mkdir(parents=True)
    identity.write_text('{"version":1,"principals":["before"]}')
    config.write_text('{"mode":"before"}')
    project.write_text("project-before")

    recovery=IdentityConfigurationRecovery(
        files={"identity":identity,"server-config":config},
        store=SnapshotStore(tmp_path/"snapshots"),
        forbidden_roots=(tmp_path/"secrets", tmp_path/"ca"),
    )
    snapshot=recovery.snapshot()

    identity.write_text('{"version":1,"principals":["after"]}')
    config.write_text('{"mode":"after"}')
    project.write_text("project-after")

    confirmation=recovery.prepare_restore(snapshot["snapshot_id"])
    recovery.restore(snapshot["snapshot_id"], confirmation.token)

    assert json.loads(identity.read_text())["principals"] == ["before"]
    assert json.loads(config.read_text())["mode"] == "before"
    assert project.read_text() == "project-after"


def test_identity_backup_rejects_secret_state_path(tmp_path):
    secret=tmp_path/"secrets"/"credentials.json"
    secret.parent.mkdir(parents=True)
    secret.write_text("{}")

    try:
        IdentityConfigurationRecovery(
            files={"credentials":secret},
            store=SnapshotStore(tmp_path/"snapshots"),
            forbidden_roots=(tmp_path/"secrets",),
        )
    except ValueError as exc:
        assert "forbidden secret state" in str(exc)
    else:
        raise AssertionError("secret state accepted into identity backup")
