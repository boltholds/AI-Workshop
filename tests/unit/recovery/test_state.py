from pathlib import Path

import pytest

from ai_workshop.recovery.state import StateAdapterRegistry, StateSnapshotService
from ai_workshop.recovery.store import SnapshotStore


class MemoryAdapter:
    def __init__(self):
        self.values = {"primary": b"before"}
        self.fail_restore = False

    def snapshot(self, target_id: str, destination: Path) -> None:
        destination.write_bytes(self.values[target_id])

    def restore(self, target_id: str, artifact: Path) -> None:
        if self.fail_restore:
            raise RuntimeError("restore failed")
        self.values[target_id] = artifact.read_bytes()


def service(tmp_path: Path):
    adapter = MemoryAdapter()
    registry = StateAdapterRegistry({"memory": adapter})
    return StateSnapshotService(registry, SnapshotStore(tmp_path / "state")), adapter


def test_state_snapshot_create_and_restore_requires_confirmation(tmp_path: Path):
    svc, adapter = service(tmp_path)
    artifact = svc.create("memory", "primary")
    assert artifact.adapter_id == "memory"
    assert artifact.target_id == "primary"
    assert (tmp_path / "state" / artifact.snapshot_id / "state" / "artifact.bin").read_bytes() == b"before"

    adapter.values["primary"] = b"after"
    with pytest.raises(PermissionError, match="confirmation"):
        svc.restore(artifact.snapshot_id, "missing")

    token = svc.prepare_restore(artifact.snapshot_id).token
    result = svc.restore(artifact.snapshot_id, token)
    assert result.restored is True
    assert adapter.values["primary"] == b"before"


def test_unknown_state_adapter_is_rejected(tmp_path: Path):
    registry = StateAdapterRegistry({})
    svc = StateSnapshotService(registry, SnapshotStore(tmp_path / "state"))
    with pytest.raises(KeyError, match="unknown state adapter"):
        svc.create("missing", "primary")


def test_failed_state_restore_keeps_artifact(tmp_path: Path):
    svc, adapter = service(tmp_path)
    artifact = svc.create("memory", "primary")
    artifact_path = tmp_path / "state" / artifact.snapshot_id / "state" / "artifact.bin"
    adapter.fail_restore = True
    token = svc.prepare_restore(artifact.snapshot_id).token

    with pytest.raises(RuntimeError, match="restore failed"):
        svc.restore(artifact.snapshot_id, token)

    assert artifact_path.read_bytes() == b"before"


def test_state_snapshot_metadata_binds_adapter_and_target(tmp_path: Path):
    svc, _ = service(tmp_path)
    artifact = svc.create("memory", "primary")
    loaded = svc.load(artifact.snapshot_id)
    assert loaded.adapter_id == "memory"
    assert loaded.target_id == "primary"
    assert loaded.sha256 == artifact.sha256
