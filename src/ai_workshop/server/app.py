from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from ai_workshop.server.config import ServerModeConfig
from ai_workshop.server.factory import build_runtime_controller
from ai_workshop.server.runtime import RuntimeController


def create_server_app(
    config: ServerModeConfig,
    *,
    state_root: Path,
    runtime_controller: RuntimeController | None = None,
) -> FastAPI:
    controller = runtime_controller or build_runtime_controller(
        config,
        state_root=state_root,
    )
    app = FastAPI(
        title="AI Workshop Server Control Plane",
        docs_url=None,
        redoc_url=None,
    )
    app.state.runtime_controller = controller

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
