from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image
from pydantic import BaseModel

from ai_workshop.browser.artifacts import ArtifactRef
from ai_workshop.browser.regions import (
    CaptureRegion,
    CoordinateRegion,
    PageRegion,
    SelectorRegion,
)
from ai_workshop.browser.runtime import BrowserRuntime


class ScreenshotRequest(BaseModel):
    page_id: str
    region: PageRegion | SelectorRegion | CoordinateRegion
    session_id: str | None = None


class ScreenshotService:
    def __init__(self, runtime: BrowserRuntime, artifacts_dir: Path) -> None:
        self._runtime = runtime
        self._artifacts_dir = artifacts_dir

    async def capture(self, request: ScreenshotRequest) -> ArtifactRef:
        page = self._runtime.get_page(request.page_id)
        resolved = await CaptureRegion.resolve(page, request.region)
        session_id = request.session_id or str(uuid4())
        artifact_id = str(uuid4())
        directory = self._artifacts_dir / session_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"screenshot-{artifact_id}.png"

        kwargs: dict[str, object] = {"path": str(path), "type": "png"}
        if resolved.full_page:
            kwargs["full_page"] = True
        elif resolved.clip is not None:
            kwargs["clip"] = resolved.clip
        await page.screenshot(**kwargs)

        with Image.open(path) as image:
            width, height = image.size
        return ArtifactRef(
            id=artifact_id,
            media_type="image/png",
            path=str(path),
            width=width,
            height=height,
        )
