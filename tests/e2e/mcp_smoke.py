from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import Client


async def main() -> None:
    async with Client("http://127.0.0.1:8765/mcp") as client:
        projects = await client.call_tool("workspace_projects", {})
        assert not projects.is_error

        write = await client.call_tool(
            "filesystem_write",
            {"project_id": "fixture", "path": "created-by-mcp.txt", "content": "written through MCP\n"},
        )
        assert not write.is_error

        shell = await client.call_tool(
            "shell_exec",
            {"project_id": "fixture", "argv": ["python", "-c", "print('mcp-shell-ok')"]},
        )
        assert not shell.is_error
        assert "mcp-shell-ok" in str(shell.structured_content or shell.content)

    assert Path("tests/fixtures/host-project/created-by-mcp.txt").read_text(encoding="utf-8") == "written through MCP\n"


if __name__ == "__main__":
    asyncio.run(main())
