from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import shutil
from ai_workshop.browser.recording import RecordingService
from ai_workshop.browser.runtime import BrowserRuntime

def serve(directory):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(directory),**kwargs)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler); Thread(target=server.serve_forever,daemon=True).start(); return server

def test_recording_is_explicit_and_produces_webm(tmp_path: Path):
    site=tmp_path/"site"; site.mkdir(); (site/"index.html").write_text('<div id="box">box</div>',encoding="utf-8")
    server=serve(site); runtime=BrowserRuntime(tmp_path/"profile",executable_path=shutil.which("chromium"))
    try:
        runtime.start(); runtime.navigate(f"http://127.0.0.1:{server.server_port}/")
        service=RecordingService(tmp_path/"artifacts"); session=service.start(runtime)
        session.page.evaluate('document.querySelector("#box").style.transform="translateX(100px)"'); session.page.wait_for_timeout(300)
        artifact=service.stop(session.session_id); video=tmp_path/"artifacts"/artifact.video.path
        assert video.exists() and video.stat().st_size>0
    finally: runtime.stop(); server.shutdown()


def test_selector_recording_tracks_union_of_element_motion(tmp_path: Path):
    from ai_workshop.browser.models import SelectorRegion
    from ai_workshop.browser.recording import RecordingRequest

    site=tmp_path/"moving-site"; site.mkdir()
    (site/"index.html").write_text(
        '<style>#box{position:absolute;left:10px;top:20px;width:40px;height:30px;background:red}</style><div id="box"></div>',
        encoding="utf-8",
    )
    server=serve(site); runtime=BrowserRuntime(tmp_path/"profile-moving",executable_path=shutil.which("chromium"))
    try:
        runtime.start(); runtime.navigate(f"http://127.0.0.1:{server.server_port}/")
        service=RecordingService(tmp_path/"artifacts-moving")
        session=service.start(runtime, RecordingRequest(region=SelectorRegion(selector="#box")))
        session.page.wait_for_timeout(120)
        session.page.evaluate('document.querySelector("#box").style.left="210px"')
        session.page.wait_for_timeout(180)
        artifact=service.stop(session.session_id)
        assert artifact.resolved_clip is not None
        assert artifact.resolved_clip["x"] <= 10
        assert artifact.resolved_clip["width"] >= 240
    finally:
        runtime.stop(); server.shutdown()
