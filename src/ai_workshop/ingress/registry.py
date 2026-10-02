from __future__ import annotations

import json
from pathlib import Path
import threading

from ai_workshop.ingress.models import IngressRoute
from ai_workshop.ingress.protocol import RuntimeEndpointAuthority
from ai_workshop.server.models import RuntimeEndpoint


class IngressRouteRegistry:
    def __init__(
        self,
        *,
        endpoint_authority: RuntimeEndpointAuthority,
        state_path: Path,
    ):
        self.endpoint_authority = endpoint_authority
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self._routes: dict[str, IngressRoute] = {}
        self._hostnames: dict[str, str] = {}
        self._load()

    def publish(
        self,
        route_id: str,
        *,
        hostname: str,
        endpoint: RuntimeEndpoint,
    ) -> IngressRoute:
        route = IngressRoute(
            route_id=route_id,
            hostname=hostname,
            endpoint=endpoint,
        )
        self._require_issued_endpoint(route.endpoint)

        with self._lock:
            if route.route_id in self._routes:
                raise ValueError(f"route already exists: {route.route_id}")
            owner = self._hostnames.get(route.hostname)
            if owner is not None:
                raise ValueError(
                    f"hostname already published by route: {owner}"
                )

            self._routes[route.route_id] = route
            self._hostnames[route.hostname] = route.route_id
            try:
                self._persist()
            except Exception:
                self._routes.pop(route.route_id, None)
                self._hostnames.pop(route.hostname, None)
                raise
            return route

    def unpublish(self, route_id: str) -> None:
        with self._lock:
            route = self._routes.get(route_id)
            if route is None:
                raise KeyError(f"unknown ingress route: {route_id}")
            self._routes.pop(route_id)
            self._hostnames.pop(route.hostname, None)
            try:
                self._persist()
            except Exception:
                self._routes[route_id] = route
                self._hostnames[route.hostname] = route_id
                raise

    def get(self, route_id: str) -> IngressRoute:
        with self._lock:
            route = self._routes.get(route_id)
            if route is None:
                raise KeyError(f"unknown ingress route: {route_id}")
            return route

    def list(self) -> list[IngressRoute]:
        with self._lock:
            return [self._routes[key] for key in sorted(self._routes)]

    def _require_issued_endpoint(self, endpoint: RuntimeEndpoint) -> None:
        try:
            issued = self.endpoint_authority.require(
                endpoint.workload_id,
                endpoint.container_port,
            )
        except Exception as exc:
            raise ValueError(
                "ingress target must be a controller-issued runtime endpoint"
            ) from exc
        if issued != endpoint:
            raise ValueError(
                "ingress target must be a controller-issued runtime endpoint"
            )

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported ingress route registry version")
        raw_routes = payload.get("routes", [])
        if not isinstance(raw_routes, list):
            raise ValueError("ingress routes must be a list")

        for raw in raw_routes:
            route = IngressRoute.model_validate(raw)
            self._require_issued_endpoint(route.endpoint)
            if route.route_id in self._routes:
                raise ValueError("duplicate ingress route id")
            if route.hostname in self._hostnames:
                raise ValueError("duplicate ingress hostname")
            self._routes[route.route_id] = route
            self._hostnames[route.hostname] = route.route_id

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "routes": [
                self._routes[key].model_dump(mode="json")
                for key in sorted(self._routes)
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
