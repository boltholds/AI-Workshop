from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ai_workshop.authn.oidc import (
    OidcAuthenticator,
    OidcDiscovery,
    OidcProviderConfig,
    OidcTokenResponse,
)
from ai_workshop.identity.models import ExternalIdentityPrincipal
from ai_workshop.identity.store import PrincipalStore


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


class FakeTransport:
    def __init__(self, clock: Clock):
        self.clock = clock
        self.keys = {}
        self.token_claims = {}
        self.exchanges = []

    def add_provider(self, provider_id: str, issuer: str):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            private.public_key(),
            as_dict=True,
        )
        public_jwk["kid"] = f"{provider_id}-key"
        public_jwk["alg"] = "RS256"
        self.keys[provider_id] = (private, public_jwk, issuer)

    def discovery(self, config: OidcProviderConfig) -> OidcDiscovery:
        _, _, issuer = self.keys[config.provider_id]
        return OidcDiscovery(
            issuer=issuer,
            authorization_endpoint=f"{issuer}/authorize",
            token_endpoint=f"{issuer}/token",
            jwks_uri=f"{issuer}/jwks",
        )

    def exchange_code(
        self,
        config: OidcProviderConfig,
        discovery: OidcDiscovery,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OidcTokenResponse:
        self.exchanges.append((config.provider_id, code, redirect_uri, code_verifier))
        private, jwk, issuer = self.keys[config.provider_id]
        claims = dict(self.token_claims[code])
        token = jwt.encode(
            claims,
            private,
            algorithm="RS256",
            headers={"kid": jwk["kid"]},
        )
        return OidcTokenResponse(id_token=token)

    def jwks(
        self,
        config: OidcProviderConfig,
        discovery: OidcDiscovery,
    ) -> tuple[dict[str, object], ...]:
        return (dict(self.keys[config.provider_id][1]),)


def setup(tmp_path):
    clock = Clock()
    transport = FakeTransport(clock)
    transport.add_provider("one", "https://issuer-one.example")
    transport.add_provider("two", "https://issuer-two.example")
    principals = PrincipalStore(tmp_path / "identity.json")
    auth = OidcAuthenticator(
        principals=principals,
        providers=(
            OidcProviderConfig(
                provider_id="one",
                issuer="https://issuer-one.example",
                client_id="client-one",
                client_secret="secret-one",
            ),
            OidcProviderConfig(
                provider_id="two",
                issuer="https://issuer-two.example",
                client_id="client-two",
                client_secret="secret-two",
            ),
        ),
        transport=transport,
        clock=clock,
        state_ttl=timedelta(minutes=5),
    )
    return auth, principals, transport, clock


def claims(
    *,
    issuer: str,
    audience: str,
    nonce: str,
    subject: str = "subject-123",
    now: datetime,
):
    return {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "nonce": nonce,
        "preferred_username": "OIDC User",
    }


def nonce_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["nonce"][0]


def test_oidc_authorization_uses_pkce_state_and_nonce(tmp_path):
    auth, _, _, _ = setup(tmp_path)

    start = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
    query = parse_qs(urlparse(start.authorization_url).query)

    assert query["response_type"] == ["code"]
    assert query["state"] == [start.state]
    assert query["nonce"] == [start.nonce]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) >= 43


def test_oidc_state_is_single_use(tmp_path):
    auth, _, transport, clock = setup(tmp_path)
    start = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
    transport.token_claims["good"] = claims(
        issuer="https://issuer-one.example",
        audience="client-one",
        nonce=start.nonce,
        now=clock.value,
    )

    auth.authenticate(state=start.state, code="good")

    with pytest.raises(PermissionError, match="state"):
        auth.authenticate(state=start.state, code="good")


def test_oidc_nonce_mismatch_is_rejected(tmp_path):
    auth, principals, transport, clock = setup(tmp_path)
    start = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
    transport.token_claims["bad-nonce"] = claims(
        issuer="https://issuer-one.example",
        audience="client-one",
        nonce="wrong",
        now=clock.value,
    )

    with pytest.raises(PermissionError, match="nonce"):
        auth.authenticate(state=start.state, code="bad-nonce")

    assert principals.list() == []


def test_oidc_issuer_mismatch_is_rejected(tmp_path):
    auth, principals, transport, clock = setup(tmp_path)
    start = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
    transport.token_claims["bad-issuer"] = claims(
        issuer="https://evil.example",
        audience="client-one",
        nonce=start.nonce,
        now=clock.value,
    )

    with pytest.raises(PermissionError, match="OIDC"):
        auth.authenticate(state=start.state, code="bad-issuer")

    assert principals.list() == []


def test_oidc_identity_key_includes_issuer_and_subject(tmp_path):
    auth, principals, transport, clock = setup(tmp_path)

    first = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
    transport.token_claims["one"] = claims(
        issuer="https://issuer-one.example",
        audience="client-one",
        nonce=first.nonce,
        subject="same-subject",
        now=clock.value,
    )
    first_identity = auth.authenticate(state=first.state, code="one")

    second = auth.begin("two", redirect_uri="https://workshop.local/oidc/callback")
    transport.token_claims["two"] = claims(
        issuer="https://issuer-two.example",
        audience="client-two",
        nonce=second.nonce,
        subject="same-subject",
        now=clock.value,
    )
    second_identity = auth.authenticate(state=second.state, code="two")

    assert isinstance(first_identity, ExternalIdentityPrincipal)
    assert isinstance(second_identity, ExternalIdentityPrincipal)
    assert first_identity.principal_id != second_identity.principal_id
    assert len(principals.list()) == 2


def test_same_issuer_subject_reuses_existing_identity(tmp_path):
    auth, principals, transport, clock = setup(tmp_path)

    identities = []
    for code in ("first", "second"):
        start = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
        transport.token_claims[code] = claims(
            issuer="https://issuer-one.example",
            audience="client-one",
            nonce=start.nonce,
            now=clock.value,
        )
        identities.append(auth.authenticate(state=start.state, code=code))

    assert identities[0].principal_id == identities[1].principal_id
    assert len(principals.list()) == 1


def test_oidc_state_expiry_rejects_callback(tmp_path):
    auth, _, transport, clock = setup(tmp_path)
    start = auth.begin("one", redirect_uri="https://workshop.local/oidc/callback")
    clock.value += timedelta(minutes=6)
    transport.token_claims["late"] = claims(
        issuer="https://issuer-one.example",
        audience="client-one",
        nonce=start.nonce,
        now=clock.value,
    )

    with pytest.raises(PermissionError, match="expired"):
        auth.authenticate(state=start.state, code="late")


def test_oidc_provider_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        OidcProviderConfig(
            provider_id="bad",
            issuer="http://issuer.example",
            client_id="client",
            client_secret="secret",
        )
