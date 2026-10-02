from pathlib import Path

from fastapi.testclient import TestClient

from ai_workshop.server.app import create_server_app
from ai_workshop.server.config import ServerModeConfig


class FakeRuntime:
    pass


def test_server_control_plane_has_private_health_endpoint(tmp_path: Path):
    app = create_server_app(
        ServerModeConfig(storage_root=tmp_path / "storage"),
        state_root=tmp_path / "state",
        runtime_controller=FakeRuntime(),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
