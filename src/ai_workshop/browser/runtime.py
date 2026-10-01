from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from ai_workshop.browser.models import ConsoleEvent, NetworkEvent, utcnow


class BrowserRuntime:
    def __init__(self, profile_dir: Path, *, headless: bool = True, chromium_executable: str | None = None) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.chromium_executable = chromium_executable or self._discover_chromium()
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._pages: dict[str, Page] = {}
        self._page_ids: dict[int, str] = {}
        self._console: dict[str, list[ConsoleEvent]] = {}
        self._network: dict[str, list[NetworkEvent]] = {}

    @staticmethod
    def _discover_chromium() -> str | None:
        configured = os.getenv("AI_WORKSHOP_CHROMIUM_EXECUTABLE")
        if configured:
            return configured
        for candidate in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

    async def start(self) -> None:
        if self._context is not None:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        kwargs: dict[str, object] = {"user_data_dir": str(self.profile_dir), "headless": self.headless, "args": ["--no-sandbox"]}
        if self.chromium_executable:
            kwargs["executable_path"] = self.chromium_executable
        self._context = await self._playwright.chromium.launch_persistent_context(**kwargs)
        for page in self._context.pages:
            self._register_page(page)
        self._context.on("page", self._register_page)

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._pages.clear()
        self._page_ids.clear()

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("browser runtime is not started")
        return self._context

    def _register_page(self, page: Page) -> str:
        identity = id(page)
        existing = self._page_ids.get(identity)
        if existing:
            return existing
        page_id = str(uuid4())
        self._page_ids[identity] = page_id
        self._pages[page_id] = page
        self._console[page_id] = []
        self._network[page_id] = []
        page.on("console", lambda message, pid=page_id: self._console[pid].append(ConsoleEvent(level=message.type, text=message.text, timestamp=utcnow())))
        page.on("request", lambda request, pid=page_id: self._network[pid].append(NetworkEvent(method=request.method, url=request.url, resource_type=request.resource_type, timestamp=utcnow())))
        return page_id

    async def ensure_page(self) -> str:
        if self._pages:
            return next(iter(self._pages))
        page = await self.context.new_page()
        return self._register_page(page)

    def get_page(self, page_id: str) -> Page:
        try:
            return self._pages[page_id]
        except KeyError as exc:
            raise KeyError(f"unknown browser page: {page_id}") from exc

    async def navigate(self, page_id: str, url: str) -> str:
        response = await self.get_page(page_id).goto(url, wait_until="domcontentloaded")
        return response.url if response else self.get_page(page_id).url

    async def click(self, page_id: str, selector: str) -> None:
        await self.get_page(page_id).locator(selector).click()

    async def type(self, page_id: str, selector: str, text: str) -> None:
        await self.get_page(page_id).locator(selector).fill(text)

    async def scroll(self, page_id: str, dx: float, dy: float) -> None:
        await self.get_page(page_id).mouse.wheel(dx, dy)

    async def evaluate(self, page_id: str, expression: str):
        return await self.get_page(page_id).evaluate(expression)

    def console_events(self, page_id: str) -> tuple[ConsoleEvent, ...]:
        self.get_page(page_id)
        return tuple(self._console[page_id])

    def network_events(self, page_id: str) -> tuple[NetworkEvent, ...]:
        self.get_page(page_id)
        return tuple(self._network[page_id])
