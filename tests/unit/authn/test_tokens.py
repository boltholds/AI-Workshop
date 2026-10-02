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


class FakeSessions:
    def __init__(self):
        self.valid = {}

    def authenticate(self, token: str) -> str:
        if token not in self.valid:
            raise PermissionError("invalid session")
        return self.valid[token]


def test_combined_authenticator_accepts_interactive_session_without_service_scope(
    tmp_path: Path,
):
    from ai_workshop.authn.tokens import WorkshopTokenAuthenticator

    sessions = FakeSessions()
    sessions.valid["session-token"] = "user-admin"
    service_tokens = store(tmp_path)
    auth = WorkshopTokenAuthenticator(
        sessions=sessions,
        service_tokens=service_tokens,
    )

    assert auth.authenticate(
        "session-token",
        required_scope="mcp.call",
    ) == "user-admin"


def test_combined_authenticator_enforces_scope_for_service_token(tmp_path: Path):
    from ai_workshop.authn.tokens import WorkshopTokenAuthenticator

    sessions = FakeSessions()
    service_tokens = store(tmp_path)
    issued = service_tokens.issue(
        principal_id="service-reader",
        scopes=frozenset({"runs.read"}),
    )
    auth = WorkshopTokenAuthenticator(
        sessions=sessions,
        service_tokens=service_tokens,
    )

    with pytest.raises(PermissionError, match="scope"):
        auth.authenticate(
            issued.token,
            required_scope="mcp.call",
        )


def test_zero_ttl_is_rejected_instead_of_using_default(tmp_path: Path):
    tokens = store(tmp_path)

    with pytest.raises(ValueError, match="TTL"):
        tokens.issue(
            principal_id="service-deploy",
            scopes=frozenset({"mcp.call"}),
            ttl=timedelta(0),
        )
