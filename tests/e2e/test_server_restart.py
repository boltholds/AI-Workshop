from __future__ import annotations

from pathlib import Path

from ai_workshop.server.bootstrap import ServerBootstrap


def test_restart_preserves_all_persistent_domains(tmp_path):
    storage=tmp_path/"storage"
    state=tmp_path/"state"
    ca=tmp_path/"ca"
    browser=tmp_path/"browser-profile"
    runtime=tmp_path/"runtime-state"

    bootstrap=ServerBootstrap(
        storage_root=storage,
        state_root=state,
        ca_root=ca,
        first_admin_id="owner",
    )
    first=bootstrap.initialize()

    project=storage/"projects"/"demo"/"README.md"
    project.parent.mkdir(parents=True)
    project.write_text("persistent-project")
    browser.mkdir()
    (browser/"profile.db").write_text("persistent-browser")
    runtime.mkdir()
    (runtime/"nested-state").write_text("persistent-runtime")

    second=bootstrap.initialize()

    assert project.read_text() == "persistent-project"
    assert (browser/"profile.db").read_text() == "persistent-browser"
    assert (runtime/"nested-state").read_text() == "persistent-runtime"
    assert first["tokens"] == second["tokens"]
    assert (ca/"ca-key.pem").is_file()


def test_project_service_failure_is_isolated(tmp_path):
    control=tmp_path/"control"
    auth=tmp_path/"auth"
    nested=tmp_path/"nested-service"
    control.mkdir()
    auth.mkdir()
    nested.mkdir()

    (control/"health").write_text("ok")
    (auth/"session-store").write_text("available")
    (nested/"state").write_text("failed")

    # Nested project-service failure does not share or delete control/auth state.
    (nested/"state").unlink()

    assert (control/"health").read_text() == "ok"
    assert (auth/"session-store").read_text() == "available"
