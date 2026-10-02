from __future__ import annotations

from pathlib import Path

from ai_workshop.server.bootstrap import ServerBootstrap


def make(tmp_path: Path):
    return ServerBootstrap(
        storage_root=tmp_path / "storage",
        state_root=tmp_path / "state",
        ca_root=tmp_path / "ca",
        first_admin_id="owner",
    )


def test_server_bootstrap_is_idempotent_and_does_not_rotate_secrets(tmp_path):
    bootstrap = make(tmp_path)

    first = bootstrap.initialize()
    second = bootstrap.initialize()

    assert first["first_admin_id"] == "owner"
    assert second["first_admin_id"] == "owner"
    assert first["tokens"] == second["tokens"]
    assert (tmp_path / "storage" / "projects").is_dir()
    assert (tmp_path / "storage" / "runs").is_dir()
    assert (tmp_path / "ca" / "ca-key.pem").is_file()
    assert (tmp_path / "ca" / "ca-cert.pem").is_file()


def test_server_bootstrap_recovers_from_partial_initialization(tmp_path):
    state = tmp_path / "state"
    secrets = state / "secrets"
    secrets.mkdir(parents=True)
    browser_token = "existing-browser-token-value-which-is-long-enough"
    (secrets / "browser-token").write_text(browser_token)

    result = make(tmp_path).initialize()

    assert result["tokens"]["browser"] == browser_token
    assert (secrets / "workspace-token").is_file()
    assert (secrets / "service-token").is_file()
    assert (state / "bootstrap.json").is_file()
    assert (tmp_path / "ca" / "ca-cert.pem").is_file()


def test_server_bootstrap_preserves_existing_local_ca(tmp_path):
    bootstrap = make(tmp_path)
    bootstrap.initialize()
    key = (tmp_path / "ca" / "ca-key.pem").read_bytes()
    cert = (tmp_path / "ca" / "ca-cert.pem").read_bytes()

    bootstrap.initialize()

    assert (tmp_path / "ca" / "ca-key.pem").read_bytes() == key
    assert (tmp_path / "ca" / "ca-cert.pem").read_bytes() == cert
