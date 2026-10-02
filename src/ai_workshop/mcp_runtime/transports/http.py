from __future__ import annotations

from ipaddress import ip_address
import socket
from urllib.parse import urlsplit

import httpx


_PROTECTED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}
_PROTECTED_IPS = {
    "169.254.169.254",
    "100.100.100.200",
}


class McpHttpEndpointPolicy:
    def __init__(
        self,
        *,
        allowed_internal_hosts: frozenset[str] = frozenset(),
    ):
        self.allowed_internal_hosts = frozenset(
            host.lower() for host in allowed_internal_hosts
        )

    def validate(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MCP HTTP endpoint must be HTTP(S)")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("MCP HTTP endpoint must not contain credentials")

        host = parsed.hostname.lower()
        if host in self.allowed_internal_hosts:
            return url
        if host in _PROTECTED_HOSTS:
            raise ValueError("MCP HTTP endpoint is protected")

        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    host,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise ValueError("MCP HTTP endpoint could not be resolved") from exc

        for raw in addresses:
            if raw in _PROTECTED_IPS:
                raise ValueError("MCP HTTP endpoint is protected")
            address = ip_address(raw)
            if (
                address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_unspecified
                or address.is_private
            ):
                raise ValueError("MCP HTTP endpoint is outside network policy")
        return url


class HttpMcpTransport:
    def __init__(
        self,
        *,
        endpoint_policy: McpHttpEndpointPolicy,
        endpoint_for,
        client_factory=None,
    ):
        self.endpoint_policy = endpoint_policy
        self.endpoint_for = endpoint_for
        self.client_factory = client_factory or (
            lambda url: httpx.Client(base_url=url, timeout=20.0)
        )
        self._clients: dict[str, object] = {}

    def start(self, registration):
        url = self.endpoint_policy.validate(
            self.endpoint_for(registration)
        )
        client = self.client_factory(url)
        self._clients[registration.server_id] = client
        return client

    def stop(self, server_id: str) -> None:
        client = self._clients.pop(server_id, None)
        if client is not None and hasattr(client, "close"):
            client.close()
