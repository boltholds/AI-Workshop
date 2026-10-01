from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ai_workshop.browser.models import ArtifactRef


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def session_dir(self, session_id: str) -> Path:
        path = self.root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def path(self, session_id: str, name: str) -> Path:
        return self.session_dir(session_id) / name

    def write_json(self, session_id: str, name: str, payload: dict[str, Any]) -> ArtifactRef:
        path = self.path(session_id, name)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return ArtifactRef(id=session_id, media_type="application/json", path=f"{session_id}/{name}")

    def cleanup_frames(self, session_id: str) -> None:
        shutil.rmtree(self.session_dir(session_id) / "frames", ignore_errors=True)
