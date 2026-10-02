from __future__ import annotations

from pathlib import Path

import pytest

from ai_workshop.credentials.models import (
    HttpsTokenCredentialProfile,
    SshCredentialProfile,
)
from ai_workshop.credentials.store import CredentialStore
from ai_workshop.server.storage import ServerStorage


def make_store(tmp_path: Path) -> tuple[CredentialStore, ServerStorage]:
    storage = ServerStorage(tmp_path / "server-storage")
    store = CredentialStore(
        state_path=tmp_path / "state" / "credentials.json",
        secret_root=tmp_path / "private-secrets",
        forbidden_roots=(storage.root,),
    )
    return store, storage


def test_ssh_profile_stores_private_key_outside_project_storage(tmp_path: Path):
    store, storage = make_store(tmp_path)
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-key-data\n-----END OPENSSH PRIVATE KEY-----\n"

    profile = store.create_ssh("github-personal", private_key=key)

    assert isinstance(profile, SshCredentialProfile)
    assert "secret-key-data" not in repr(profile)
    secret_path = store.secret_path("github-personal")
    assert secret_path.read_text(encoding="utf-8") == key
    with pytest.raises(ValueError):
        secret_path.resolve().relative_to(storage.root.resolve())


def test_https_profile_stores_token_outside_metadata_and_project_storage(tmp_path: Path):
    store, storage = make_store(tmp_path)
    profile = store.create_https_token(
        "gitlab-company",
        username="oauth2",
        token="super-secret-token",
    )

    assert isinstance(profile, HttpsTokenCredentialProfile)
    assert "super-secret-token" not in (tmp_path / "state" / "credentials.json").read_text(
        encoding="utf-8"
    )
    secret_path = store.secret_path("gitlab-company")
    assert secret_path.read_text(encoding="utf-8") == "super-secret-token"
    with pytest.raises(ValueError):
        secret_path.resolve().relative_to(storage.root.resolve())


def test_credential_store_rejects_secret_root_inside_project_storage(tmp_path: Path):
    storage = ServerStorage(tmp_path / "server-storage")

    with pytest.raises(ValueError, match="forbidden"):
        CredentialStore(
            state_path=tmp_path / "state" / "credentials.json",
            secret_root=storage.root / "secrets",
            forbidden_roots=(storage.root,),
        )


def test_ssh_git_context_uses_key_via_environment_not_git_argv(tmp_path: Path):
    store, _ = make_store(tmp_path)
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nssh-secret\n-----END OPENSSH PRIVATE KEY-----\n"
    store.create_ssh("github", private_key=key)

    with store.git_context("github") as context:
        env = context.environment()
        assert "GIT_SSH_COMMAND" in env
        assert "ssh-secret" not in env["GIT_SSH_COMMAND"]
        assert "GIT_TERMINAL_PROMPT" in env
        argv = ["git", "fetch", "origin"]
        assert "ssh-secret" not in " ".join(argv)
        temporary_key = context.private_material_path
        assert temporary_key is not None
        assert temporary_key.is_file()
        assert temporary_key.read_text(encoding="utf-8") == key

    assert not temporary_key.exists()


def test_https_git_context_uses_askpass_and_does_not_embed_token_in_remote(tmp_path: Path):
    store, _ = make_store(tmp_path)
    store.create_https_token(
        "gitlab",
        username="oauth2",
        token="https-secret-token",
    )

    with store.git_context("gitlab") as context:
        env = context.environment()
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["AI_WORKSHOP_GIT_USERNAME"] == "oauth2"
        assert env["AI_WORKSHOP_GIT_TOKEN"] == "https-secret-token"
        askpass = Path(env["GIT_ASKPASS"])
        assert askpass.is_file()
        assert "https-secret-token" not in askpass.read_text(encoding="utf-8")
        remote = "https://gitlab.example/team/repo.git"
        assert "https-secret-token" not in remote

    assert not askpass.exists()


def test_git_error_redacts_credentials(tmp_path: Path):
    store, _ = make_store(tmp_path)
    store.create_https_token(
        "gitlab",
        username="oauth2",
        token="super-secret-token",
    )

    with store.git_context("gitlab") as context:
        message = context.redact(
            "fatal: auth failed for oauth2 with super-secret-token"
        )

    assert "super-secret-token" not in message
    assert "[REDACTED]" in message


def test_duplicate_credential_profile_is_rejected(tmp_path: Path):
    store, _ = make_store(tmp_path)
    store.create_ssh("github", private_key="key")

    with pytest.raises(ValueError, match="already exists"):
        store.create_ssh("github", private_key="other")


def test_profile_metadata_survives_reload_without_secret_material(tmp_path: Path):
    store, storage = make_store(tmp_path)
    store.create_https_token(
        "gitlab",
        username="oauth2",
        token="persisted-token",
    )

    reloaded = CredentialStore(
        state_path=tmp_path / "state" / "credentials.json",
        secret_root=tmp_path / "private-secrets",
        forbidden_roots=(storage.root,),
    )

    profile = reloaded.get("gitlab")
    assert isinstance(profile, HttpsTokenCredentialProfile)
    assert profile.username == "oauth2"
    assert "persisted-token" not in repr(profile)
