from __future__ import annotations

from pathlib import Path

from ai_workshop.credentials.models import HttpsTokenCredentialProfile


class HttpTokenCredentialContext:
    def __init__(
        self,
        profile: HttpsTokenCredentialProfile,
        secret_path: Path,
    ):
        self.profile = profile
        self.secret_path = Path(secret_path)
        self._token: str | None = None

    def __enter__(self) -> "HttpTokenCredentialContext":
        token = self.secret_path.read_text(encoding="utf-8")
        if not token:
            raise ValueError("credential token must not be empty")
        self._token = token
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._token = None

    @property
    def token(self) -> str:
        if self._token is None:
            raise RuntimeError("HTTP token credential context is not active")
        return self._token

    def redact(self, value: str) -> str:
        if self._token:
            return value.replace(self._token, "[REDACTED]")
        return value
