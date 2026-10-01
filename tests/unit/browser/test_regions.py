import pytest

from ai_workshop.browser.models import CoordinateRegion, PageRegion, SelectorRegion
from ai_workshop.browser.regions import resolve_region


class Locator:
    def __init__(self, count: int, box=None):
        self._count = count
        self._box = box
    def count(self): return self._count
    def bounding_box(self): return self._box


class Page:
    viewport_size = {"width": 800, "height": 600}
    def __init__(self, locator=None): self._locator = locator
    def locator(self, selector): return self._locator


def test_page_region_viewport_and_full_page():
    page = Page()
    viewport = resolve_region(page, PageRegion(full_page=False))
    full = resolve_region(page, PageRegion(full_page=True))
    assert viewport.clip is None and viewport.full_page is False
    assert full.clip is None and full.full_page is True


def test_coordinate_region_resolves_clip():
    resolved = resolve_region(Page(), CoordinateRegion(x=10, y=20, width=300, height=200))
    assert resolved.clip == {"x": 10, "y": 20, "width": 300, "height": 200}


def test_coordinate_region_rejects_out_of_bounds():
    with pytest.raises(ValueError, match="viewport"):
        resolve_region(Page(), CoordinateRegion(x=700, y=500, width=200, height=200))


def test_selector_region_requires_single_match():
    with pytest.raises(ValueError, match="exactly one"):
        resolve_region(Page(Locator(0)), SelectorRegion(selector="#missing"))
    with pytest.raises(ValueError, match="exactly one"):
        resolve_region(Page(Locator(2)), SelectorRegion(selector=".duplicate"))


def test_selector_region_uses_bounding_box():
    box = {"x": 1.5, "y": 2.5, "width": 100.0, "height": 50.0}
    assert resolve_region(Page(Locator(1, box)), SelectorRegion(selector="#target")).clip == box
