from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ai_workshop.analysis.engine import AnalysisEngine


class ExecRequest(BaseModel):
    project_id: str
    argv: list[str]
    timeout_seconds: float = Field(default=30, ge=1, le=900)


class CargoRequest(BaseModel):
    project_id: str
    manifest_path: str = 'Cargo.toml'
    timeout_seconds: float = Field(default=300, ge=1, le=900)


class BinaryRequest(BaseModel):
    project_id: str
    path: str


def create_analysis_app(engine: AnalysisEngine, *, token: str) -> FastAPI:
    if not token:
        raise ValueError('analysis worker token must be set')
    app = FastAPI(title='AI Workshop Analysis Worker', docs_url=None, redoc_url=None)

    @app.middleware('http')
    async def auth(request: Request, call_next):
        if request.url.path.startswith('/v1/'):
            if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
                return JSONResponse(status_code=401, content={'error': 'unauthorized'})
        return await call_next(request)

    @app.exception_handler(ValueError)
    def invalid_request(_request: Request, _exc: ValueError):
        return JSONResponse(status_code=400, content={'error': 'invalid or unavailable project operation'})

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/v1/shell/exec')
    def shell_exec(request: ExecRequest):
        return engine.shell_exec(request.project_id, request.argv, request.timeout_seconds)

    @app.post('/v1/cargo/test')
    def cargo_test(request: CargoRequest):
        return engine.cargo_test(request.project_id, request.manifest_path, request.timeout_seconds)

    @app.post('/v1/binary/analyze')
    def binary_analyze(request: BinaryRequest):
        return engine.binary_analyze(request.project_id, request.path)

    @app.get('/v1/binary/results/{project_id}/{analysis_id}')
    def results(project_id: str, analysis_id: str):
        return engine.analysis_get_results(project_id, analysis_id)

    return app


def load_app() -> FastAPI:
    return create_analysis_app(
        AnalysisEngine(
            projects_root=Path(os.environ.get('AI_WORKSHOP_PROJECTS_ROOT', '/workspace/projects')),
            results_root=Path(os.environ.get('AI_WORKSHOP_ANALYSIS_RESULTS', '/analysis')),
        ),
        token=os.environ['AI_WORKSHOP_ANALYSIS_TOKEN'],
    )
