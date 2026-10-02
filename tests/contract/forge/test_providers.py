from __future__ import annotations

import httpx
import pytest

from ai_workshop.forge.forgejo import ForgejoForgeProvider
from ai_workshop.forge.github import GitHubForgeProvider
from ai_workshop.forge.gitlab import GitLabForgeProvider
from ai_workshop.forge.models import ForgeCapability, ForgeProfile, ForgeProviderKind


@pytest.mark.parametrize(
    ("kind", "provider_type", "base_url", "path", "payload"),
    [
        (
            ForgeProviderKind.GITHUB,
            GitHubForgeProvider,
            "https://api.github.test",
            "/user/repos",
            [{"id": 1, "name": "demo", "owner": {"login": "acme"}, "html_url": "https://github.test/acme/demo", "default_branch": "main", "archived": False}],
        ),
        (
            ForgeProviderKind.GITLAB,
            GitLabForgeProvider,
            "https://gitlab.test",
            "/api/v4/projects",
            [{"id": 2, "path": "demo", "path_with_namespace": "acme/demo", "namespace": {"path": "acme", "full_path": "acme"}, "web_url": "https://gitlab.test/acme/demo", "default_branch": "main", "archived": False}],
        ),
        (
            ForgeProviderKind.FORGEJO,
            ForgejoForgeProvider,
            "https://forgejo.test",
            "/api/v1/user/repos",
            [{"id": 3, "name": "demo", "owner": {"login": "acme"}, "html_url": "https://forgejo.test/acme/demo", "default_branch": "main", "archived": False}],
        ),
    ],
)
def test_provider_repository_list_normalizes_domain_models(kind, provider_type, base_url, path, payload):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        assert request.url.path == path
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    profile = ForgeProfile(
        profile_id=f"{kind.value}-main",
        provider=kind,
        base_url=base_url,
        credential_id=f"{kind.value}-token",
    )
    provider = provider_type(profile, "super-secret-token", client=client)

    repositories = provider.repository_list()

    assert len(repositories) == 1
    assert repositories[0].ref.owner == "acme"
    assert repositories[0].ref.name == "demo"
    assert repositories[0].default_branch == "main"
    assert provider.capabilities() == frozenset(ForgeCapability)
    assert seen == [("GET", path)]


@pytest.mark.parametrize(
    ("kind", "provider_type", "base_url"),
    [
        (ForgeProviderKind.GITHUB, GitHubForgeProvider, "https://api.github.test"),
        (ForgeProviderKind.GITLAB, GitLabForgeProvider, "https://gitlab.test"),
        (ForgeProviderKind.FORGEJO, ForgejoForgeProvider, "https://forgejo.test"),
    ],
)
def test_provider_errors_never_expose_token(kind, provider_type, base_url):
    token = "never-leak-this-token"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"provider exploded with {token}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    profile = ForgeProfile(
        profile_id="main",
        provider=kind,
        base_url=base_url,
        credential_id="forge-token",
    )
    provider = provider_type(profile, token, client=client)

    with pytest.raises(Exception) as exc:
        provider.repository_list()

    assert token not in str(exc.value)
