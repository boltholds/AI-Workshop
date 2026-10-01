from pathlib import Path
from ai_workshop.browser.models import CoordinateRegion
from ai_workshop.browser.screenshots import ScreenshotService

class FakePage:
    viewport_size={"width":800,"height":600}
    def screenshot(self,**kwargs):
        Path(kwargs["path"]).write_bytes(b"png"); self.kwargs=kwargs

def test_screenshot_service_writes_session_artifact(tmp_path: Path):
    page=FakePage(); artifact=ScreenshotService(tmp_path).capture(page,CoordinateRegion(x=10,y=20,width=30,height=40),session_id="abc")
    assert artifact.path=="abc/screenshot.png"
    assert page.kwargs["clip"]=={"x":10,"y":20,"width":30,"height":40}
    assert artifact.width==30 and artifact.height==40
