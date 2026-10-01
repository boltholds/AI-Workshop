from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.filesystem import FilesystemService
from ai_workshop.workspace.paths import PathPolicy


def make_service(root: Path, *, mode: str = "rw") -> FilesystemService:
    config = WorkshopConfig(projects={
        "app": ProjectMount(project_id="app", host=root, container=root.as_posix(), mode=mode)
    })
    return FilesystemService(PathPolicy(config), config)


def test_list_and_read_text(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    svc = make_service(root)
    assert [entry.name for entry in svc.list("app", ".")] == ["a.txt"]
    assert svc.read("app", "a.txt") == "hello"


def test_write_text_creates_parent_directories(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    svc = make_service(root)
    svc.write("app", "src/new.txt", "data")
    assert (root / "src/new.txt").read_text(encoding="utf-8") == "data"


def test_read_only_project_rejects_write(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    with pytest.raises(PermissionError, match="read-only"):
        make_service(root, mode="ro").write("app", "x.txt", "x")


def test_read_rejects_binary(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    (root / "bin.dat").write_bytes(b"\x00\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        make_service(root).read("app", "bin.dat")


def test_read_enforces_max_bytes(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    (root / "big.txt").write_text("123456", encoding="utf-8")
    with pytest.raises(ValueError, match="maximum"):
        make_service(root).read("app", "big.txt", max_bytes=5)


def test_patch_requires_unique_expected_text(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    (root / "x.txt").write_text("one one", encoding="utf-8")
    with pytest.raises(ValueError, match="appears 2 times"):
        make_service(root).patch("app", "x.txt", "one", "two")


def test_patch_replaces_exact_occurrence(tmp_path: Path) -> None:
    root = tmp_path / "app"; root.mkdir()
    (root / "x.txt").write_text("one one", encoding="utf-8")
    make_service(root).patch("app", "x.txt", "one", "two", occurrence=2)
    assert (root / "x.txt").read_text(encoding="utf-8") == "one two"


def test_search_finds_text_recursively(tmp_path: Path) -> None:
    root = tmp_path / "app"; (root / "src").mkdir(parents=True)
    (root / "src/a.txt").write_text("needle here", encoding="utf-8")
    (root / "src/b.txt").write_text("nothing", encoding="utf-8")
    matches = make_service(root).search("app", "needle")
    assert [(m.path, m.line, m.text) for m in matches] == [("src/a.txt", 1, "needle here")]
