from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_workshop.projects.models import ExternalProject, GitManagedProject
from ai_workshop.projects.store import ProjectStore
from ai_workshop.server.storage import ServerStorage


def make_store(tmp_path: Path, *, external_roots: tuple[Path, ...] = ()) -> ProjectStore:
    return ProjectStore(
        storage=ServerStorage(tmp_path / "server-storage"),
        state_path=tmp_path / "state" / "projects.json",
        external_roots=external_roots,
    )


def test_register_git_uses_canonical_server_project_path(tmp_path: Path):
    store = make_store(tmp_path)

    project = store.register_git(
        "demo",
        remote_url="git@example.test:team/demo.git",
    )

    assert isinstance(project, GitManagedProject)
    assert project.project_id == "demo"
    assert project.path == (tmp_path / "server-storage" / "projects" / "demo").resolve()
    assert project.remote_url == "git@example.test:team/demo.git"
    assert store.get("demo") == project


def test_clone_destination_cannot_escape_project_store(tmp_path: Path):
    store = make_store(tmp_path)

    with pytest.raises(ValueError, match="project"):
        store.register_git(
            "../escape",
            remote_url="git@example.test:team/demo.git",
        )


def test_duplicate_project_id_is_rejected(tmp_path: Path):
    store = make_store(tmp_path)
    store.register_git("demo", remote_url="git@example.test:team/demo.git")

    with pytest.raises(ValueError, match="already registered"):
        store.register_git("demo", remote_url="git@example.test:team/other.git")


def test_external_project_must_be_inside_configured_external_root(tmp_path: Path):
    allowed = tmp_path / "external"
    allowed.mkdir()
    project_path = allowed / "existing-project"
    project_path.mkdir()
    store = make_store(tmp_path, external_roots=(allowed,))

    project = store.register_external("external-demo", project_path)

    assert isinstance(project, ExternalProject)
    assert project.path == project_path.resolve()

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="external root"):
        store.register_external("outside", outside)


def test_external_project_rejects_symlink_escape(tmp_path: Path):
    allowed = tmp_path / "external"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = allowed / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    store = make_store(tmp_path, external_roots=(allowed,))
    with pytest.raises(ValueError, match="external root"):
        store.register_external("escape", link)


def test_remove_registration_keeps_checkout(tmp_path: Path):
    store = make_store(tmp_path)
    project = store.register_git("demo", remote_url="git@example.test:team/demo.git")
    marker = project.path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    store.remove_registration("demo")

    with pytest.raises(KeyError):
        store.get("demo")
    assert marker.read_text(encoding="utf-8") == "keep"


def test_delete_checkout_removes_only_managed_checkout(tmp_path: Path):
    store = make_store(tmp_path)
    project = store.register_git("demo", remote_url="git@example.test:team/demo.git")
    (project.path / "delete.txt").write_text("delete", encoding="utf-8")

    store.delete_checkout("demo")

    assert not project.path.exists()
    with pytest.raises(KeyError):
        store.get("demo")


def test_delete_checkout_rejects_external_project(tmp_path: Path):
    allowed = tmp_path / "external"
    allowed.mkdir()
    project_path = allowed / "repo"
    project_path.mkdir()
    store = make_store(tmp_path, external_roots=(allowed,))
    store.register_external("external", project_path)

    with pytest.raises(ValueError, match="external"):
        store.delete_checkout("external")

    assert project_path.is_dir()


def test_registry_load_rejects_tampered_managed_path(tmp_path: Path):
    state_path = tmp_path / "state" / "projects.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "projects": [
                    {
                        "kind": "git-managed",
                        "project_id": "demo",
                        "path": str((tmp_path / "outside").resolve()),
                        "remote_url": "git@example.test:team/demo.git",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="canonical project path"):
        ProjectStore(
            storage=ServerStorage(tmp_path / "server-storage"),
            state_path=state_path,
        )


def test_list_is_stable_and_sorted(tmp_path: Path):
    store = make_store(tmp_path)
    store.register_git("zeta", remote_url="git@example.test:zeta.git")
    store.register_git("alpha", remote_url="git@example.test:alpha.git")

    assert [item.project_id for item in store.list()] == ["alpha", "zeta"]


def test_git_managed_project_rejects_http_remote_with_embedded_credentials(tmp_path: Path):
    store = make_store(tmp_path)

    with pytest.raises(ValueError, match="credential"):
        store.register_git(
            "secret-url",
            remote_url="https://user:super-secret@example.test/team/repo.git",
        )
