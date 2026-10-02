from __future__ import annotations

from pathlib import Path

import pytest

from ai_workshop.credentials.store import CredentialStore
from ai_workshop.forge.models import ForgeProfile, ForgeProviderKind, ForgeRepositoryBinding, ForgeRepositoryRef
from ai_workshop.forge.registry import ForgeRegistry
from ai_workshop.forge.service import ForgeService


class _Authorization:
    def __init__(self):
        self.calls = []

    def require(self, principal_id: str, permission: str, project_id: str | None):
        self.calls.append((principal_id, permission, project_id))
        if principal_id == "denied":
            raise PermissionError("permission denied")


def _service(tmp_path: Path) -> ForgeService:
    credentials = CredentialStore(
        state_path=tmp_path / "credentials.json",
        secret_root=tmp_path / "secrets",
    )
    credentials.create_https_token("forge-token", username="git", token="secret-token")
    registry = ForgeRegistry(tmp_path / "forges.json")
    registry.create_profile(
        ForgeProfile(
            profile_id="github-main",
            provider=ForgeProviderKind.GITHUB,
            base_url="https://api.github.test",
            credential_id="forge-token",
        )
    )
    registry.bind_project(
        ForgeRepositoryBinding(
            project_id="demo",
            profile_id="github-main",
            repository_owner="acme",
            repository_name="demo",
        )
    )
    return ForgeService(registry, credentials, _Authorization())


def test_merge_rejects_repository_binding_mismatch(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(PermissionError, match="does not match project binding"):
        service.pull_request_merge(
            "alice",
            "demo",
            ForgeRepositoryRef(owner="evil", name="other"),
            7,
        )


def test_forge_authorization_is_project_scoped(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(PermissionError, match="permission denied"):
        service.repository_get("denied", "demo")


def test_repository_delete_requires_one_time_confirmation(tmp_path, monkeypatch):
    service = _service(tmp_path)
    deleted = []

    monkeypatch.setattr(
        service,
        "_call",
        lambda binding, callback: deleted.append(binding.project_id),
    )

    with pytest.raises(PermissionError, match="valid forge confirmation required"):
        service.repository_delete("alice", "demo", "missing")

    confirmation = service.prepare_repository_delete("alice", "demo")
    service.repository_delete("alice", "demo", confirmation.token)
    assert deleted == ["demo"]

    with pytest.raises(PermissionError, match="valid forge confirmation required"):
        service.repository_delete("alice", "demo", confirmation.token)


def test_http_token_context_rejects_ssh_credentials(tmp_path):
    credentials = CredentialStore(
        state_path=tmp_path / "credentials.json",
        secret_root=tmp_path / "secrets",
    )
    credentials.create_ssh("ssh", private_key="key")

    with pytest.raises(TypeError, match="HTTP token credential required"):
        credentials.http_token_context("ssh")
