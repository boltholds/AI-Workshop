from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import httpx


_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(slots=True)
class ForgeHttpError(Exception):
    code: str
    message: str
    status_code: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ForgeHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        default_headers: Mapping[str, str] | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        max_pages: int = 50,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0 or max_retries > 5:
            raise ValueError("max_retries must be between 0 and 5")
        if max_pages < 1 or max_pages > 500:
            raise ValueError("max_pages must be between 1 and 500")

        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("forge HTTP base URL must be HTTP(S)")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("forge HTTP base URL must not contain credentials")

        self.base_url = base_url.rstrip("/")
        self._origin = (
            parsed.scheme.lower(),
            parsed.hostname.lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
        self.default_headers = dict(default_headers or {})
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_pages = max_pages
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> Any:
        payload, _ = self._request_json(
            "GET",
            path,
            params=params,
        )
        return payload

    def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> Any:
        data, _ = self._request_json(
            "POST",
            path,
            json_payload=dict(payload),
        )
        return data

    def patch_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> Any:
        data, _ = self._request_json(
            "PATCH",
            path,
            json_payload=dict(payload),
        )
        return data

    def put_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> Any:
        data, _ = self._request_json(
            "PUT",
            path,
            json_payload=dict(payload),
        )
        return data

    def delete(
        self,
        path: str,
    ) -> None:
        self._request(
            "DELETE",
            path,
        )

    def get_paginated(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> list[dict[str, Any]]:
        current_url = path
        current_params: dict[str, str | int] | None = (
            dict(params) if params is not None else None
        )
        result: list[dict[str, Any]] = []

        for page_index in range(self.max_pages):
            payload, response = self._request_json(
                "GET",
                current_url,
                params=current_params,
            )
            if not isinstance(payload, list) or any(
                not isinstance(item, dict) for item in payload
            ):
                raise ForgeHttpError(
                    "FORGE_RESPONSE_INVALID",
                    "Forge provider returned an invalid paginated response",
                    status_code=response.status_code,
                )
            result.extend(dict(item) for item in payload)

            next_url = self._next_link(response)
            if next_url is not None:
                current_url = next_url
                current_params = None
                continue

            next_page = response.headers.get("X-Next-Page", "").strip()
            if next_page:
                current_url = path
                current_params = dict(params or {})
                current_params["page"] = next_page
                continue

            return result

        raise ForgeHttpError(
            "FORGE_PAGINATION_LIMIT",
            "Forge provider pagination limit exceeded",
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> tuple[Any, httpx.Response]:
        response = self._request(
            method,
            path,
            params=params,
            json_payload=json_payload,
        )
        if not response.content:
            return None, response
        try:
            return response.json(), response
        except Exception as exc:
            raise ForgeHttpError(
                "FORGE_RESPONSE_INVALID",
                "Forge provider returned an invalid JSON response",
                status_code=response.status_code,
            ) from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        method = method.upper()
        url = self._safe_url(path)
        attempts = self.max_retries + 1 if method in {"GET", "HEAD"} else 1

        for attempt in range(attempts):
            try:
                response = self.client.request(
                    method,
                    url,
                    params=params,
                    json=json_payload,
                    headers=self.default_headers,
                    timeout=self.timeout_seconds,
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                if attempt + 1 < attempts:
                    continue
                raise ForgeHttpError(
                    "FORGE_TIMEOUT",
                    "Forge provider request timed out",
                    retryable=True,
                ) from exc
            except httpx.HTTPError as exc:
                if attempt + 1 < attempts:
                    continue
                raise ForgeHttpError(
                    "FORGE_NETWORK_ERROR",
                    "Forge provider request failed",
                    retryable=True,
                ) from exc

            if 200 <= response.status_code < 300:
                return response

            retryable = response.status_code in _RETRYABLE_STATUS
            if retryable and attempt + 1 < attempts:
                continue
            raise ForgeHttpError(
                "FORGE_PROVIDER_ERROR",
                "Forge provider request failed",
                status_code=response.status_code,
                retryable=retryable,
            )

        raise AssertionError("unreachable forge request loop")

    def _safe_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            target = path
        else:
            target = urljoin(self.base_url + "/", path.lstrip("/"))
        parsed = urlsplit(target)
        origin = (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
        if origin != self._origin:
            raise ForgeHttpError(
                "FORGE_REDIRECT_REJECTED",
                "Forge provider pagination target changed origin",
            )
        return target

    @staticmethod
    def _next_link(response: httpx.Response) -> str | None:
        raw = response.headers.get("Link")
        if not raw:
            return None
        for part in raw.split(","):
            section = part.strip()
            if 'rel="next"' not in section and "rel=next" not in section:
                continue
            if not section.startswith("<") or ">" not in section:
                raise ForgeHttpError(
                    "FORGE_RESPONSE_INVALID",
                    "Forge provider returned an invalid pagination link",
                    status_code=response.status_code,
                )
            return section[1 : section.index(">")]
        return None
