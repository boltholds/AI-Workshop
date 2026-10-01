from pathlib import Path

from ai_workshop.browser.models import PageRegion
from ai_workshop.browser.recording import CaptureSession, RecordingService


class FakeContext:
    def close(self): pass
class FakeBrowser:
    def close(self): pass
class FakeVideo:
    def __init__(self,path): self._path=path
    def path(self): return str(self._path)


def test_record_stop_is_idempotent_for_followup_diagnostics(tmp_path: Path):
    service=RecordingService(tmp_path)
    source=tmp_path/"raw.webm"; source.write_bytes(b"video")
    service._sessions["s1"]=CaptureSession(
        session_id="s1",page=object(),context=FakeContext(),browser=FakeBrowser(),video=FakeVideo(source),
        source_url="https://example.test",viewport={"width":100,"height":80},region=PageRegion(),
    )
    first=service.stop("s1")
    second=service.stop("s1")
    assert second == first
    assert (tmp_path/"s1"/"recording.webm").read_bytes() == b"video"
