from __future__ import annotations

from enum import StrEnum
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


_ID = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
_REPO_PART = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForgeProviderKind(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"
    FORGEJO = "forgejo"


class ForgeTransportSecurity(StrEnum):
    HTTPS = "https"
    INTERNAL_HTTP = "internal-http"


class ForgeCapability(StrEnum):
    REPOSITORY = "repository"
    PULL_REQUEST = "pull-request"
    ISSUE = "issue"
    RELEASE = "release"
    BRANCH_PROTECTION = "branch-protection"
    WEBHOOK = "webhook"


class ForgeProfile(_FrozenModel):
    profile_id: str = Field(min_length=1, pattern=_ID)
    provider: ForgeProviderKind
    base_url: str = Field(min_length=1)
    credential_id: str = Field(min_length=1, pattern=_ID)
    transport_security: ForgeTransportSecurity = ForgeTransportSecurity.HTTPS

    @model_validator(mode="after")
    def validate_base_url(self) -> "ForgeProfile":
        parsed = urlsplit(self.base_url)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("forge base URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("forge base URL must not contain query or fragment")
        if self.transport_security is ForgeTransportSecurity.HTTPS:
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("external forge profile requires HTTPS")
        else:
            if parsed.scheme != "http" or not parsed.hostname:
                raise ValueError("internal forge profile requires HTTP internal DNS")
            hostname = parsed.hostname.lower()
            try:
                ip_address(hostname)
            except ValueError:
                pass
            else:
                raise ValueError("internal HTTP forge must use internal DNS")
            if hostname in {"localhost", "localhost.localdomain"}:
                raise ValueError("internal HTTP forge must use internal DNS")
        return self

    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


class ForgeRepositoryRef(_FrozenModel):
    owner: str = Field(min_length=1, pattern=_REPO_PART)
    name: str = Field(min_length=1, pattern=_REPO_PART)


class ForgeRepositoryBinding(_FrozenModel):
    project_id: str = Field(min_length=1, pattern=_ID)
    profile_id: str = Field(min_length=1, pattern=_ID)
    repository_owner: str = Field(min_length=1, pattern=_REPO_PART)
    repository_name: str = Field(min_length=1, pattern=_REPO_PART)

    def repository_ref(self) -> ForgeRepositoryRef:
        return ForgeRepositoryRef(
            owner=self.repository_owner,
            name=self.repository_name,
        )


class ForgeRepository(_FrozenModel):
    provider_repository_id: str = Field(min_length=1)
    ref: ForgeRepositoryRef
    web_url: str = Field(min_length=1)
    default_branch: str = Field(min_length=1)
    archived: bool = False


class ForgePullRequestState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class ForgePullRequest(_FrozenModel):
    provider_pull_request_id: str = Field(min_length=1)
    number: int = Field(ge=1)
    repository: ForgeRepositoryRef
    title: str = Field(min_length=1)
    source_branch: str = Field(min_length=1)
    target_branch: str = Field(min_length=1)
    state: ForgePullRequestState
    web_url: str = Field(min_length=1)


class ForgeIssueState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ForgeIssue(_FrozenModel):
    provider_issue_id: str = Field(min_length=1)
    number: int = Field(ge=1)
    repository: ForgeRepositoryRef
    title: str = Field(min_length=1)
    state: ForgeIssueState
    web_url: str = Field(min_length=1)


class ForgeRelease(_FrozenModel):
    provider_release_id: str = Field(min_length=1)
    repository: ForgeRepositoryRef
    tag: str = Field(min_length=1)
    name: str = Field(min_length=1)
    web_url: str = Field(min_length=1)
