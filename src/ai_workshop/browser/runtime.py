from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright


class BrowserRuntime:
    def __init__(self, profile_dir: Path, *, headless: bool = True, executable_path: Path | str | None = None):
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.executable_path = str(executable_path) if executable_path is not None else None
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._console_events: list[dict[str, Any]] = []
        self._network_events: list[dict[str, Any]] = []

    def start(self) -> None:
        if self._context is not None:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            executable_path=self.executable_path,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._attach_page(self._page)
        self._context.on("page", self._attach_page)

    def stop(self) -> None:
        context, playwright = self._context, self._playwright
        self._page = None
        self._context = None
        self._playwright = None
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()

    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("browser runtime is not started")
        return self._context

    def browser_type(self):
        if self._playwright is None:
            raise RuntimeError("browser runtime is not started")
        return self._playwright.chromium

    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("browser runtime is not started")
        return self._page

    def navigate(self, url: str) -> None:
        self.page().goto(url, wait_until="domcontentloaded")

    def console_events(self) -> list[dict[str, Any]]:
        return list(self._console_events)

    def network_events(self) -> list[dict[str, Any]]:
        return list(self._network_events)

    def _attach_page(self, page: Page) -> None:
        self._page = page
        page.on("console", lambda message: self._console_events.append({"type": message.type, "text": message.text}))
        page.on("request", lambda request: self._network_events.append(
            {"url": request.url, "method": request.method, "resource_type": request.resource_type}
        ))
