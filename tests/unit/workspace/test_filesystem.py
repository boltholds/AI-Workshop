from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.filesystem import FilesystemService
from ai_workshop.workspace.paths import PathPolicy


def service(root: Path) -> FilesystemService:
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=root, container="/workspace/p", mode="rw")])
    return FilesystemService(PathPolicy(cfg, host_paths=True), max_read_bytes=32)


def test_write_read_list_and_search(tmp_path: Path):
    fs = service(tmp_path)
    fs.write("p", "src/a.txt", "hello needle")
    fs.write("p", "src/b.txt", "other")
    assert fs.read("p", "src/a.txt") == "hello needle"
    assert fs.list("p", "src") == ["a.txt", "b.txt"]
    assert fs.search("p", "needle") == [{"path": "src/a.txt", "line": 1, "text": "hello needle"}]


def test_rejects_binary_read(tmp_path: Path):
    (tmp_path / "x.bin").write_bytes(b"\x00\xff")
    with pytest.raises(ValueError, match="binary"):
        service(tmp_path).read("p", "x.bin")


def test_rejects_oversized_read(tmp_path: Path):
    (tmp_path / "big.txt").write_text("x" * 33, encoding="utf-8")
    with pytest.raises(ValueError, match="read limit"):
        service(tmp_path).read("p", "big.txt")


def test_patch_requires_unique_expected_text(tmp_path: Path):
    fs = service(tmp_path)
    fs.write("p", "a.txt", "one one")
    with pytest.raises(ValueError, match="more than once"):
        fs.patch("p", "a.txt", "one", "two")
    fs.patch("p", "a.txt", "one", "two", occurrence=2)
    assert fs.read("p", "a.txt") == "one two"


def test_patch_requires_old_text(tmp_path: Path):
    fs = service(tmp_path)
    fs.write("p", "a.txt", "one")
    with pytest.raises(ValueError, match="not found"):
        fs.patch("p", "a.txt", "missing", "two")
