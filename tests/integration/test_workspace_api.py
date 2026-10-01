import sys
from pathlib import Path

from fastapi.testclient import TestClient

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.app import create_workspace_app


def make_client(root: Path) -> TestClient:
    cfg = WorkshopConfig(projects={
        "app": ProjectMount(project_id="app", host=root, container=root.as_posix(), mode="rw")
    })
    return TestClient(create_workspace_app(cfg))


def test_health_projects_files_shell_and_structured_errors(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    (root / "hello.txt").write_text("hello", encoding="utf-8")
    client = make_client(root)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/v1/projects").json() == [{"id": "app", "mode": "rw"}]
    assert client.post("/v1/files/read", json={"project_id": "app", "path": "hello.txt"}).json()["content"] == "hello"
    write = client.post("/v1/files/write", json={"project_id": "app", "path": "new.txt", "content": "new"})
    assert write.status_code == 200
    shell = client.post("/v1/shell/exec", json={"project_id": "app", "argv": [sys.executable, "-c", "print('ok')"]})
    assert shell.status_code == 200
    assert shell.json()["stdout"].strip() == "ok"
    error = client.post("/v1/files/read", json={"project_id": "app", "path": "../escape"})
    assert error.status_code == 400
    assert error.json() == {"error": {"code": "INVALID_REQUEST", "message": "path escapes project root"}}
    assert "Traceback" not in error.text
