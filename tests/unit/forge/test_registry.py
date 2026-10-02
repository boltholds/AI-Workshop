from __future__ import annotations

from pathlib import Path

import pytest

from ai_workshop.forge.models import (
    ForgeProfile,
    ForgeProviderKind,
    ForgeRepositoryBinding,
    ForgeTransportSecurity,
)
from ai_workshop.forge.registry import ForgeRegistry


def registry(tmp_path: Path) -> ForgeRegistry:
    return ForgeRegistry(tmp_path / "forge-registry.json")


def test_profiles_are_identity_scoped(tmp_path: Path):
    store = registry(tmp_path)
    personal = store.create_profile(
        ForgeProfile(
            profile_id="personal",
            provider=ForgeProviderKind.GITHUB,
            base_url="https://api.github.com",
            credential_id="github-personal",
        )
    )
    company = store.create_profile(
        ForgeProfile(
            profile_id="company",
            provider=ForgeProviderKind.GITHUB,
            base_url="https://github.company.example/api/v3",
            credential_id="github-work",
        )
    )

    assert personal.profile_id == "personal"
    assert company.profile_id == "company"
    assert store.get_profile("personal").credential_id == "github-personal"
    assert store.get_profile("company").credential_id == "github-work"
    assert store.get_profile("personal").base_url != store.get_profile("company").base_url


def test_profile_metadata_survives_reload(tmp_path: Path):
    state = tmp_path / "forge-registry.json"
    store = ForgeRegistry(state)
    store.create_profile(
        ForgeProfile(
            profile_id="gitlab-company",
            provider=ForgeProviderKind.GITLAB,
            base_url="https://gitlab.example/api/v4",
            credential_id="gitlab-company",
        )
    )

    reloaded = ForgeRegistry(state)

    assert reloaded.get_profile("gitlab-company") == store.get_profile("gitlab-company")


def test_duplicate_profile_id_is_rejected(tmp_path: Path):
    store = registry(tmp_path)
    profile = ForgeProfile(
        profile_id="personal",
        provider=ForgeProviderKind.GITHUB,
        base_url="https://api.github.com",
        credential_id="github-personal",
    )
    store.create_profile(profile)

    with pytest.raises(ValueError, match="already exists"):
        store.create_profile(profile)


def test_external_forge_profile_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        ForgeProfile(
            profile_id="unsafe",
            provider=ForgeProviderKind.GITLAB,
            base_url="http://gitlab.example/api/v4",
            credential_id="gitlab-company",
        )


def test_embedded_forgejo_can_use_explicit_internal_http():
    profile = ForgeProfile(
        profile_id="homelab",
        provider=ForgeProviderKind.FORGEJO,
        base_url="http://forgejo:3000/api/v1",
        credential_id="forgejo-home",
        transport_security=ForgeTransportSecurity.INTERNAL_HTTP,
    )

    assert profile.transport_security is ForgeTransportSecurity.INTERNAL_HTTP


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:3000/api/v1",
        "http://localhost:3000/api/v1",
        "http://169.254.169.254/api/v1",
    ],
)
def test_internal_http_profile_rejects_loopback_and_ip_targets(url: str):
    with pytest.raises(ValueError, match="internal DNS"):
        ForgeProfile(
            profile_id="unsafe-internal",
            provider=ForgeProviderKind.FORGEJO,
            base_url=url,
            credential_id="forgejo-home",
            transport_security=ForgeTransportSecurity.INTERNAL_HTTP,
        )


def test_project_binding_requires_existing_profile(tmp_path: Path):
    store = registry(tmp_path)

    with pytest.raises(KeyError, match="forge profile"):
        store.bind_project(
            ForgeRepositoryBinding(
                project_id="plc-web",
                profile_id="missing",
                repository_owner="boltholds",
                repository_name="PLC-Web",
            )
        )


def test_project_binding_is_stable_and_persistent(tmp_path: Path):
    state = tmp_path / "forge-registry.json"
    store = ForgeRegistry(state)
    store.create_profile(
        ForgeProfile(
            profile_id="personal",
            provider=ForgeProviderKind.GITHUB,
            base_url="https://api.github.com",
            credential_id="github-personal",
        )
    )
    binding = store.bind_project(
        ForgeRepositoryBinding(
            project_id="ai-workshop",
            profile_id="personal",
            repository_owner="boltholds",
            repository_name="AI-Workshop",
        )
    )

    assert store.project_binding("ai-workshop") == binding

    reloaded = ForgeRegistry(state)
    assert reloaded.project_binding("ai-workshop") == binding


def test_project_binding_cannot_be_silently_replaced(tmp_path: Path):
    store = registry(tmp_path)
    store.create_profile(
        ForgeProfile(
            profile_id="personal",
            provider=ForgeProviderKind.GITHUB,
            base_url="https://api.github.com",
            credential_id="github-personal",
        )
    )
    store.bind_project(
        ForgeRepositoryBinding(
            project_id="demo",
            profile_id="personal",
            repository_owner="owner",
            repository_name="one",
        )
    )

    with pytest.raises(ValueError, match="already bound"):
        store.bind_project(
            ForgeRepositoryBinding(
                project_id="demo",
                profile_id="personal",
                repository_owner="owner",
                repository_name="two",
            )
        )


def test_profile_repr_and_registry_state_never_contain_secret_material(tmp_path: Path):
    store = registry(tmp_path)
    profile = store.create_profile(
        ForgeProfile(
            profile_id="personal",
            provider=ForgeProviderKind.GITHUB,
            base_url="https://api.github.com",
            credential_id="github-personal",
        )
    )

    raw = (tmp_path / "forge-registry.json").read_text(encoding="utf-8")
    assert "github-personal" in raw
    assert "token" not in profile.model_fields
    assert "password" not in profile.model_fields
    assert "private_key" not in profile.model_fields
