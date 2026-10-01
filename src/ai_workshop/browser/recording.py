from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import cv2

from ai_workshop.browser.artifacts import ArtifactStore
from ai_workshop.browser.frames import FrameSample
from ai_workshop.browser.models import ArtifactRef, CaptureRegion, PageRegion
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
