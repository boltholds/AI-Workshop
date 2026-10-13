import asyncio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import ListToolsResult, Tool

async def tools(ctx, params):
    page = params.cursor if params else None
    return ListToolsResult(tools=[Tool(name='second' if page else 'first', input_schema={'type': 'object'})], next_cursor=None if page else 'page2')
server = Server('paged-tools-only', on_list_tools=tools)
async def main():
    async with stdio_server() as streams:
        await server.run(*streams, server.create_initialization_options())
asyncio.run(main())
