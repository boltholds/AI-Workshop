from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from ai_workshop.browser.runtime import BrowserRuntime


class NavigateRequest(BaseModel):
    page_id: str
    url: str


class SelectorRequest(BaseModel):
    page_id: str
    selector: str


class TypeRequest(SelectorRequest):
    text: str


class ScrollRequest(BaseModel):
    page_id: str
    dx: float = 0
    dy: float = 0


class EvaluateRequest(BaseModel):
    page_id: str
    expression: str


def create_browser_app(runtime: BrowserRuntime, *, manage_lifecycle: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="AI Workshop Browser", docs_url=None, redoc_url=None, lifespan=lifespan if manage_lifecycle else None)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/pages/ensure")
    async def ensure_page():
        return {"page_id": await runtime.ensure_page()}

    @app.post("/v1/navigate")
    async def navigate(req: NavigateRequest):
        return {"url": await runtime.navigate(req.page_id, req.url)}

    @app.post("/v1/click")
    async def click(req: SelectorRequest):
        await runtime.click(req.page_id, req.selector)
        return {"ok": True}

    @app.post("/v1/type")
    async def type_text(req: TypeRequest):
        await runtime.type(req.page_id, req.selector, req.text)
        return {"ok": True}

    @app.post("/v1/scroll")
    async def scroll(req: ScrollRequest):
        await runtime.scroll(req.page_id, req.dx, req.dy)
        return {"ok": True}

    @app.post("/v1/evaluate")
    async def evaluate(req: EvaluateRequest):
        return {"value": await runtime.evaluate(req.page_id, req.expression)}

    @app.get("/v1/pages/{page_id}/console")
    async def console(page_id: str):
        return [event.model_dump(mode="json") for event in runtime.console_events(page_id)]

    @app.get("/v1/pages/{page_id}/network")
    async def network(page_id: str):
        return [event.model_dump(mode="json") for event in runtime.network_events(page_id)]

    return app
