from __future__ import annotations

from pathlib import Path
import threading
from typing import Mapping, Sequence

import httpx
from fastapi import FastAPI, Request
from starlette.responses import Response

from ai_workshop.ingress.models import IngressRoute


_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ProxyAdapter:
    def __init__(
        self,
        *,
        allowed_target_hosts: frozenset[str] = frozenset({"rootless-runtime"}),
        timeout_seconds: float = 60.0,
    ):
        if not allowed_target_hosts:
            raise ValueError("at least one target host must be allowed")
        self.allowed_target_hosts = allowed_target_hosts
        self.timeout_seconds = timeout_seconds
        self._lock = threading.RLock()
        self._routes: dict[str, IngressRoute] = {}
        self._certificates: dict[str, tuple[Path, Path]] = {}
        self.app = FastAPI(
            title="AI Workshop Ingress",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        self._register_routes()

    def apply(
        self,
        routes: Sequence[IngressRoute],
        certificates: Mapping[str, tuple[Path, Path]],
    ) -> None:
        next_routes: dict[str, IngressRoute] = {}
        for route in routes:
            if route.endpoint.host not in self.allowed_target_hosts:
                raise ValueError("ingress target host is not allowed")
            if route.hostname in next_routes:
                raise ValueError(f"duplicate hostname: {route.hostname}")
            next_routes[route.hostname] = route

        unknown_certificates = set(certificates) - set(next_routes)
        if unknown_certificates:
            raise ValueError("certificate binding has no ingress route")

        next_certificates = {
            hostname: (Path(paths[0]), Path(paths[1]))
            for hostname, paths in certificates.items()
        }
        with self._lock:
            self._routes = next_routes
            self._certificates = next_certificates

    def route_for_hostname(self, hostname: str) -> IngressRoute | None:
        normalized = hostname.lower().rstrip(".")
        with self._lock:
            return self._routes.get(normalized)

    def certificate_bindings(self) -> dict[str, tuple[Path, Path]]:
        with self._lock:
            return dict(self._certificates)

    def _register_routes(self) -> None:
        methods = [
            "GET",
            "HEAD",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ]

        @self.app.api_route("/", methods=methods)
        async def proxy_root(request: Request) -> Response:
            return await self._proxy(request)

        @self.app.api_route("/{path:path}", methods=methods)
        async def proxy_path(path: str, request: Request) -> Response:
            return await self._proxy(request)

    async def _proxy(self, request: Request) -> Response:
        hostname = self._request_hostname(request)
        route = self.route_for_hostname(hostname)
        if route is None:
            return Response(
                content=b"Unknown ingress hostname",
                status_code=421,
                media_type="text/plain",
            )

        endpoint = route.endpoint
        path = request.url.path or "/"
        query = request.url.query
        target = f"http://{endpoint.host}:{endpoint.host_port}{path}"
        if query:
            target += f"?{query}"

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS
            and key.lower() != "host"
        }
        headers["x-forwarded-host"] = hostname
        headers["x-forwarded-proto"] = request.url.scheme

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
            ) as client:
                upstream = await client.request(
                    request.method,
                    target,
                    headers=headers,
                    content=await request.body(),
                )
        except httpx.HTTPError:
            return Response(
                content=b"Upstream service unavailable",
                status_code=502,
                media_type="text/plain",
            )

        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS
            and key.lower() != "content-length"
        }
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    @staticmethod
    def _request_hostname(request: Request) -> str:
        raw = request.headers.get("host", "")
        if not raw:
            return ""
        if raw.startswith("["):
            return ""
        return raw.split(":", 1)[0].lower().rstrip(".")
