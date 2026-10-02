from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from ai_workshop.credentials.git_env import GitCredentialContext
from ai_workshop.credentials.http_token import HttpTokenCredentialContext
from ai_workshop.credentials.models import CredentialProfile


class CredentialProvider(Protocol):
    def get(self, credential_id: str) -> CredentialProfile: ...

    def git_context(
        self,
        credential_id: str,
    ) -> AbstractContextManager[GitCredentialContext]: ...

    def http_token_context(
        self,
        credential_id: str,
    ) -> AbstractContextManager[HttpTokenCredentialContext]: ...
