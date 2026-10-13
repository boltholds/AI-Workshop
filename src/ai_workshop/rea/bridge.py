"""Authenticated Streamable HTTP bridge to one persistent REA stdio server."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.types import ListPromptsResult, ListResourcesResult
from starlette.responses import JSONResponse
from starlette.routing import Route


class BearerAuth:
    def __init__(self, app, token: str):
        self.app = app
        self.expected = ('Bearer ' + token).encode()

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            headers = dict(scope.get('headers', []))
            if not hmac.compare_digest(headers.get(b'authorization', b''), self.expected):
                await JSONResponse({'error': 'unauthorized'}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(command: StdioServerParameters, *, token: str):
    if not token.strip():
        raise ValueError('REA bridge token is required')
    session = None
    capabilities = None
    lock = asyncio.Lock()

    async def forward(method, *args, **kwargs):
        async with lock:
            if session is None:
                raise RuntimeError('REA is unavailable')
            return await getattr(session, method)(*args, **kwargs)

    async def list_tools(ctx, params):
        return await forward('list_tools', params=params)

    async def call_tool(ctx, params):
        return await forward('call_tool', params.name, params.arguments, meta=params.meta)

    async def list_resources(ctx, params):
        if capabilities.resources is None:
            return ListResourcesResult(resources=[])
        return await forward('list_resources', params=params)

    async def read_resource(ctx, params):
        return await forward('read_resource', str(params.uri))

    async def list_prompts(ctx, params):
        if capabilities.prompts is None:
            return ListPromptsResult(prompts=[])
        return await forward('list_prompts', params=params)

    async def get_prompt(ctx, params):
        return await forward('get_prompt', params.name, params.arguments)

    async def health(request):
        try:
            # Pings must remain available during long analysis calls.
            if session is None:
                raise RuntimeError('not initialized')
            await asyncio.wait_for(session.send_ping(), timeout=3)
            return JSONResponse({'status': 'ok', 'server': 'rea'})
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503)

    server = Server('WAI REA bridge', on_list_tools=list_tools, on_call_tool=call_tool,
                    on_list_resources=list_resources, on_read_resource=read_resource,
                    on_list_prompts=list_prompts, on_get_prompt=get_prompt)
    app = server.streamable_http_app(json_response=True, stateless_http=True,
                                     host='0.0.0.0', custom_starlette_routes=[Route('/health', health)])
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        nonlocal session, capabilities
        async with stdio_client(command) as streams:
            async with ClientSession(*streams, read_timeout_seconds=600) as child:
                initialized = await asyncio.wait_for(child.initialize(), timeout=30)
                session, capabilities = child, initialized.capabilities
                try:
                    async with original_lifespan(app):
                        yield
                finally:
                    session = None

    app.router.lifespan_context = lifespan
    return BearerAuth(app, token)


def load_app():
    # The REA child never inherits the bridge bearer token or arbitrary host env.
    child_env = {key: os.environ[key] for key in (
        'PATH', 'HOME', 'JAVA_HOME', 'GHIDRA_INSTALL_DIR', 'REA_ANALYSIS_PROVIDER',
        'REA_GHIDRA_STARTUP_TIMEOUT_MS', 'REA_LOG_LEVEL', 'XDG_CONFIG_HOME',
        'XDG_CACHE_HOME', 'XDG_DATA_HOME',
    ) if key in os.environ}
    command = StdioServerParameters(command='/opt/rea/node_modules/.bin/rea', args=['mcp'],
                                    cwd='/data', env=child_env)
    return create_app(command, token=os.environ.get('AI_WORKSHOP_REA_TOKEN', ''))
