from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Callable, Protocol
from urllib.parse import urlencode, urlsplit

import jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_workshop.identity.models import ExternalIdentityPrincipal
from ai_workshop.identity.protocol import PrincipalService


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OidcProviderConfig(_FrozenModel):
    provider_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    issuer: str
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1, repr=False, exclude=True)

    @field_validator("issuer")
    @classmethod
    def issuer_must_be_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("OIDC issuer must use HTTPS")
        return value.rstrip("/")


class OidcDiscovery(_FrozenModel):
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


class OidcTokenResponse(_FrozenModel):
    id_token: str = Field(min_length=1, repr=False)


class OidcAuthorizationStart(_FrozenModel):
    authorization_url: str
    state: str
    nonce: str


class OidcTransport(Protocol):
    def discovery(self, config: OidcProviderConfig) -> OidcDiscovery: ...

    def exchange_code(
        self,
        config: OidcProviderConfig,
        discovery: OidcDiscovery,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> OidcTokenResponse: ...

    def jwks(
        self,
        config: OidcProviderConfig,
        discovery: OidcDiscovery,
    ) -> tuple[dict[str, object], ...]: ...


@dataclass(frozen=True, slots=True)
class _PendingAuthorization:
    provider_id: str
    redirect_uri: str
    nonce: str
    code_verifier: str
    expires_at: datetime


class OidcAuthenticator:
    def __init__(
        self,
        *,
        principals: PrincipalService,
        providers: tuple[OidcProviderConfig, ...],
        transport: OidcTransport,
        clock: Callable[[], datetime] | None = None,
        state_ttl: timedelta = timedelta(minutes=5),
    ):
        if state_ttl <= timedelta(0):
            raise ValueError("OIDC state TTL must be positive")
        self.principals = principals
        self.providers = {item.provider_id: item for item in providers}
        if len(self.providers) != len(providers):
            raise ValueError("duplicate OIDC provider id")
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.state_ttl = state_ttl
        self._pending: dict[str, _PendingAuthorization] = {}

    def begin(
        self,
        provider_id: str,
        *,
        redirect_uri: str,
    ) -> OidcAuthorizationStart:
        config = self._provider(provider_id)
        discovery = self.transport.discovery(config)
        self._validate_discovery(config, discovery)

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = self._pkce_challenge(verifier)
        self._pending[state] = _PendingAuthorization(
            provider_id=provider_id,
            redirect_uri=redirect_uri,
            nonce=nonce,
            code_verifier=verifier,
            expires_at=self.clock() + self.state_ttl,
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": config.client_id,
                "redirect_uri": redirect_uri,
                "scope": "openid profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return OidcAuthorizationStart(
            authorization_url=f"{discovery.authorization_endpoint}?{query}",
            state=state,
            nonce=nonce,
        )

    def authenticate(
        self,
        *,
        state: str,
        code: str,
    ) -> ExternalIdentityPrincipal:
        pending = self._pending.pop(state, None)
        if pending is None:
            raise PermissionError("invalid or already used OIDC state")
        if self.clock() > pending.expires_at:
            raise PermissionError("OIDC state expired")

        config = self._provider(pending.provider_id)
        discovery = self.transport.discovery(config)
        self._validate_discovery(config, discovery)
        response = self.transport.exchange_code(
            config,
            discovery,
            code=code,
            redirect_uri=pending.redirect_uri,
            code_verifier=pending.code_verifier,
        )
        claims = self._verify_id_token(
            config,
            discovery,
            response.id_token,
            expected_nonce=pending.nonce,
        )

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise PermissionError("OIDC token subject is missing")

        issuer_binding = self._issuer_binding(discovery.issuer)
        existing = self.principals.find_external(issuer_binding, subject)
        if isinstance(existing, ExternalIdentityPrincipal):
            return existing

        display_name = claims.get("preferred_username")
        if not isinstance(display_name, str) or not display_name:
            display_name = subject

        principal = ExternalIdentityPrincipal(
            principal_id=self._principal_id(discovery.issuer, subject),
            display_name=display_name[:200],
            provider_id=issuer_binding,
            subject=subject,
        )
        created = self.principals.create(principal)
        if not isinstance(created, ExternalIdentityPrincipal):
            raise RuntimeError("OIDC identity store returned wrong principal type")
        return created

    def _verify_id_token(
        self,
        config: OidcProviderConfig,
        discovery: OidcDiscovery,
        token: str,
        *,
        expected_nonce: str,
    ) -> dict[str, object]:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            alg = header.get("alg")
            if not isinstance(kid, str) or alg != "RS256":
                raise PermissionError("OIDC token key or algorithm is invalid")

            jwk = next(
                (
                    item
                    for item in self.transport.jwks(config, discovery)
                    if item.get("kid") == kid
                ),
                None,
            )
            if jwk is None:
                raise PermissionError("OIDC signing key was not found")

            key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                options={
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                    "verify_iat": False,
                    "require": ["iss", "sub", "aud", "exp", "iat", "nonce"],
                },
            )
        except PermissionError:
            raise
        except Exception as exc:
            raise PermissionError("OIDC token validation failed") from exc

        if claims.get("iss") != discovery.issuer:
            raise PermissionError("OIDC issuer validation failed")

        audience = claims.get("aud")
        if isinstance(audience, str):
            audience_ok = audience == config.client_id
        elif isinstance(audience, list):
            audience_ok = config.client_id in audience
        else:
            audience_ok = False
        if not audience_ok:
            raise PermissionError("OIDC audience validation failed")

        now = self.clock().timestamp()
        exp = claims.get("exp")
        iat = claims.get("iat")
        if not isinstance(exp, (int, float)) or exp <= now:
            raise PermissionError("OIDC token expired")
        if not isinstance(iat, (int, float)) or iat > now + 60:
            raise PermissionError("OIDC token issued-at validation failed")

        if claims.get("nonce") != expected_nonce:
            raise PermissionError("OIDC nonce validation failed")

        return dict(claims)

    def _provider(self, provider_id: str) -> OidcProviderConfig:
        config = self.providers.get(provider_id)
        if config is None:
            raise KeyError(f"unknown OIDC provider: {provider_id}")
        return config

    @staticmethod
    def _validate_discovery(
        config: OidcProviderConfig,
        discovery: OidcDiscovery,
    ) -> None:
        if discovery.issuer.rstrip("/") != config.issuer:
            raise PermissionError("OIDC discovery issuer mismatch")
        for value in (
            discovery.authorization_endpoint,
            discovery.token_endpoint,
            discovery.jwks_uri,
        ):
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc:
                raise PermissionError("OIDC discovery endpoints must use HTTPS")

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _issuer_binding(issuer: str) -> str:
        digest = hashlib.sha256(issuer.encode("utf-8")).hexdigest()[:32]
        return f"oidc-{digest}"

    @staticmethod
    def _principal_id(issuer: str, subject: str) -> str:
        digest = hashlib.sha256(
            f"{issuer}\0{subject}".encode("utf-8")
        ).hexdigest()[:40]
        return f"oidc-{digest}"
