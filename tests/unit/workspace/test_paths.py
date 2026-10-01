from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.paths import PathPolicy


def make_policy(root: Path) -> PathPolicy:
    return PathPolicy(WorkshopConfig(projects={
        "app": ProjectMount(project_id="app", host=root, container=root.as_posix(), mode="rw")
    }))


def test_resolves_nested_path(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "src").mkdir()
    assert make_policy(root).resolve("app", "src/main.py") == (root / "src/main.py").resolve()


def test_rejects_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    with pytest.raises(ValueError, match="escapes project root"):
        make_policy(root).resolve("app", "../secret.txt")


def test_rejects_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    with pytest.raises(ValueError, match="relative"):
        make_policy(root).resolve("app", str((tmp_path / "other").resolve()))


def test_rejects_unknown_project(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown project"):
        make_policy(tmp_path).resolve("missing", "a.txt")


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "app"
    outside = tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes project root"):
        make_policy(root).resolve("app", "link/secret.txt")
