from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ForgejoTarget:
    service_id: str


class ForgejoBackupExecutor(Protocol):
    def backup(self, target: ForgejoTarget, destination: Path) -> None: ...
    def restore(self, target: ForgejoTarget, artifact: Path) -> None: ...


class ForgejoAdapter:
    def __init__(
        self,
        targets: dict[str, ForgejoTarget],
        *,
        executor: ForgejoBackupExecutor,
    ):
        self.targets = dict(targets)
        self.executor = executor

    def snapshot(self, target_id: str, destination: Path) -> None:
        target = self._target(target_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        diagnostics = destination.with_suffix(destination.suffix + ".failed.json")
        try:
            self.executor.backup(target, temporary)
            if not temporary.is_file():
                raise RuntimeError("Forgejo backup did not produce an artifact")
            temporary.replace(destination)
            diagnostics.unlink(missing_ok=True)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            diagnostics.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "target_id": target_id,
                        "code": "FORGEJO_BACKUP_FAILED",
                        "message": type(exc).__name__,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            raise RuntimeError("Forgejo backup failed") from None

    def restore(self, target_id: str, artifact: Path) -> None:
        target = self._target(target_id)
        if not artifact.is_file():
            raise FileNotFoundError("Forgejo backup artifact is unavailable")
        self.executor.restore(target, artifact)

    def _target(self, target_id: str) -> ForgejoTarget:
        target = self.targets.get(target_id)
        if target is None:
            raise KeyError(f"unknown Forgejo target: {target_id}")
        return target
