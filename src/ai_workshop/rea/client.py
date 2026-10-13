"""Synchronous facade for WAI's synchronous downstream proxy contract."""
from __future__ import annotations

import asyncio

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams


class ReaMcpClient:
    def __init__(self, url: str, *, token: str, timeout: float = 600, uds: str | None = None):
        self.url, self._token, self.timeout = url, token, timeout
        self.uds = uds

    def _run(self, method, *args, collection=None):
        async def run():
            timeout = min(self.timeout, 20) if collection else self.timeout
            transport = httpx2.AsyncHTTPTransport(uds=self.uds, trust_env=False)
            async with httpx2.AsyncClient(transport=transport, headers={'Authorization': 'Bearer ' + self._token},
                                          timeout=timeout, trust_env=False,
                                          follow_redirects=False) as http:
                async with streamable_http_client(self.url, http_client=http) as streams:
                    async with ClientSession(streams[0], streams[1], read_timeout_seconds=timeout) as session:
                        initialized = await session.initialize()
                        if collection in {'resources', 'prompts'} and getattr(initialized.capabilities, collection) is None:
                            return []
                        if collection:
                            items, cursor, seen = [], None, set()
                            while True:
                                result = await getattr(session, method)(params=PaginatedRequestParams(cursor=cursor))
                                items.extend(x.model_dump(mode='json', by_alias=True, exclude_none=True) for x in getattr(result, collection))
                                cursor = result.next_cursor
                                if cursor is None:
                                    return items
                                if cursor in seen or len(seen) >= 1000:
                                    raise RuntimeError('invalid downstream pagination')
                                seen.add(cursor)
                        result = await getattr(session, method)(*args)
                        return result.model_dump(mode='json', by_alias=True, exclude_none=True)
        # No retries: a lost response does not imply that a tool had no effect.
        return asyncio.run(run())

    def list_tools(self): return self._run('list_tools', collection='tools')
    def list_resources(self): return self._run('list_resources', collection='resources')
    def list_prompts(self): return self._run('list_prompts', collection='prompts')
    def call_tool(self, name, arguments): return self._run('call_tool', name, dict(arguments))
    def read_resource(self, uri): return self._run('read_resource', uri)
    def get_prompt(self, name, arguments): return self._run('get_prompt', name, dict(arguments))
