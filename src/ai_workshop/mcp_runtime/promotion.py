from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PromotedMcpTool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exposed_name: str = Field(min_length=1, max_length=200)
    server_id: str = Field(min_length=1)
    downstream_name: str = Field(min_length=1)


class McpPromotionRegistry:
    def __init__(self):
        self._by_name: dict[str, PromotedMcpTool] = {}

    def list(self) -> tuple[PromotedMcpTool, ...]:
        return tuple(self._by_name[key] for key in sorted(self._by_name))

    def promote(
        self,
        server_id: str,
        downstream_name: str,
        *,
        exposed_name: str | None = None,
    ) -> PromotedMcpTool:
        name = exposed_name or downstream_name
        existing = self._by_name.get(name)
        if existing is not None:
            if (
                existing.server_id == server_id
                and existing.downstream_name == downstream_name
            ):
                return existing
            if exposed_name is None:
                raise ValueError(
                    "promoted MCP tool name collision requires explicit name"
                )
            raise ValueError(f"promoted MCP tool name already exists: {name}")

        promoted = PromotedMcpTool(
            exposed_name=name,
            server_id=server_id,
            downstream_name=downstream_name,
        )
        self._by_name[name] = promoted
        return promoted

    def unpromote(self, exposed_name: str) -> None:
        if exposed_name not in self._by_name:
            raise KeyError(f"unknown promoted MCP tool: {exposed_name}")
        self._by_name.pop(exposed_name)

    def resolve(self, exposed_name: str) -> PromotedMcpTool:
        item = self._by_name.get(exposed_name)
        if item is None:
            raise KeyError(f"unknown promoted MCP tool: {exposed_name}")
        return item
