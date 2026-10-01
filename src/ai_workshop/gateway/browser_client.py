from __future__ import annotations

from typing import Any

import httpx

from ai_workshop.gateway.errors import GatewayError


def _sanitize_browser_error(response: httpx.Response) -> GatewayError:
    if response.status_code >= 500:
        return GatewayError("BROWSER_UNAVAILABLE", "Browser service could not complete the request")
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, dict):
            code = str(detail.get("code") or "BROWSER_ERROR")
            message = str(detail.get("message") or "Browser request failed")
        elif isinstance(detail, str):
            code = "BROWSER_ERROR"
            message = detail
        else:
            error = body.get("error", {})
            code = str(error.get("code") or "BROWSER_ERROR")
            message = str(error.get("message") or "Browser request failed")
    except Exception:
        code = "BROWSER_ERROR"
        message = "Browser request failed"
    if "Traceback" in message:
        message = "Browser request failed"
    return GatewayError(code, message)


class BrowserClient:
    def __init__(self, base_url: str, *, token: str, transport: httpx.BaseTransport | None = None, timeout: float = 120.0):
        if not token:
            raise ValueError("browser token must not be empty")
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise GatewayError("BROWSER_UNAVAILABLE", "Browser service could not be reached") from exc
        if response.is_error:
            raise _sanitize_browser_error(response)
        try:
            body = response.json()
        except Exception as exc:
            raise GatewayError("BROWSER_PROTOCOL_ERROR", "Browser response was invalid") from exc
        if not isinstance(body, dict):
            raise GatewayError("BROWSER_PROTOCOL_ERROR", "Browser response was invalid")
        return body

    @staticmethod
    def _required(body: dict[str, Any], field: str) -> Any:
        if field not in body:
            raise GatewayError("BROWSER_PROTOCOL_ERROR", "Browser response was invalid")
        return body[field]

    def navigate(self, url: str, *, session_id: str | None = None) -> str:
        body = self._request("POST", "/v1/navigate", json={"url": url, "session_id": session_id})
        return str(self._required(body, "url"))

    def click(self, selector: str, *, session_id: str | None = None) -> None:
        self._request("POST", "/v1/click", json={"selector": selector, "session_id": session_id})

    def type_text(self, selector: str, text: str, *, session_id: str | None = None) -> None:
        self._request("POST", "/v1/type", json={"selector": selector, "text": text, "session_id": session_id})

    def screenshot(self, region: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
        body = self._request("POST", "/v1/screenshot", json={"region": region, "session_id": session_id})
        return dict(self._required(body, "artifact"))

    def record_start(self, region: dict[str, Any]) -> str:
        body = self._request("POST", "/v1/record/start", json={"region": region})
        return str(self._required(body, "session_id"))

    def record_stop(self, session_id: str) -> dict[str, Any]:
        body = self._request("POST", "/v1/record/stop", json={"session_id": session_id})
        return dict(self._required(body, "recording"))

    def capture_diagnostics(self, session_id: str, **options: Any) -> dict[str, Any]:
        return self._request("POST", "/v1/diagnostics", json={"session_id": session_id, **options})

    def console_events(self) -> list[dict[str, Any]]:
        body = self._request("GET", "/v1/console")
        return list(self._required(body, "events"))

    def network_events(self) -> list[dict[str, Any]]:
        body = self._request("GET", "/v1/network")
        return list(self._required(body, "events"))

    def artifact_bytes(self, artifact: dict[str, Any]) -> bytes:
        path = str(artifact["path"])
        parts = path.split("/", 1)
        if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("invalid artifact path")
        try:
            response = self._client.get(f"/v1/artifacts/{parts[0]}/{parts[1]}")
        except httpx.RequestError as exc:
            raise GatewayError("BROWSER_UNAVAILABLE", "Browser service could not be reached") from exc
        if response.is_error:
            raise _sanitize_browser_error(response)
        return response.content
