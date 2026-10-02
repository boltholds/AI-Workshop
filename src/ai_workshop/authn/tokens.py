from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import threading
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_workshop.authn.sessions import SessionStore


_SCOPE_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]*$"


class IssuedScopedToken(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str = Field(min_length=32, repr=False)
    principal_id: str = Field(min_length=1)
    scopes: frozenset[str]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expiry_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("token expiry must be timezone-aware")
        return value


class ScopedTokenStore:
    def __init__(
        self,
        state_path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        default_ttl: timedelta = timedelta(hours=24),
    ):
        if default_ttl <= timedelta(0):
            raise ValueError("default token TTL must be positive")
        self.state_path = Path(state_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.default_ttl = default_ttl
        self._lock = threading.RLock()
        self._records: dict[str, tuple[str, frozenset[str], datetime]] = {}
        self._load()

    def issue(
        self,
        *,
        principal_id: str,
        scopes: frozenset[str],
        ttl: timedelta | None = None,
    ) -> IssuedScopedToken:
        if not principal_id:
            raise ValueError("principal id is required")
        if not scopes:
            raise ValueError("token requires at least one scope")
        for scope in scopes:
            import re
            if re.fullmatch(_SCOPE_PATTERN, scope) is None:
                raise ValueError("invalid token scope")

        lifetime = self.default_ttl if ttl is None else ttl
        if lifetime <= timedelta(0):
            raise ValueError("token TTL must be positive")

        now = self._now()
        raw = secrets.token_urlsafe(48)
        digest = self._digest(raw)
        expires_at = now + lifetime
        with self._lock:
            self._records[digest] = (
                principal_id,
                frozenset(scopes),
                expires_at,
            )
            try:
                self._persist()
            except Exception:
                self._records.pop(digest, None)
                raise
        return IssuedScopedToken(
            token=raw,
            principal_id=principal_id,
            scopes=frozenset(scopes),
            expires_at=expires_at,
        )

    def authenticate(
        self,
        token: str,
        *,
        required_scope: str | None,
    ) -> str:
        digest = self._digest(token)
        with self._lock:
            record = self._records.get(digest)
            if record is None:
                raise PermissionError("invalid service token")
            principal_id, scopes, expires_at = record
            if expires_at <= self._now():
                self._records.pop(digest, None)
                self._persist()
                raise PermissionError("service token expired")
            if required_scope is not None and required_scope not in scopes:
                raise PermissionError("service token scope denied")
            return principal_id

    def revoke(self, token: str) -> None:
        digest = self._digest(token)
        with self._lock:
            record = self._records.pop(digest, None)
            if record is None:
                raise PermissionError("invalid service token")
            try:
                self._persist()
            except Exception:
                self._records[digest] = record
                raise

    @staticmethod
    def _digest(token: str) -> str:
        if not token:
            return hashlib.sha256(b"").hexdigest()
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("token clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported scoped token store version")
        for raw in payload.get("tokens", []):
            digest = str(raw["token_hash"])
            if digest in self._records:
                raise ValueError("duplicate service token hash")
            expires_at = datetime.fromisoformat(str(raw["expires_at"]))
            if expires_at.tzinfo is None or expires_at.utcoffset() is None:
                raise ValueError("service token expiry must be timezone-aware")
            scopes = frozenset(str(scope) for scope in raw["scopes"])
            if not scopes:
                raise ValueError("service token requires scopes")
            self._records[digest] = (
                str(raw["principal_id"]),
                scopes,
                expires_at,
            )

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "tokens": [
                {
                    "token_hash": digest,
                    "principal_id": principal_id,
                    "scopes": sorted(scopes),
                    "expires_at": expires_at.isoformat(),
                }
                for digest, (principal_id, scopes, expires_at)
                in sorted(self._records.items())
            ],
        }
        temporary = self.state_path.with_suffix(
            self.state_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)


class WorkshopTokenAuthenticator:
    def __init__(
        self,
        *,
        sessions: SessionStore,
        service_tokens: ScopedTokenStore,
    ):
        self.sessions = sessions
        self.service_tokens = service_tokens

    def authenticate(
        self,
        token: str,
        *,
        required_scope: str | None,
    ) -> str:
        try:
            return self.sessions.authenticate(token)
        except PermissionError:
            return self.service_tokens.authenticate(
                token,
                required_scope=required_scope,
            )
