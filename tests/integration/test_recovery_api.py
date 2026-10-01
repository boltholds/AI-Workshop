from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.app import create_app


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_workspace_recovery_api_round_trip(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "value.txt").write_text("before\n", encoding="utf-8")
    git(root, "add", "value.txt")
    git(root, "commit", "-m", "initial")

    config = WorkshopConfig(projects=[
        ProjectMount(project_id="project", host=root, container="/workspace/project", mode="rw")
    ])
    client = TestClient(
        create_app(
            config,
            host_paths=True,
            workspace_token="secret",
            state_root=tmp_path / "state",
        ),
        headers={"Authorization": "Bearer secret"},
    )

    created = client.post("/v1/recovery/snapshots", json={"project_id": "project"})
    assert created.status_code == 200
    snapshot_id = created.json()["snapshot"]["snapshot_id"]

    (root / "value.txt").write_text("after\n", encoding="utf-8")
    preview = client.get(f"/v1/recovery/snapshots/{snapshot_id}/restore-preview")
    assert preview.status_code == 200
    assert "value.txt" in preview.json()["preview"]["reset_paths"]

    prepared = client.post(
        f"/v1/recovery/snapshots/{snapshot_id}/restore-prepare",
        json={"ttl_seconds": 300},
    )
    token = prepared.json()["confirmation"]["token"]

    restored = client.post(
        f"/v1/recovery/snapshots/{snapshot_id}/restore",
        json={"confirmation_token": token},
    )
    assert restored.status_code == 200
    assert (root / "value.txt").read_text(encoding="utf-8") == "before\n"
