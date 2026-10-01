from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ai_workshop.browser.diagnostics import DiagnosticOptions
from ai_workshop.browser.engine import BrowserEngine
from ai_workshop.browser.models import CoordinateRegion, PageRegion, SelectorRegion
from ai_workshop.browser.worker import BrowserWorker

Region = Annotated[PageRegion | SelectorRegion | CoordinateRegion, Field(discriminator="kind")]


class NavigateRequest(BaseModel):
    url: str
    session_id: str | None = None


class ClickRequest(BaseModel):
    selector: str
    session_id: str | None = None


class TypeRequest(ClickRequest):
    text: str


class ScrollRequest(BaseModel):
    dx: int = 0
    dy: int = 0
    session_id: str | None = None


class EvaluateRequest(BaseModel):
    expression: str
    session_id: str | None = None


class ScreenshotRequest(BaseModel):
    region: Region = Field(default_factory=PageRegion)
    session_id: str | None = None


class RecordingStartRequest(BaseModel):
    region: Region = Field(default_factory=PageRegion)


class RecordingStopRequest(BaseModel):
    session_id: str


class DiagnosticsRequest(RecordingStopRequest):
    variants: Literal["neutral", "time-gradient", "both"] = "neutral"
    legend: bool = False
    sensitivity: Literal["auto", "low", "medium", "high"] = "auto"
    max_fps: float = Field(default=10.0, gt=0)
    keep_frames: bool = False


def create_browser_app(profile_dir: Path, artifact_root: Path, *, executable_path: Path | str | None = None, worker: BrowserWorker | None = None) -> FastAPI:
    artifact_root = Path(artifact_root).resolve()
    worker = worker or BrowserWorker(lambda: BrowserEngine(profile_dir, artifact_root, executable_path=executable_path))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="AI Workshop Browser", docs_url=None, redoc_url=None, lifespan=lifespan)

    def invoke(method: str, *args: Any, **kwargs: Any):
        try:
            return worker.call(method, *args, **kwargs)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except Exception:
            raise HTTPException(status_code=500, detail="Browser request failed") from None

    @app.get("/health")
    def health(): return {"status": "ok"}

    @app.post("/v1/navigate")
    def navigate(request: NavigateRequest): return {"url": invoke("navigate", request.url, session_id=request.session_id)}

    @app.post("/v1/click")
    def click(request: ClickRequest):
        invoke("click", request.selector, session_id=request.session_id); return {"ok": True}

    @app.post("/v1/type")
    def type_text(request: TypeRequest):
        invoke("type_text", request.selector, request.text, session_id=request.session_id); return {"ok": True}

    @app.post("/v1/scroll")
    def scroll(request: ScrollRequest):
        invoke("scroll", request.dx, request.dy, session_id=request.session_id); return {"ok": True}

    @app.post("/v1/evaluate")
    def evaluate(request: EvaluateRequest): return {"value": invoke("evaluate", request.expression, session_id=request.session_id)}

    @app.get("/v1/console")
    def console(): return {"events": invoke("console_events")}

    @app.get("/v1/network")
    def network(): return {"events": invoke("network_events")}

    @app.post("/v1/screenshot")
    def screenshot(request: ScreenshotRequest):
        result = invoke("screenshot", request.region, session_id=request.session_id)
        return {"artifact": result.model_dump()}

    @app.post("/v1/record/start")
    def record_start(request: RecordingStartRequest): return {"session_id": invoke("recording_start", request.region)}

    @app.post("/v1/record/stop")
    def record_stop(request: RecordingStopRequest):
        result = invoke("recording_stop", request.session_id)
        return {"recording": result.video.model_dump()}

    @app.post("/v1/diagnostics")
    def diagnostics(request: DiagnosticsRequest):
        result = invoke("capture_diagnostics", request.session_id, DiagnosticOptions(
            variants=request.variants, legend=request.legend, sensitivity=request.sensitivity,
            max_fps=request.max_fps, keep_frames=request.keep_frames,
        ))
        return {"session_id": result.session_id, "artifacts": [a.model_dump() for a in result.artifacts]}

    @app.get("/v1/artifacts/{session_id}/{name}")
    def artifact(session_id: str, name: str):
        target = (artifact_root / session_id / name).resolve()
        try:
            target.relative_to(artifact_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid artifact path") from None
        if not target.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(target)

    return app
