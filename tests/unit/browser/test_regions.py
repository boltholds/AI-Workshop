import asyncio

import pytest

from ai_workshop.browser.regions import (
    CaptureRegion,
    CoordinateRegion,
    PageRegion,
    SelectorRegion,
)


class FakeLocator:
    def __init__(self, count: int, box: dict[str, float] | None):
        self._count = count
        self._box = box

    async def count(self) -> int:
        return self._count

    async def bounding_box(self):
        return self._box


class FakePage:
    def __init__(self, *, viewport=None, locator=None):
        self.viewport_size = viewport or {"width": 800, "height": 600}
        self._locator = locator

    def locator(self, selector: str):
        assert selector
        return self._locator


async def resolve(page, request):
    return await CaptureRegion.resolve(page, request)


def test_page_region_resolves_viewport() -> None:
    result = asyncio.run(resolve(FakePage(), PageRegion(full_page=False)))
    assert result.full_page is False
    assert result.clip == {"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0}


def test_page_region_full_page_has_no_clip() -> None:
    result = asyncio.run(resolve(FakePage(), PageRegion(full_page=True)))
    assert result.full_page is True
    assert result.clip is None


def test_coordinate_region_resolves_inside_viewport() -> None:
    request = CoordinateRegion(x=10, y=20, width=200, height=100)
    result = asyncio.run(resolve(FakePage(), request))
    assert result.clip == {"x": 10.0, "y": 20.0, "width": 200.0, "height": 100.0}


def test_coordinate_region_rejects_out_of_bounds() -> None:
    request = CoordinateRegion(x=700, y=20, width=200, height=100)
    with pytest.raises(ValueError, match="viewport"):
        asyncio.run(resolve(FakePage(), request))


def test_selector_region_requires_single_match() -> None:
    for count in (0, 2):
        page = FakePage(locator=FakeLocator(count, {"x": 1, "y": 2, "width": 30, "height": 40}))
        with pytest.raises(ValueError, match="exactly one"):
            asyncio.run(resolve(page, SelectorRegion(selector="#target")))


def test_selector_region_resolves_bounding_box() -> None:
    page = FakePage(locator=FakeLocator(1, {"x": 11, "y": 22, "width": 33, "height": 44}))
    result = asyncio.run(resolve(page, SelectorRegion(selector="#target")))
    assert result.clip == {"x": 11.0, "y": 22.0, "width": 33.0, "height": 44.0}
    assert result.selector == "#target"
