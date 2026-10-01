from __future__ import annotations

from pathlib import Path

from ai_workshop.browser.diagnostics import DiagnosticOptions, DiagnosticResult, DiagnosticService
from ai_workshop.browser.models import ArtifactRef, CaptureRegion
from ai_workshop.browser.recording import RecordingArtifact, RecordingRequest, RecordingService
from ai_workshop.browser.runtime import BrowserRuntime
from ai_workshop.browser.screenshots import ScreenshotService


class BrowserEngine:
    def __init__(self, profile_dir: Path, artifact_root: Path, *, executable_path: Path | str | None = None, headless: bool = True):
        self.runtime = BrowserRuntime(profile_dir, executable_path=executable_path, headless=headless)
        self.screenshots = ScreenshotService(artifact_root)
        self.recordings = RecordingService(artifact_root)
        self.diagnostics = DiagnosticService(artifact_root)

    def start(self) -> None:
        self.runtime.start()

    def stop(self) -> None:
        self.runtime.stop()

    def _page(self, session_id: str | None = None):
        return self.recordings.page(session_id) if session_id else self.runtime.page()

    def navigate(self, url: str, *, session_id: str | None = None) -> str:
        page = self._page(session_id)
        page.goto(url, wait_until="domcontentloaded")
        return page.url

    def click(self, selector: str, *, session_id: str | None = None) -> None:
        self._page(session_id).locator(selector).click()

    def type_text(self, selector: str, text: str, *, session_id: str | None = None) -> None:
        self._page(session_id).locator(selector).fill(text)

    def scroll(self, dx: int, dy: int, *, session_id: str | None = None) -> None:
        self._page(session_id).evaluate("([dx,dy]) => window.scrollBy(dx,dy)", [dx, dy])

    def evaluate(self, expression: str, *, session_id: str | None = None):
        return self._page(session_id).evaluate(expression)

    def console_events(self):
        return self.runtime.console_events()

    def network_events(self):
        return self.runtime.network_events()

    def screenshot(self, region: CaptureRegion, *, session_id: str | None = None) -> ArtifactRef:
        return self.screenshots.capture(self._page(session_id), region, session_id=session_id)

    def recording_start(self, region: CaptureRegion) -> str:
        return self.recordings.start(self.runtime, RecordingRequest(region=region)).session_id

    def recording_stop(self, session_id: str) -> RecordingArtifact:
        return self.recordings.stop(session_id)

    def capture_diagnostics(self, session_id: str, options: DiagnosticOptions) -> DiagnosticResult:
        return self.diagnostics.build(self.recordings.stop(session_id), options)
