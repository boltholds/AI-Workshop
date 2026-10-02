from __future__ import annotations

import json

import pytest

from ai_workshop.recovery.server_projects import RetainedRunRecovery


class Workspace:
    def __init__(self, run_id, project_id, path, commit_id="a"*40, writable=True):
        self.run_id=run_id
        self.project_id=project_id
        self.path=path
        self.commit_id=commit_id
        self.writable=writable


class Workspaces:
    def __init__(self, workspace):
        self.workspace=workspace

    def get(self, run_id):
        assert run_id == self.workspace.run_id
        return self.workspace


class Storage:
    def __init__(self, root):
        self.root=root

    def resolve_run_path(self, run_id, relative):
        target=(self.root/run_id/relative).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


class Store:
    def __init__(self, root):
        self.root=root
        root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, snapshot_id, project_id):
        p=self.root/snapshot_id/project_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def existing_project_dir(self, snapshot_id, project_id):
        p=self.root/snapshot_id/project_id
        if not p.is_dir():
            raise FileNotFoundError
        return p


def test_run_workspace_restore_rejects_project_mismatch(tmp_path):
    path=tmp_path/"runs"/"run-1"/"workspace"
    path.mkdir(parents=True)
    workspace=Workspace("run-1","project-a",path)
    recovery=RetainedRunRecovery(
        Workspaces(workspace),
        Storage(tmp_path/"runs"),
        Store(tmp_path/"snapshots"),
    )
    snapshot=recovery.snapshot("run-1")

    workspace.project_id="project-b"

    with pytest.raises(ValueError, match="project identity mismatch"):
        recovery.preview_restore(snapshot["snapshot_id"])


def test_retained_run_round_trip(tmp_path):
    path=tmp_path/"runs"/"run-1"/"workspace"
    path.mkdir(parents=True)
    (path/"note.txt").write_text("before")
    workspace=Workspace("run-1","project-a",path)
    recovery=RetainedRunRecovery(
        Workspaces(workspace),
        Storage(tmp_path/"runs"),
        Store(tmp_path/"snapshots"),
    )
    snapshot=recovery.snapshot("run-1")
    (path/"note.txt").write_text("after")

    confirmation=recovery.prepare_restore(snapshot["snapshot_id"])
    recovery.restore(snapshot["snapshot_id"], confirmation.token)

    assert (path/"note.txt").read_text() == "before"
