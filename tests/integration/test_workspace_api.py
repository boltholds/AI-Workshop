from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.app import create_app


def make_client(tmp_path: Path) -> TestClient:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=tmp_path, container="/workspace/p", mode="rw")])
    return TestClient(
        create_app(cfg, host_paths=True, workspace_token="test-token"),
        headers={"Authorization": "Bearer test-token"},
    )


def test_health_and_project_listing(tmp_path: Path):
    client = make_client(tmp_path)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/v1/projects").json() == {"projects": ["p"]}


def test_filesystem_shell_and_git_status(tmp_path: Path):
    client = make_client(tmp_path)
    response = client.post("/v1/files/write", json={"project_id": "p", "path": "a.txt", "content": "hello"})
    assert response.status_code == 200
    assert client.post("/v1/files/read", json={"project_id": "p", "path": "a.txt"}).json()["content"] == "hello"
    shell = client.post("/v1/shell/exec", json={"project_id": "p", "argv": ["python", "-c", 'print("ok")']}).json()
    assert shell["stdout"].strip() == "ok"
    git = client.get("/v1/git/status", params={"project_id": "p"}).json()
    assert "a.txt" in git["porcelain"]


def test_api_sanitizes_internal_failure(tmp_path: Path):
    client = make_client(tmp_path)
    response = client.post("/v1/files/read", json={"project_id": "p", "path": "../escape"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "WORKSPACE_ERROR"
    assert "Traceback" not in body["error"]["message"]


def test_v1_requires_workspace_bearer_token(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=tmp_path, container="/workspace/p", mode="rw")])
    client = TestClient(create_app(cfg, host_paths=True, workspace_token="secret"))
    response = client.get("/v1/projects")
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "UNAUTHORIZED", "message": "Valid workspace token required"}}


def test_health_does_not_require_token(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=tmp_path, container="/workspace/p", mode="rw")])
    client = TestClient(create_app(cfg, host_paths=True, workspace_token="secret"))
    assert client.get("/health").json() == {"status": "ok"}
