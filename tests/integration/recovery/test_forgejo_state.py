from __future__ import annotations

from pathlib import Path

import pytest

from ai_workshop.recovery.adapters.forgejo import (
    ForgejoAdapter,
    ForgejoTarget,
)


class Executor:
    def __init__(self):
        self.fail = False
        self.restored = []

    def backup(self, target, destination):
        if self.fail:
            raise OSError("internal secret path /token")
        destination.write_bytes(b"new-good-backup")

    def restore(self, target, artifact):
        self.restored.append((target.service_id, artifact.read_bytes()))


def test_forgejo_failed_backup_keeps_last_good_snapshot(tmp_path):
    executor=Executor()
    adapter=ForgejoAdapter(
        {"internal": ForgejoTarget(service_id="forgejo")},
        executor=executor,
    )
    artifact=tmp_path/"forgejo.bin"
    artifact.write_bytes(b"last-good")

    executor.fail=True
    with pytest.raises(RuntimeError, match="Forgejo backup failed"):
        adapter.snapshot("internal", artifact)

    assert artifact.read_bytes() == b"last-good"
    diagnostics=artifact.with_suffix(".bin.failed.json")
    assert diagnostics.is_file()
    text=diagnostics.read_text()
    assert "FORGEJO_BACKUP_FAILED" in text
    assert "/token" not in text


def test_forgejo_success_atomically_replaces_backup(tmp_path):
    executor=Executor()
    adapter=ForgejoAdapter(
        {"internal": ForgejoTarget(service_id="forgejo")},
        executor=executor,
    )
    artifact=tmp_path/"forgejo.bin"
    artifact.write_bytes(b"old")

    adapter.snapshot("internal", artifact)

    assert artifact.read_bytes() == b"new-good-backup"
