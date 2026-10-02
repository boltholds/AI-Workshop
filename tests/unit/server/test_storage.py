from pathlib import Path

import pytest

from ai_workshop.server.storage import ServerStorage


def test_server_storage_creates_canonical_project_and_run_roots(tmp_path: Path):
    storage = ServerStorage(tmp_path / "server-state")

    project = storage.project_root("app")
    run = storage.run_root("run-123")

    assert project == (tmp_path / "server-state" / "projects" / "app").resolve()
    assert run == (tmp_path / "server-state" / "runs" / "run-123").resolve()
    assert project.is_dir()
    assert run.is_dir()


@pytest.mark.parametrize(
    "identifier",
    ["../escape", "/absolute", "--flag", "nested/name", ""],
)
def test_storage_rejects_invalid_project_and_run_ids(tmp_path: Path, identifier: str):
    storage = ServerStorage(tmp_path / "server-state")

    with pytest.raises(ValueError):
        storage.project_root(identifier)

    with pytest.raises(ValueError):
        storage.run_root(identifier)


@pytest.mark.parametrize(
    "relative",
    ["../escape", "../../escape", "/absolute/path"],
)
def test_runtime_mount_rejects_storage_escape(tmp_path: Path, relative: str):
    storage = ServerStorage(tmp_path / "server-state")
    storage.run_root("run-123")

    with pytest.raises(ValueError, match="escape|relative"):
        storage.resolve_run_path("run-123", relative)


def test_resolve_run_path_accepts_nested_relative_path(tmp_path: Path):
    storage = ServerStorage(tmp_path / "server-state")

    resolved = storage.resolve_run_path("run-123", "src/package/file.py")

    assert resolved == (
        tmp_path
        / "server-state"
        / "runs"
        / "run-123"
        / "src"
        / "package"
        / "file.py"
    ).resolve()


def test_runtime_mount_rejects_symlink_escape(tmp_path: Path):
    storage = ServerStorage(tmp_path / "server-state")
    run_root = storage.run_root("run-123")
    outside = tmp_path / "outside"
    outside.mkdir()
    (run_root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escape"):
        storage.resolve_run_path("run-123", "link/secret.txt")
