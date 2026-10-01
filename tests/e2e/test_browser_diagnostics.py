from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import shutil

from ai_workshop.browser.diagnostics import DiagnosticOptions, DiagnosticService
from ai_workshop.browser.recording import RecordingService
from ai_workshop.browser.runtime import BrowserRuntime


def serve(directory: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, *args): pass
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    return server


def test_real_video_produces_dual_temporal_composites(tmp_path: Path):
    site=tmp_path/"site"; site.mkdir()
    (site/"index.html").write_text("""<!doctype html>
<style>#box{width:40px;height:40px;background:rgb(40,120,220);transition:transform .6s linear}</style>
<div id="box"></div>""",encoding="utf-8")
    server=serve(site)
    runtime=BrowserRuntime(tmp_path/"profile",executable_path=shutil.which("chromium"))
    try:
        runtime.start(); runtime.navigate(f"http://127.0.0.1:{server.server_port}/")
        recordings=RecordingService(tmp_path/"artifacts")
        session=recordings.start(runtime)
        session.page.wait_for_timeout(150)
        session.page.evaluate('document.querySelector("#box").style.transform="translateX(180px)"')
        session.page.wait_for_timeout(900)
        recording=recordings.stop(session.session_id)
        result=DiagnosticService(tmp_path/"artifacts").build(recording,DiagnosticOptions(variants="both",max_fps=8))
        names={Path(a.path).name for a in result.artifacts}
        assert {"recording.webm","composite-neutral.png","composite-time-gradient.png","metadata.json"} <= names
        assert (tmp_path/"artifacts"/session.session_id/"composite-neutral.png").stat().st_size > 0
    finally:
        runtime.stop(); server.shutdown()
