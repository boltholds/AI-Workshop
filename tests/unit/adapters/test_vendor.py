from pathlib import Path

import pytest

from ai_workshop.adapters.vendor import GitSubtreeVendor


class FakeCloneRunner:
    def __init__(self):
        self.calls = 0

    def clone(self, source_url: str, ref: str, destination: Path) -> None:
        self.calls += 1
        docker = destination / "docker"
        docker.mkdir(parents=True)
        (docker / "docker-compose.yml").write_text(
            f"# {source_url}@{ref}\nservices: {{}}\n",
            encoding="utf-8",
        )


def test_vendor_requires_pinned_ref(tmp_path: Path):
    vendor = GitSubtreeVendor(
        adapter_id="example",
        source_url="https://example.invalid/repo.git",
        subtree="docker",
        runner=FakeCloneRunner(),
    )
    with pytest.raises(ValueError, match="pinned ref"):
        vendor.vendor("", tmp_path / "out")


def test_vendor_writes_manifest_and_checksum(tmp_path: Path):
    runner = FakeCloneRunner()
    vendor = GitSubtreeVendor(
        adapter_id="example",
        source_url="https://example.invalid/repo.git",
        subtree="docker",
        runner=runner,
    )
    result = vendor.vendor("release/v1", tmp_path / "out")
    assert result.adapter_id == "example"
    assert result.source_url == "https://example.invalid/repo.git"
    assert result.ref == "release/v1"
    assert len(result.sha256) == 64
    assert (tmp_path / "out" / "docker-compose.yml").exists()
    assert (tmp_path / "out" / ".ai-workshop-vendor.json").exists()
    assert runner.calls == 1


def test_vendor_is_idempotent_for_same_verified_ref(tmp_path: Path):
    runner = FakeCloneRunner()
    vendor = GitSubtreeVendor(
        adapter_id="example",
        source_url="https://example.invalid/repo.git",
        subtree="docker",
        runner=runner,
    )
    first = vendor.vendor("release/v1", tmp_path / "out")
    second = vendor.vendor("release/v1", tmp_path / "out")
    assert second == first
    assert runner.calls == 1
