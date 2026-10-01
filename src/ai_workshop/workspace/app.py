from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ai_workshop.config import WorkshopConfig
from ai_workshop.models.process import ExecRequest
from ai_workshop.workspace.filesystem import FilesystemService
from ai_workshop.workspace.git import GitService
from ai_workshop.workspace.paths import PathPolicy
from ai_workshop.workspace.processes import ProcessService


class PathRequest(BaseModel):
    project_id: str
    path: str = "."


class ReadRequest(PathRequest):
    max_bytes: int = Field(default=1_048_576, gt=0, le=16_777_216)


class WriteRequest(PathRequest):
    content: str


class PatchRequest(PathRequest):
    expected: str
    replacement: str
    occurrence: int | None = Field(default=None, ge=1)


class SearchRequest(PathRequest):
    query: str


class CancelRequest(BaseModel):
    run_id: UUID


def _message(exc: Exception) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def create_workspace_app(config: WorkshopConfig) -> FastAPI:
    paths = PathPolicy(config)
    files = FilesystemService(paths, config)
    processes = ProcessService(paths)
    git = GitService(processes)
    app = FastAPI(title="AI Workshop Workspace", docs_url=None, redoc_url=None)

    @app.exception_handler(ValueError)
    @app.exception_handler(KeyError)
    @app.exception_handler(PermissionError)
    @app.exception_handler(FileNotFoundError)
    @app.exception_handler(NotADirectoryError)
    async def expected_error(_: Request, exc: Exception) -> JSONResponse:
        code = "PERMISSION_DENIED" if isinstance(exc, PermissionError) else "INVALID_REQUEST"
        return JSONResponse(status_code=403 if isinstance(exc, PermissionError) else 400, content={"error": {"code": code, "message": _message(exc)}})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/projects")
    def projects() -> list[dict[str, str]]:
        return [{"id": key, "mode": config.projects[key].mode} for key in sorted(config.projects)]

    @app.post("/v1/files/list")
    def list_files(req: PathRequest):
        return [item.model_dump() for item in files.list(req.project_id, req.path)]

    @app.post("/v1/files/read")
    def read_file(req: ReadRequest):
        return {"content": files.read(req.project_id, req.path, max_bytes=req.max_bytes)}

    @app.post("/v1/files/write")
    def write_file(req: WriteRequest):
        files.write(req.project_id, req.path, req.content)
        return {"ok": True}

    @app.post("/v1/files/patch")
    def patch_file(req: PatchRequest):
        files.patch(req.project_id, req.path, req.expected, req.replacement, occurrence=req.occurrence)
        return {"ok": True}

    @app.post("/v1/files/search")
    def search_files(req: SearchRequest):
        return [item.model_dump() for item in files.search(req.project_id, req.query, relative_path=req.path)]

    @app.post("/v1/shell/exec")
    async def shell_exec(req: ExecRequest):
        return (await processes.exec(req)).model_dump(mode="json")

    @app.post("/v1/shell/cancel")
    async def shell_cancel(req: CancelRequest):
        return {"cancelled": await processes.cancel(req.run_id)}

    @app.get("/v1/git/status/{project_id}")
    def git_status(project_id: str):
        return git.status(project_id).model_dump()

    @app.get("/v1/git/diff/{project_id}")
    def git_diff(project_id: str, staged: bool = False):
        return {"diff": git.diff(project_id, staged=staged)}

    return app
