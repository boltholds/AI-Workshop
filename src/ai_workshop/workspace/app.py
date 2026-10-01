from __future__ import annotations

from uuid import UUID
import hmac

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ai_workshop.config import WorkshopConfig
from ai_workshop.models.process import ExecRequest
from ai_workshop.workspace.filesystem import FilesystemService
from ai_workshop.workspace.git import GitService
from ai_workshop.workspace.paths import PathPolicy
from ai_workshop.workspace.processes import ProcessService


class FilePathRequest(BaseModel):
    project_id: str
    path: str


class FileWriteRequest(FilePathRequest):
    content: str


class FilePatchRequest(FilePathRequest):
    old: str
    new: str
    occurrence: int | None = None


class FileSearchRequest(BaseModel):
    project_id: str
    needle: str
    path: str = "."


class CancelRequest(BaseModel):
    run_id: UUID


def create_app(config: WorkshopConfig, *, host_paths: bool = False, workspace_token: str) -> FastAPI:
    policy = PathPolicy(config, host_paths=host_paths)
    files = FilesystemService(policy)
    processes = ProcessService(policy)
    git = GitService(processes)
    if not workspace_token:
        raise ValueError("workspace token must not be empty")
    app = FastAPI(title="AI Workshop Workspace", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def workspace_auth(request: Request, call_next):
        if request.url.path.startswith("/v1/"):
            auth = request.headers.get("authorization", "")
            expected = f"Bearer {workspace_token}"
            if not hmac.compare_digest(auth, expected):
                return JSONResponse(
                    status_code=401,
                    content={"error": {"code": "UNAUTHORIZED", "message": "Valid workspace token required"}},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    @app.exception_handler(KeyError)
    @app.exception_handler(ValueError)
    def expected_error(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": {"code": "WORKSPACE_ERROR", "message": str(exc)}})

    @app.exception_handler(PermissionError)
    def permission_error(_request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "WORKSPACE_READ_ONLY", "message": str(exc)}},
        )

    @app.exception_handler(Exception)
    def unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "Workspace request failed"}})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/projects")
    def projects() -> dict[str, list[str]]:
        return {"projects": [p.project_id for p in config.projects]}

    @app.get("/v1/files/list")
    def file_list(project_id: str, path: str = ".") -> dict[str, list[str]]:
        return {"entries": files.list(project_id, path)}

    @app.post("/v1/files/read")
    def file_read(request: FilePathRequest) -> dict[str, str]:
        return {"content": files.read(request.project_id, request.path)}

    @app.post("/v1/files/write")
    def file_write(request: FileWriteRequest) -> dict[str, bool]:
        files.write(request.project_id, request.path, request.content)
        return {"ok": True}

    @app.post("/v1/files/patch")
    def file_patch(request: FilePatchRequest) -> dict[str, bool]:
        files.patch(request.project_id, request.path, request.old, request.new, occurrence=request.occurrence)
        return {"ok": True}

    @app.post("/v1/files/search")
    def file_search(request: FileSearchRequest) -> dict[str, list[dict[str, object]]]:
        return {"matches": files.search(request.project_id, request.needle, request.path)}

    @app.post("/v1/shell/exec")
    def shell_exec(request: ExecRequest) -> dict[str, object]:
        return processes.exec(request).model_dump(mode="json")

    @app.post("/v1/shell/cancel")
    def shell_cancel(request: CancelRequest) -> dict[str, bool]:
        return {"cancelled": processes.cancel(request.run_id)}

    @app.get("/v1/git/status")
    def git_status(project_id: str) -> dict[str, str]:
        return git.status(project_id).model_dump()

    @app.get("/v1/git/diff")
    def git_diff(project_id: str, staged: bool = False) -> dict[str, str]:
        return {"diff": git.diff(project_id, staged=staged)}

    return app
