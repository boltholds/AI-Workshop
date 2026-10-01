from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel

from ai_workshop.browser.regions import CaptureRegion, CoordinateRegion, PageRegion, ResolvedRegion, SelectorRegion
from ai_workshop.browser.runtime import BrowserRuntime


class RecordingRequest(BaseModel):
    page_id: str
    region: PageRegion | SelectorRegion | CoordinateRegion
    session_id: str | None = None


class CaptureSession(BaseModel):
    id: str
    source_url: str
    viewport: dict[str, int]
    region: ResolvedRegion


class RecordingArtifact(BaseModel):
    id: str
    path: str
    media_type: str = "video/webm"
    source_url: str
    viewport: dict[str, int]
    region: ResolvedRegion


@dataclass
class _ActiveRecording:
    session: CaptureSession
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page


class RecordingService:
    def __init__(self, runtime: BrowserRuntime, artifacts_dir: Path) -> None:
        self._runtime = runtime
        self._artifacts_dir = artifacts_dir
        self._active: dict[str, _ActiveRecording] = {}

    async def start(self, request: RecordingRequest) -> CaptureSession:
        source_page = self._runtime.get_page(request.page_id)
        viewport = source_page.viewport_size
        if viewport is None:
            raise ValueError("source page viewport is unavailable")
        resolved = await CaptureRegion.resolve(source_page, request.region)
        session_id = request.session_id or str(uuid4())
        if session_id in self._active:
            raise ValueError(f"recording session already exists: {session_id}")
        directory = self._artifacts_dir / session_id
        directory.mkdir(parents=True, exist_ok=True)

        playwright = await async_playwright().start()
        launch_kwargs: dict[str, object] = {"headless": True, "args": ["--no-sandbox"]}
        if self._runtime.chromium_executable:
            launch_kwargs["executable_path"] = self._runtime.chromium_executable
        browser = await playwright.chromium.launch(**launch_kwargs)
        storage_state = await self._runtime.context.storage_state()
        context = await browser.new_context(
            viewport={"width": int(viewport["width"]), "height": int(viewport["height"])},
            storage_state=storage_state,
            record_video_dir=str(directory),
            record_video_size={"width": int(viewport["width"]), "height": int(viewport["height"])},
        )
        page = await context.new_page()
        source_url = source_page.url
        if source_url and source_url != "about:blank":
            await page.goto(source_url, wait_until="domcontentloaded")

        session = CaptureSession(
            id=session_id,
            source_url=source_url or "about:blank",
            viewport={"width": int(viewport["width"]), "height": int(viewport["height"])},
            region=resolved,
        )
        self._active[session_id] = _ActiveRecording(session, playwright, browser, context, page)
        return session

    def page(self, session_id: str) -> Page:
        try:
            return self._active[session_id].page
        except KeyError as exc:
            raise KeyError(f"unknown recording session: {session_id}") from exc

    async def stop(self, session_id: str) -> RecordingArtifact:
        try:
            active = self._active.pop(session_id)
        except KeyError as exc:
            raise KeyError(f"unknown recording session: {session_id}") from exc
        video = active.page.video
        if video is None:
            raise RuntimeError("recording page has no video")
        target = self._artifacts_dir / session_id / "recording.webm"
        try:
            await active.context.close()
            await video.save_as(str(target))
        finally:
            await active.browser.close()
            await active.playwright.stop()
        return RecordingArtifact(
            id=session_id,
            path=str(target),
            source_url=active.session.source_url,
            viewport=active.session.viewport,
            region=active.session.region,
        )
