from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import threading

from ai_workshop.authn.models import SessionToken


class SessionStore:
    def __init__(
        self,
        state_path: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        session_ttl: timedelta = timedelta(hours=12),
    ):
        if session_ttl <= timedelta(0):
            raise ValueError("session TTL must be positive")
        self.state_path = Path(state_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.session_ttl = session_ttl
        self._lock = threading.RLock()
        self._records: dict[str, tuple[str, datetime]] = {}
        self._load()

    def issue(self, principal_id: str) -> SessionToken:
        now = self._now()
        raw = secrets.token_urlsafe(48)
        digest = self._digest(raw)
        expires_at = now + self.session_ttl
        with self._lock:
            self._records[digest] = (principal_id, expires_at)
            try:
                self._persist()
            except Exception:
                self._records.pop(digest, None)
                raise
        return SessionToken(
            token=raw,
            principal_id=principal_id,
            expires_at=expires_at,
        )

    def authenticate(self, token: str) -> str:
        digest = self._digest(token)
        with self._lock:
            record = self._records.get(digest)
            if record is None:
                raise PermissionError("invalid session")
            principal_id, expires_at = record
            if expires_at <= self._now():
                self._records.pop(digest, None)
                self._persist()
                raise PermissionError("session expired")
            return principal_id

    def revoke(self, token: str) -> None:
        digest = self._digest(token)
        with self._lock:
            if digest not in self._records:
                raise PermissionError("invalid session")
            record = self._records.pop(digest)
            try:
                self._persist()
            except Exception:
                self._records[digest] = record
                raise

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("session clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported session store version")
        for raw in payload.get("sessions", []):
            digest = str(raw["token_hash"])
            expires_at = datetime.fromisoformat(str(raw["expires_at"]))
            if expires_at.tzinfo is None or expires_at.utcoffset() is None:
                raise ValueError("session expiry must be timezone-aware")
            if digest in self._records:
                raise ValueError("duplicate session token hash")
            self._records[digest] = (str(raw["principal_id"]), expires_at)

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "sessions": [
                {
                    "token_hash": digest,
                    "principal_id": principal_id,
                    "expires_at": expires_at.isoformat(),
                }
                for digest, (principal_id, expires_at) in sorted(
                    self._records.items()
                )
            ],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
