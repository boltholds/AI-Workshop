from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ai_workshop.browser.app import create_browser_app
from ai_workshop.browser.models import ConsoleEvent, NetworkEvent


class FakeRuntime:
    async def ensure_page(self): return "p1"
    async def navigate(self, page_id, url): return url
    async def click(self, page_id, selector): self.clicked = (page_id, selector)
    async def type(self, page_id, selector, text): self.typed = (page_id, selector, text)
    async def scroll(self, page_id, dx, dy): self.scrolled = (page_id, dx, dy)
    async def evaluate(self, page_id, expression): return "value"
    def console_events(self, page_id): return (ConsoleEvent(level="log", text="hello", timestamp=datetime.now(timezone.utc)),)
    def network_events(self, page_id): return (NetworkEvent(method="GET", url="https://example.test", resource_type="document", timestamp=datetime.now(timezone.utc)),)


def test_browser_private_api_routes_actions_and_events() -> None:
    runtime = FakeRuntime()
    client = TestClient(create_browser_app(runtime))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/v1/pages/ensure").json() == {"page_id": "p1"}
    assert client.post("/v1/navigate", json={"page_id": "p1", "url": "https://example.test"}).status_code == 200
    assert client.post("/v1/type", json={"page_id": "p1", "selector": "#x", "text": "abc"}).status_code == 200
    assert runtime.typed == ("p1", "#x", "abc")
    assert client.get("/v1/pages/p1/console").json()[0]["text"] == "hello"
    assert client.get("/v1/pages/p1/network").json()[0]["method"] == "GET"
