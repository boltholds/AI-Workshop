from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ai_workshop.browser.models import ArtifactRef, CaptureRegion
from ai_workshop.browser.regions import resolve_region


class ScreenshotService:
    def __init__(self, artifact_root: Path):
        self.artifact_root = Path(artifact_root)

    def capture(self, page, region: CaptureRegion, *, session_id: str | None = None) -> ArtifactRef:
        session_id = session_id or str(uuid4())
        session_dir = self.artifact_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        output = session_dir / "screenshot.png"
        resolved = resolve_region(page, region)
        kwargs = {"path": str(output), "full_page": resolved.full_page}
        if resolved.clip is not None:
            kwargs["clip"] = resolved.clip
            width = int(resolved.clip["width"])
            height = int(resolved.clip["height"])
        else:
            viewport = page.viewport_size or {}
            width = int(viewport.get("width", 0)) or None
            height = int(viewport.get("height", 0)) or None
        page.screenshot(**kwargs)
        return ArtifactRef(
            id=session_id,
            media_type="image/png",
            path=f"{session_id}/screenshot.png",
            width=width,
            height=height,
        )
