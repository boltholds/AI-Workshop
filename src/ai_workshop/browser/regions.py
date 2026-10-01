from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from playwright.async_api import Page


class PageRegion(BaseModel):
    kind: Literal["page"] = "page"
    full_page: bool = False


class SelectorRegion(BaseModel):
    kind: Literal["selector"] = "selector"
    selector: str = Field(min_length=1)


class CoordinateRegion(BaseModel):
    kind: Literal["coordinates"] = "coordinates"
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class ResolvedRegion(BaseModel):
    kind: Literal["page", "selector", "coordinates"]
    clip: dict[str, float] | None
    full_page: bool = False
    selector: str | None = None


RegionRequest = PageRegion | SelectorRegion | CoordinateRegion


class CaptureRegion:
    @staticmethod
    async def resolve(page: Page, request: RegionRequest) -> ResolvedRegion:
        if isinstance(request, PageRegion):
            if request.full_page:
                return ResolvedRegion(kind="page", clip=None, full_page=True)
            viewport = page.viewport_size
            if viewport is None:
                raise ValueError("page viewport is unavailable")
            return ResolvedRegion(
                kind="page",
                clip={
                    "x": 0.0,
                    "y": 0.0,
                    "width": float(viewport["width"]),
                    "height": float(viewport["height"]),
                },
            )

        if isinstance(request, SelectorRegion):
            locator = page.locator(request.selector)
            count = await locator.count()
            if count != 1:
                raise ValueError(f"selector must match exactly one element; matched {count}")
            box = await locator.bounding_box()
            if box is None:
                raise ValueError("selected element has no visible bounding box")
            return ResolvedRegion(
                kind="selector",
                selector=request.selector,
                clip={key: float(box[key]) for key in ("x", "y", "width", "height")},
            )

        viewport = page.viewport_size
        if viewport is None:
            raise ValueError("page viewport is unavailable")
        if request.x + request.width > viewport["width"] or request.y + request.height > viewport["height"]:
            raise ValueError("coordinate region exceeds viewport")
        return ResolvedRegion(
            kind="coordinates",
            clip={
                "x": float(request.x),
                "y": float(request.y),
                "width": float(request.width),
                "height": float(request.height),
            },
        )
