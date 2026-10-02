from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_workshop.authn.tokens import ScopedTokenStore


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


def store(tmp_path: Path, clock: Clock | None = None) -> ScopedTokenStore:
    return ScopedTokenStore(
        tmp_path / "tokens.json",
        clock=clock,
    )


def test_token_issue_persists_only_hash_and_metadata(tmp_path: Path):
    tokens = store(tmp_path)

    issued = tokens.issue(
        principal_id="service-deploy",
        scopes=frozenset({"mcp.call", "runs.read"}),
        ttl=timedelta(hours=1),
    )

    raw = (tmp_path / "tokens.json").read_text(encoding="utf-8")
    assert issued.token not in raw
    assert "service-deploy" in raw
    assert "mcp.call" in raw


def test_token_authentication_requires_scope(tmp_path: Path):
    tokens = store(tmp_path)
    issued = tokens.issue(
        principal_id="service-deploy",
        scopes=frozenset({"mcp.call"}),
    )

    assert tokens.authenticate(
        issued.token,
        required_scope="mcp.call",
    ) == "service-deploy"

    with pytest.raises(PermissionError, match="scope"):
        tokens.authenticate(
            issued.token,
            required_scope="runs.write",
        )


def test_token_revocation_is_immediate_and_persistent(tmp_path: Path):
    tokens = store(tmp_path)
    issued = tokens.issue(
        principal_id="service-deploy",
        scopes=frozenset({"mcp.call"}),
    )

    tokens.revoke(issued.token)

    with pytest.raises(PermissionError, match="invalid"):
        tokens.authenticate(issued.token, required_scope="mcp.call")

    reloaded = store(tmp_path)
    with pytest.raises(PermissionError, match="invalid"):
        reloaded.authenticate(issued.token, required_scope="mcp.call")


def test_token_expiry_is_enforced(tmp_path: Path):
    clock = Clock()
    tokens = store(tmp_path, clock)
    issued = tokens.issue(
        principal_id="service-deploy",
        scopes=frozenset({"mcp.call"}),
        ttl=timedelta(minutes=5),
    )

    clock.value += timedelta(minutes=6)

    with pytest.raises(PermissionError, match="expired"):
        tokens.authenticate(issued.token, required_scope="mcp.call")


def test_token_scope_set_must_be_nonempty(tmp_path: Path):
    tokens = store(tmp_path)

    with pytest.raises(ValueError, match="scope"):
        tokens.issue(
            principal_id="service-deploy",
            scopes=frozenset(),
        )
