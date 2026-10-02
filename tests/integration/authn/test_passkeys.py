from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_workshop.authn.models import (
    VerifiedAuthentication,
    VerifiedRegistration,
)
from ai_workshop.authn.sessions import SessionStore
from ai_workshop.authn.webauthn import WebAuthnService
from ai_workshop.authz.service import AuthorizationService
from ai_workshop.identity.models import UserPrincipal
from ai_workshop.identity.store import PrincipalStore


def b64(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


class FakeBackend:
    credential_id = b"credential-one"
    public_key = b"fake-cose-public-key"

    def registration_options(
        self,
        *,
        user_id: bytes,
        username: str,
        display_name: str,
        challenge: bytes,
        exclude_credentials: tuple[bytes, ...],
    ) -> str:
        return (
            '{"kind":"registration","challenge":"'
            + b64(challenge)
            + '","user":"'
            + username
            + '"}'
        )

    def verify_registration(
        self,
        response: dict[str, object],
        *,
        expected_challenge: bytes,
    ) -> VerifiedRegistration:
        assert response["challenge"] == b64(expected_challenge)
        return VerifiedRegistration(
            credential_id=self.credential_id,
            public_key=self.public_key,
            sign_count=0,
        )

    def authentication_options(
        self,
        *,
        challenge: bytes,
        allow_credentials: tuple[bytes, ...],
    ) -> str:
        assert allow_credentials == (self.credential_id,)
        return (
            '{"kind":"authentication","challenge":"'
            + b64(challenge)
            + '"}'
        )

    def credential_id_from_response(self, response: dict[str, object]) -> bytes:
        return str(response["credential_id"]).encode("ascii")

    def verify_authentication(
        self,
        response: dict[str, object],
        *,
        expected_challenge: bytes,
        credential_public_key: bytes,
        credential_current_sign_count: int,
    ) -> VerifiedAuthentication:
        assert response["challenge"] == b64(expected_challenge)
        assert credential_public_key == self.public_key
        return VerifiedAuthentication(
            credential_id=self.credential_id,
            new_sign_count=credential_current_sign_count + 1,
        )


def services(tmp_path: Path):
    clock = Clock()
    principals = PrincipalStore(tmp_path / "identity.json")
    sessions = SessionStore(
        tmp_path / "sessions.json",
        clock=clock,
        session_ttl=timedelta(hours=12),
    )
    authn = WebAuthnService(
        principals=principals,
        sessions=sessions,
        state_path=tmp_path / "authn.json",
        rp_id="workshop.local",
        origin="https://workshop.local",
        rp_name="AI Workshop",
        backend=FakeBackend(),
        clock=clock,
        challenge_ttl=timedelta(minutes=5),
    )
    return authn, principals, sessions, clock


def bootstrap(authn: WebAuthnService):
    start = authn.begin_admin_bootstrap(
        "admin-user",
        display_name="Administrator",
    )
    result = authn.finish_admin_bootstrap(
        start.challenge_id,
        {"challenge": start.challenge_b64},
    )
    return start, result


def test_first_passkey_bootstraps_admin_principal_and_role(tmp_path: Path):
    authn, principals, sessions, _ = services(tmp_path)

    _, result = bootstrap(authn)

    principal = principals.get("admin-user")
    assert isinstance(principal, UserPrincipal)
    assert principal.display_name == "Administrator"
    assert "admin" in principals.global_roles("admin-user")
    assert AuthorizationService(principals).require(
        "admin-user",
        "runs.start",
        "any-project",
    ).allows("runs.start")
    assert sessions.authenticate(result.session.token) == "admin-user"
    assert len(result.recovery_codes) == 8


def test_first_admin_bootstrap_cannot_be_replayed(tmp_path: Path):
    authn, _, _, _ = services(tmp_path)
    bootstrap(authn)

    with pytest.raises(PermissionError, match="bootstrap"):
        authn.begin_admin_bootstrap(
            "second-admin",
            display_name="Second",
        )


def test_passkey_challenge_is_single_use(tmp_path: Path):
    authn, _, _, _ = services(tmp_path)
    bootstrap(authn)
    start = authn.begin_login("admin-user")
    response = {
        "challenge": start.challenge_b64,
        "credential_id": "credential-one",
    }

    authn.finish_login(start.challenge_id, response)

    with pytest.raises(PermissionError, match="challenge"):
        authn.finish_login(start.challenge_id, response)


def test_expired_challenge_is_rejected_and_consumed(tmp_path: Path):
    authn, _, _, clock = services(tmp_path)
    bootstrap(authn)
    start = authn.begin_login("admin-user")
    clock.value += timedelta(minutes=6)
    response = {
        "challenge": start.challenge_b64,
        "credential_id": "credential-one",
    }

    with pytest.raises(PermissionError, match="expired"):
        authn.finish_login(start.challenge_id, response)
    with pytest.raises(PermissionError, match="challenge"):
        authn.finish_login(start.challenge_id, response)


def test_login_updates_sign_count_and_issues_session(tmp_path: Path):
    authn, _, sessions, _ = services(tmp_path)
    bootstrap(authn)
    start = authn.begin_login("admin-user")

    result = authn.finish_login(
        start.challenge_id,
        {
            "challenge": start.challenge_b64,
            "credential_id": "credential-one",
        },
    )

    assert sessions.authenticate(result.token) == "admin-user"
    assert authn.credentials_for("admin-user")[0].sign_count == 1


def test_recovery_code_is_one_time(tmp_path: Path):
    authn, _, sessions, _ = services(tmp_path)
    _, result = bootstrap(authn)
    code = result.recovery_codes[0]

    recovered = authn.authenticate_recovery_code("admin-user", code)

    assert sessions.authenticate(recovered.token) == "admin-user"
    with pytest.raises(PermissionError, match="recovery"):
        authn.authenticate_recovery_code("admin-user", code)


def test_session_token_is_hashed_at_rest_and_revocable(tmp_path: Path):
    authn, _, sessions, _ = services(tmp_path)
    _, result = bootstrap(authn)
    raw_state = (tmp_path / "sessions.json").read_text(encoding="utf-8")

    assert result.session.token not in raw_state
    assert sessions.authenticate(result.session.token) == "admin-user"

    sessions.revoke(result.session.token)

    with pytest.raises(PermissionError, match="session"):
        sessions.authenticate(result.session.token)


def test_authentication_state_survives_reload(tmp_path: Path):
    authn, principals, _, clock = services(tmp_path)
    bootstrap(authn)

    sessions = SessionStore(
        tmp_path / "sessions-2.json",
        clock=clock,
    )
    reloaded = WebAuthnService(
        principals=principals,
        sessions=sessions,
        state_path=tmp_path / "authn.json",
        rp_id="workshop.local",
        origin="https://workshop.local",
        rp_name="AI Workshop",
        backend=FakeBackend(),
        clock=clock,
    )

    assert reloaded.bootstrap_completed is True
    assert reloaded.credentials_for("admin-user")[0].credential_id_b64 == b64(
        FakeBackend.credential_id
    )
