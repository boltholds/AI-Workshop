from __future__ import annotations

from ai_workshop.browser.models import CaptureRegion, CoordinateRegion, PageRegion, ResolvedRegion, SelectorRegion


def resolve_region(page, region: CaptureRegion) -> ResolvedRegion:
    if isinstance(region, PageRegion):
        return ResolvedRegion(full_page=region.full_page)
    if isinstance(region, SelectorRegion):
        locator = page.locator(region.selector)
        count = locator.count()
        if count != 1:
            raise ValueError(f"selector must match exactly one element, got {count}")
        box = locator.bounding_box()
        if box is None:
            raise ValueError("selected element has no visible bounding box")
        return ResolvedRegion(clip=box)
    if isinstance(region, CoordinateRegion):
        viewport = page.viewport_size
        if viewport is None:
            raise ValueError("coordinate capture requires a fixed viewport")
        if region.x + region.width > viewport["width"] or region.y + region.height > viewport["height"]:
            raise ValueError("coordinate region exceeds viewport")
        return ResolvedRegion(
            clip={"x": region.x, "y": region.y, "width": region.width, "height": region.height}
        )
    raise TypeError(f"unsupported region type: {type(region).__name__}")
