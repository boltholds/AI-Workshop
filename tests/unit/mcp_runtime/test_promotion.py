from __future__ import annotations

import pytest

from ai_workshop.mcp_runtime.promotion import McpPromotionRegistry


def test_promote_collision_requires_explicit_name():
    registry = McpPromotionRegistry()
    registry.promote("docs", "search")

    with pytest.raises(
        ValueError,
        match="collision requires explicit name",
    ):
        registry.promote("code", "search")

    second = registry.promote(
        "code",
        "search",
        exposed_name="code_search",
    )

    assert second.exposed_name == "code_search"
    assert [item.exposed_name for item in registry.list()] == [
        "code_search",
        "search",
    ]


def test_unpromote_is_non_destructive_to_other_tools():
    registry = McpPromotionRegistry()
    registry.promote("docs", "search")
    registry.promote("code", "symbols")

    registry.unpromote("search")

    assert [item.exposed_name for item in registry.list()] == ["symbols"]
