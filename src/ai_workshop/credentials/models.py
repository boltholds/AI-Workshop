from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


_CREDENTIAL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class CredentialKind(StrEnum):
    SSH = "ssh"
    HTTPS_TOKEN = "https-token"


class _CredentialProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    credential_id: str = Field(min_length=1, pattern=_CREDENTIAL_ID_PATTERN)
    kind: CredentialKind


class SshCredentialProfile(_CredentialProfile):
    kind: CredentialKind = CredentialKind.SSH


class HttpsTokenCredentialProfile(_CredentialProfile):
    kind: CredentialKind = CredentialKind.HTTPS_TOKEN
    username: str = Field(min_length=1)


CredentialProfile = SshCredentialProfile | HttpsTokenCredentialProfile
