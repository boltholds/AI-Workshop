from __future__ import annotations

import pytest

from ai_workshop.recovery.server_domains import ServerRecoveryRegistry


class Domain:
    def __init__(self, domain_id: str):
        self.domain_id = domain_id


def test_domain_registry_lists_sorted_ids():
    registry = ServerRecoveryRegistry((Domain("projects"), Domain("identity")))

    assert registry.list() == ["identity", "projects"]


def test_domain_registry_rejects_collision():
    registry = ServerRecoveryRegistry((Domain("identity"),))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(Domain("identity"))


def test_domain_registry_rejects_unknown_domain():
    registry = ServerRecoveryRegistry()

    with pytest.raises(KeyError, match="unknown server recovery domain"):
        registry.require("missing")
