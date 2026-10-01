import asyncio
from pathlib import Path

from ai_workshop.browser.runtime import BrowserRuntime

HTML = """<!doctype html><html><body><button id='btn'>Click</button><input id='name'><script>
console.log('page-ready');
document.querySelector('#btn').addEventListener('click', () => { document.body.dataset.clicked='yes'; });
</script></body></html>"""


def test_runtime_interact_and_capture_console(tmp_path: Path) -> None:
    async def scenario():
        runtime = BrowserRuntime(tmp_path / "profile", headless=True)
        await runtime.start()
        try:
            page_id = await runtime.ensure_page()
            await runtime.get_page(page_id).set_content(HTML)
            await runtime.type(page_id, "#name", "Grace")
            await runtime.click(page_id, "#btn")
            assert await runtime.evaluate(page_id, "document.body.dataset.clicked") == "yes"
            assert any("page-ready" in event.text for event in runtime.console_events(page_id))
            assert runtime.network_events(page_id) == ()
        finally:
            await runtime.stop()
    asyncio.run(scenario())


def test_profile_survives_restart(tmp_path: Path) -> None:
    async def scenario():
        profile = tmp_path / "profile"
        first = BrowserRuntime(profile, headless=True)
        await first.start()
        await first.context.add_cookies([{"name": "session", "value": "abc", "url": "https://workshop.test"}])
        await first.stop()
        second = BrowserRuntime(profile, headless=True)
        await second.start()
        try:
            cookies = await second.context.cookies("https://workshop.test")
            assert any(cookie["name"] == "session" and cookie["value"] == "abc" for cookie in cookies)
        finally:
            await second.stop()
    asyncio.run(scenario())
