from pathlib import Path

import pytest

from ai_workshop.config import ProjectMount, WorkshopConfig
from ai_workshop.workspace.paths import PathPolicy


def policy_for(root: Path) -> PathPolicy:
    cfg = WorkshopConfig(projects=[ProjectMount(project_id="p", host=root, container="/workspace/p", mode="rw")])
    return PathPolicy(cfg, host_paths=True)


def test_resolves_nested_path(tmp_path: Path):
    assert policy_for(tmp_path).resolve("p", "a/b.txt") == (tmp_path / "a" / "b.txt").resolve()


def test_rejects_parent_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="outside project root"):
        policy_for(tmp_path).resolve("p", "../escape.txt")


def test_rejects_absolute_path(tmp_path: Path):
    with pytest.raises(ValueError, match="relative"):
        policy_for(tmp_path).resolve("p", "/etc/passwd")


def test_rejects_unknown_project(tmp_path: Path):
    with pytest.raises(KeyError, match="unknown"):
        policy_for(tmp_path).resolve("unknown", "x")


def test_rejects_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside-workshop"
    outside.mkdir(exist_ok=True)
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside project root"):
        policy_for(tmp_path).resolve("p", "link/secret.txt")
