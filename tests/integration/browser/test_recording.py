import asyncio
import os
from pathlib import Path

import pytest

from ai_workshop.browser.recording import RecordingRequest, RecordingService
from ai_workshop.browser.regions import PageRegion
from ai_workshop.browser.runtime import BrowserRuntime


def _playwright_ffmpeg_available() -> bool:
    root = Path(os.getenv("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache/ms-playwright"))
    return any(root.glob("ffmpeg-*/ffmpeg-linux"))


HTML = """<!doctype html><html><body>
<div id='box' style='width:50px;height:50px;background:red'></div>
<script>window.step = () => { document.querySelector('#box').style.transform = 'translateX(120px)'; };</script>
</body></html>"""


@pytest.mark.skipif(not _playwright_ffmpeg_available(), reason="Playwright FFmpeg helper unavailable in execution sandbox")
def test_recording_is_explicit_and_flushes_webm(tmp_path: Path) -> None:
    async def scenario():
        runtime = BrowserRuntime(tmp_path / "profile", headless=True)
        await runtime.start()
        try:
            page_id = await runtime.ensure_page()
            page = runtime.get_page(page_id)
            await page.set_viewport_size({"width": 320, "height": 240})
            await page.set_content(HTML)
            artifacts = tmp_path / "artifacts"
            assert not list(artifacts.rglob("*.webm")) if artifacts.exists() else True

            service = RecordingService(runtime, artifacts)
            session = await service.start(RecordingRequest(page_id=page_id, region=PageRegion()))
            record_page = service.page(session.id)
            await record_page.set_content(HTML)
            await record_page.evaluate("window.step()")
            await record_page.wait_for_timeout(250)
            result = await service.stop(session.id)

            assert Path(result.path).exists()
            assert Path(result.path).suffix == ".webm"
            assert Path(result.path).stat().st_size > 0
            assert result.source_url == "about:blank"
            assert result.viewport == {"width": 320, "height": 240}
            assert result.region.kind == "page"
        finally:
            await runtime.stop()

    asyncio.run(scenario())
