from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import cv2

from ai_workshop.browser.artifacts import ArtifactStore
from ai_workshop.browser.frames import FrameSample
from ai_workshop.browser.models import ArtifactRef, CaptureRegion, PageRegion, SelectorRegion
from ai_workshop.browser.regions import resolve_region


@dataclass(slots=True)
class RecordingRequest:
    region: CaptureRegion = field(default_factory=PageRegion)


@dataclass(slots=True)
class CaptureSession:
    session_id: str
    page: object
    context: object
    browser: object
    video: object
    source_url: str
    viewport: dict[str, int] | None
    region: CaptureRegion
    resolved_clip: dict[str, float | int] | None = None


@dataclass(slots=True)
class RecordingArtifact:
    session_id: str
    video: ArtifactRef
    source_url: str
    viewport: dict[str, int] | None
    region: CaptureRegion
    resolved_clip: dict[str, float | int] | None = None


class RecordingService:
    def __init__(self, artifact_root: Path):
        self.store = ArtifactStore(artifact_root)
        self._sessions: dict[str, CaptureSession] = {}
        self._completed: dict[str, RecordingArtifact] = {}

    def start(self, runtime, request: RecordingRequest | None = None) -> CaptureSession:
        request = request or RecordingRequest()
        session_id = str(uuid4())
        source_page = runtime.page()
        source_url = source_page.url
        viewport = source_page.viewport_size
        state = runtime.context().storage_state(indexed_db=True)
        browser = runtime.browser_type().launch(headless=runtime.headless, executable_path=runtime.executable_path)
        context = browser.new_context(storage_state=state, viewport=viewport, record_video_dir=str(self.store.session_dir(session_id)))
        page = context.new_page()
        if source_url and source_url != "about:blank":
            page.goto(source_url, wait_until="domcontentloaded")
        resolved = resolve_region(page, request.region)
        if isinstance(request.region, SelectorRegion):
            self._start_selector_tracking(page, request.region.selector)
        if page.video is None:
            context.close(); browser.close()
            raise RuntimeError("Playwright did not create a video recorder")
        session = CaptureSession(
            session_id=session_id, page=page, context=context, browser=browser, video=page.video,
            source_url=source_url, viewport=viewport, region=request.region, resolved_clip=resolved.clip,
        )
        self._sessions[session_id] = session
        return session

    def page(self, session_id: str):
        try:
            return self._sessions[session_id].page
        except KeyError as exc:
            raise KeyError(f"unknown recording session: {session_id}") from exc

    def stop(self, session_id: str) -> RecordingArtifact:
        completed = self._completed.get(session_id)
        if completed is not None:
            return completed
        try:
            session = self._sessions.pop(session_id)
        except KeyError as exc:
            raise KeyError(f"unknown recording session: {session_id}") from exc
        try:
            if isinstance(session.region, SelectorRegion):
                tracked_clip = self._stop_selector_tracking(session.page, session.viewport)
                if tracked_clip is not None:
                    session.resolved_clip = tracked_clip
            session.context.close()
            source = Path(session.video.path())
            destination = self.store.path(session_id, "recording.webm")
            if source != destination:
                shutil.move(str(source), destination)
        finally:
            session.browser.close()
        artifact = RecordingArtifact(
            session_id=session_id,
            video=ArtifactRef(id=session_id, media_type="video/webm", path=f"{session_id}/recording.webm"),
            source_url=session.source_url, viewport=session.viewport, region=session.region, resolved_clip=session.resolved_clip,
        )
        self._completed[session_id] = artifact
        return artifact


    @staticmethod
    def _start_selector_tracking(page, selector: str) -> None:
        page.evaluate(
            """selector => {
                window.__aiWorkshopSelectorRects = [];
                const sample = () => {
                    const elements = document.querySelectorAll(selector);
                    if (elements.length === 1) {
                        const r = elements[0].getBoundingClientRect();
                        window.__aiWorkshopSelectorRects.push({
                            x: r.x,
                            y: r.y,
                            width: r.width,
                            height: r.height,
                        });
                    }
                    window.__aiWorkshopSelectorTracker = requestAnimationFrame(sample);
                };
                sample();
            }""",
            selector,
        )

    @staticmethod
    def _stop_selector_tracking(page, viewport: dict[str, int] | None) -> dict[str, float] | None:
        try:
            rects = page.evaluate(
                """() => {
                    if (window.__aiWorkshopSelectorTracker !== undefined) {
                        cancelAnimationFrame(window.__aiWorkshopSelectorTracker);
                    }
                    return window.__aiWorkshopSelectorRects || [];
                }"""
            )
        except Exception:
            return None
        if not rects:
            return None

        valid = [
            rect for rect in rects
            if float(rect.get("width", 0)) > 0 and float(rect.get("height", 0)) > 0
        ]
        if not valid:
            return None

        x0 = min(float(rect["x"]) for rect in valid)
        y0 = min(float(rect["y"]) for rect in valid)
        x1 = max(float(rect["x"]) + float(rect["width"]) for rect in valid)
        y1 = max(float(rect["y"]) + float(rect["height"]) for rect in valid)

        if viewport is not None:
            x0 = max(0.0, min(x0, float(viewport["width"])))
            y0 = max(0.0, min(y0, float(viewport["height"])))
            x1 = max(x0, min(x1, float(viewport["width"])))
            y1 = max(y0, min(y1, float(viewport["height"])))

        if x1 <= x0 or y1 <= y0:
            return None
        return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def decode_video(path: Path, *, frames_dir: Path | None = None) -> list[FrameSample]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot decode video: {path}")
    frames: list[FrameSample] = []
    index = 0
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    try:
        while True:
            ok, bgr = capture.read()
            if not ok:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp <= 0 and index:
                timestamp = index * 1000.0 / fps
            sample = FrameSample(timestamp_ms=int(round(timestamp)), image=rgb)
            frames.append(sample)
            if frames_dir is not None:
                frames_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(frames_dir / f"{index:06d}.png"), bgr)
            index += 1
    finally:
        capture.release()
    if not frames:
        raise ValueError(f"video contains no decodable frames: {path}")
    return frames
