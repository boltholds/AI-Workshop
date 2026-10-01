from pathlib import Path
import shutil
from ai_workshop.browser.runtime import BrowserRuntime

def chromium_path(): return shutil.which("chromium")

def virtual_site(runtime,html):
    def handler(route):
        if route.request.url.endswith("/ping.txt"): route.fulfill(status=200,body="pong",content_type="text/plain")
        else: route.fulfill(status=200,body=html,content_type="text/html")
    runtime.page().route("https://workshop.test/**",handler)

def test_runtime_navigates_and_captures_console_network(tmp_path: Path):
    runtime=BrowserRuntime(tmp_path/"profile",executable_path=chromium_path())
    try:
        runtime.start(); virtual_site(runtime,'<script>console.log("hello-console"); fetch("/ping.txt")</script>')
        runtime.navigate("https://workshop.test/"); runtime.page().wait_for_timeout(100)
        assert any("hello-console" in e["text"] for e in runtime.console_events())
        assert any("/ping.txt" in e["url"] for e in runtime.network_events())
    finally: runtime.stop()

def test_profile_survives_restart(tmp_path: Path):
    profile=tmp_path/"profile"; html='<script>if (!localStorage.getItem("token")) localStorage.setItem("token","saved"); if (!document.cookie) document.cookie="session=alive; path=/";</script>'
    first=BrowserRuntime(profile,executable_path=chromium_path()); first.start(); virtual_site(first,html); first.navigate("https://workshop.test/"); first.stop()
    second=BrowserRuntime(profile,executable_path=chromium_path())
    try:
        second.start(); virtual_site(second,html); second.navigate("https://workshop.test/")
        assert second.page().evaluate('localStorage.getItem("token")')=="saved"
        assert "session=alive" in second.page().evaluate("document.cookie")
    finally: second.stop()
