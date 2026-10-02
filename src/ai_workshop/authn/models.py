from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerifiedRegistration(_FrozenModel):
    credential_id: bytes
    public_key: bytes
    sign_count: int = Field(ge=0)


class VerifiedAuthentication(_FrozenModel):
    credential_id: bytes
    new_sign_count: int = Field(ge=0)


class PasskeyCredential(_FrozenModel):
    principal_id: str = Field(min_length=1)
    credential_id_b64: str = Field(min_length=1)
    public_key_b64: str = Field(min_length=1)
    sign_count: int = Field(ge=0)


class CeremonyStart(_FrozenModel):
    challenge_id: str = Field(min_length=1)
    challenge_b64: str = Field(min_length=1)
    options_json: str = Field(min_length=2)


class SessionToken(_FrozenModel):
    token: str = Field(min_length=32)
    principal_id: str = Field(min_length=1)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def expiry_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("session expiry must be timezone-aware")
        return value


class BootstrapResult(_FrozenModel):
    session: SessionToken
    recovery_codes: tuple[str, ...]
