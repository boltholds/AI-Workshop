from __future__ import annotations

import base64
import json
from typing import Literal

from ai_workshop.gateway.browser_client import BrowserClient


def _region(
    mode: Literal["page", "selector", "coordinates"],
    *,
    full_page: bool = False,
    selector: str | None = None,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, object]:
    if mode == "page":
        return {"kind": "page", "full_page": full_page}
    if mode == "selector":
        if not selector:
            raise ValueError("selector is required for selector mode")
        return {"kind": "selector", "selector": selector}
    values = (x, y, width, height)
    if any(value is None for value in values):
        raise ValueError("x, y, width and height are required for coordinates mode")
    return {"kind": "coordinates", "x": x, "y": y, "width": width, "height": height}


def register_browser_tools(server, client: BrowserClient) -> None:
    from mcp.types import ImageContent, TextContent

    @server.tool()
    def browser_navigate(url: str, session_id: str | None = None) -> str:
        """Navigate the persistent browser or an active recording session."""
        return client.navigate(url, session_id=session_id)

    @server.tool()
    def browser_click(selector: str, session_id: str | None = None) -> dict[str, bool]:
        client.click(selector, session_id=session_id)
        return {"ok": True}

    @server.tool()
    def browser_type(selector: str, text: str, session_id: str | None = None) -> dict[str, bool]:
        client.type_text(selector, text, session_id=session_id)
        return {"ok": True}

    @server.tool(structured_output=False)
    def browser_screenshot(
        mode: Literal["page", "selector", "coordinates"] = "page",
        full_page: bool = False,
        selector: str | None = None,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        session_id: str | None = None,
    ) -> list[TextContent | ImageContent]:
        region = _region(mode, full_page=full_page, selector=selector, x=x, y=y, width=width, height=height)
        artifact = client.screenshot(region, session_id=session_id)
        data = base64.b64encode(client.artifact_bytes(artifact)).decode("ascii")
        return [
            TextContent(type="text", text=json.dumps(artifact, sort_keys=True)),
            ImageContent(type="image", data=data, mime_type="image/png"),
        ]

    @server.tool()
    def browser_record_start(
        mode: Literal["page", "selector", "coordinates"] = "page",
        selector: str | None = None,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> str:
        return client.record_start(_region(mode, selector=selector, x=x, y=y, width=width, height=height))

    @server.tool()
    def browser_record_stop(session_id: str) -> dict[str, object]:
        return client.record_stop(session_id)

    @server.tool(structured_output=False)
    def browser_capture_diagnostics(
        session_id: str,
        variants: Literal["neutral", "time-gradient", "both"] = "both",
        legend: bool = False,
        sensitivity: Literal["auto", "low", "medium", "high"] = "auto",
        max_fps: float = 10.0,
        keep_frames: bool = False,
    ) -> list[TextContent | ImageContent]:
        result = client.capture_diagnostics(
            session_id, variants=variants, legend=legend, sensitivity=sensitivity,
            max_fps=max_fps, keep_frames=keep_frames,
        )
        blocks: list[TextContent | ImageContent] = [
            TextContent(type="text", text=json.dumps(
                {"session_id": result["session_id"], "artifacts": result["artifacts"]}, sort_keys=True
            ))
        ]
        for artifact in result["artifacts"]:
            if artifact["media_type"] == "image/png":
                data = base64.b64encode(client.artifact_bytes(artifact)).decode("ascii")
                blocks.append(ImageContent(type="image", data=data, mime_type="image/png"))
            elif artifact["media_type"] == "application/json":
                blocks.append(TextContent(type="text", text=client.artifact_bytes(artifact).decode("utf-8")))
        return blocks
