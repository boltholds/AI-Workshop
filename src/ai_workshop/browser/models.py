from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PageRegion(BaseModel):
    kind: Literal["page"] = "page"
    full_page: bool = False


class SelectorRegion(BaseModel):
    kind: Literal["selector"] = "selector"
    selector: str = Field(min_length=1)


class CoordinateRegion(BaseModel):
    kind: Literal["coordinates"] = "coordinates"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


CaptureRegion = PageRegion | SelectorRegion | CoordinateRegion


class ResolvedRegion(BaseModel):
    clip: dict[str, float | int] | None = None
    full_page: bool = False


class ArtifactRef(BaseModel):
    id: str
    media_type: str
    path: str
    width: int | None = None
    height: int | None = None
