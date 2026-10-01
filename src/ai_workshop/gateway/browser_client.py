from __future__ import annotations

from typing import Any

import httpx

from ai_workshop.gateway.errors import sanitize_workspace_error


class BrowserClient:
    def __init__(self, base_url: str, *, transport: httpx.BaseTransport | None = None, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=timeout)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        if response.is_error:
            raise sanitize_workspace_error(response)
        return response.json()

    def navigate(self, url: str, *, session_id: str | None = None) -> str:
        return str(self._request("POST", "/v1/navigate", json={"url": url, "session_id": session_id})["url"])

    def click(self, selector: str, *, session_id: str | None = None) -> None:
        self._request("POST", "/v1/click", json={"selector": selector, "session_id": session_id})

    def type_text(self, selector: str, text: str, *, session_id: str | None = None) -> None:
        self._request("POST", "/v1/type", json={"selector": selector, "text": text, "session_id": session_id})

    def screenshot(self, region: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
        return dict(self._request("POST", "/v1/screenshot", json={"region": region, "session_id": session_id})["artifact"])

    def record_start(self, region: dict[str, Any]) -> str:
        return str(self._request("POST", "/v1/record/start", json={"region": region})["session_id"])

    def record_stop(self, session_id: str) -> dict[str, Any]:
        return dict(self._request("POST", "/v1/record/stop", json={"session_id": session_id})["recording"])

    def capture_diagnostics(self, session_id: str, **options: Any) -> dict[str, Any]:
        return self._request("POST", "/v1/diagnostics", json={"session_id": session_id, **options})

    def console_events(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/console")["events"])

    def network_events(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v1/network")["events"])

    def artifact_bytes(self, artifact: dict[str, Any]) -> bytes:
        path = str(artifact["path"])
        parts = path.split("/", 1)
        if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("invalid artifact path")
        response = self._client.get(f"/v1/artifacts/{parts[0]}/{parts[1]}")
        if response.is_error:
            raise sanitize_workspace_error(response)
        return response.content
