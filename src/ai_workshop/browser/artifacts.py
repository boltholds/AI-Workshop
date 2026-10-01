from __future__ import annotations

from pydantic import BaseModel


class ArtifactRef(BaseModel):
    id: str
    media_type: str
    path: str
    width: int | None = None
    height: int | None = None
