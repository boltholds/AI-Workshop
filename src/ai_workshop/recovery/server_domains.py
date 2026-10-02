from __future__ import annotations

from typing import Protocol


class ServerRecoveryDomain(Protocol):
    domain_id: str

    def preview_snapshot(self, target_id: str) -> dict[str, object]: ...
    def snapshot(self, target_id: str) -> dict[str, object]: ...
    def preview_restore(self, snapshot_id: str) -> dict[str, object]: ...
    def restore(self, snapshot_id: str, confirmation_token: str) -> dict[str, object]: ...


class ServerRecoveryRegistry:
    def __init__(self, domains: tuple[ServerRecoveryDomain, ...] = ()):
        self._domains: dict[str, ServerRecoveryDomain] = {}
        for domain in domains:
            self.register(domain)

    def register(self, domain: ServerRecoveryDomain) -> None:
        domain_id = getattr(domain, "domain_id", "")
        if not domain_id:
            raise ValueError("server recovery domain requires domain_id")
        if domain_id in self._domains:
            raise ValueError(f"server recovery domain already registered: {domain_id}")
        self._domains[domain_id] = domain

    def require(self, domain_id: str) -> ServerRecoveryDomain:
        domain = self._domains.get(domain_id)
        if domain is None:
            raise KeyError(f"unknown server recovery domain: {domain_id}")
        return domain

    def list(self) -> list[str]:
        return sorted(self._domains)
