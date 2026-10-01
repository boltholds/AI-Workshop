import asyncio
from pathlib import Path

from PIL import Image

from ai_workshop.browser.regions import CoordinateRegion, PageRegion, SelectorRegion
from ai_workshop.browser.runtime import BrowserRuntime
from ai_workshop.browser.screenshots import ScreenshotRequest, ScreenshotService

HTML = """<!doctype html><html><head><style>
html, body { margin: 0; padding: 0; }
body { width: 1280px; min-height: 1200px; background: white; }
#target { position:absolute; left:100px; top:120px; width:120px; height:80px; background:#123456; }
#bottom { position:absolute; top:1100px; width:10px; height:10px; }
</style></head><body><div id='target'></div><div id='bottom'></div></body></html>"""


def image_size(path: str) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def test_screenshot_viewport_fullpage_selector_and_coordinates(tmp_path: Path) -> None:
    async def scenario():
        runtime = BrowserRuntime(tmp_path / "profile", headless=True)
        await runtime.start()
        try:
            page_id = await runtime.ensure_page()
            page = runtime.get_page(page_id)
            await page.set_viewport_size({"width": 640, "height": 480})
            await page.set_content(HTML)
            service = ScreenshotService(runtime, tmp_path / "artifacts")

            viewport = await service.capture(ScreenshotRequest(page_id=page_id, region=PageRegion()))
            assert (viewport.width, viewport.height) == (640, 480)
            assert image_size(viewport.path) == (640, 480)

            full = await service.capture(ScreenshotRequest(page_id=page_id, region=PageRegion(full_page=True)))
            assert full.width == 1280
            assert full.height >= 1200
            assert image_size(full.path) == (full.width, full.height)

            selector = await service.capture(ScreenshotRequest(page_id=page_id, region=SelectorRegion(selector="#target")))
            assert (selector.width, selector.height) == (120, 80)
            assert image_size(selector.path) == (120, 80)

            coords = await service.capture(ScreenshotRequest(page_id=page_id, region=CoordinateRegion(x=10, y=20, width=50, height=40)))
            assert (coords.width, coords.height) == (50, 40)
            assert image_size(coords.path) == (50, 40)
            assert selector.media_type == "image/png"
            assert Path(selector.path).parent.parent == tmp_path / "artifacts"
        finally:
            await runtime.stop()

    asyncio.run(scenario())
