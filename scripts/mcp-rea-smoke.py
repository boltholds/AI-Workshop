#!/usr/bin/env python3
"""Read-only smoke check through the existing WAI gateway, using stdlib only."""
import importlib.util
from functools import partial
from pathlib import Path

spec = importlib.util.spec_from_file_location('analysis_smoke', Path(__file__).with_name('mcp-analysis-smoke.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    import argparse
    from urllib.parse import urlsplit
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8765/mcp')
    parser.add_argument('--timeout', type=float, default=120, help='HTTP response timeout in seconds (default: 120)')
    args = parser.parse_args()
    if not 0 < args.timeout <= 600:
        parser.error('timeout must be greater than zero and at most 600 seconds')
    parsed = urlsplit(args.url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/mcp' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error('expected a loopback WAI MCP URL')
    module.URL = args.url
    post = partial(module.post, timeout=args.timeout)
    init = post('initialize', 1, {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'wai-rea-smoke', 'version': '1.0'}})
    if 'error' in init:
        raise RuntimeError('WAI MCP initialization failed')
    post('notifications/initialized', None)
    names = {t['name'] for t in post('tools/list', 2)['result']['tools']}
    if not {'mcp.servers_list', 'mcp.tools_list', 'mcp.tool_call', 'git_status'} <= names:
        raise RuntimeError('REA proxy tools or existing Git tool missing')
    result = post('tools/call', 3, {'name': 'mcp.tools_list', 'arguments': {'server_id': 'rea'}})
    if 'error' in result or result.get('result', {}).get('isError'):
        raise RuntimeError('REA discovery through WAI failed: ' + repr(result)[:1500])
    import json
    # SDK serializes each member of a list as a separate text content block.
    tools = []
    for block in result['result'].get('content', []):
        if block.get('type') == 'text':
            value = json.loads(block['text'])
            tools.extend(value if isinstance(value, list) else [value])
    if not tools or not all('name' in t and 'inputSchema' in t for t in tools):
        raise RuntimeError('REA tool schemas missing')
    print(f'REA discovered through WAI: {len(tools)} tools with input schemas')


if __name__ == '__main__':
    main()
