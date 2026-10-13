#!/usr/bin/env python3
"""Read-only MCP discovery smoke check for the Server Mode analysis extension."""
from __future__ import annotations

import json
import sys
import urllib.request

URL = 'http://127.0.0.1:8765/mcp'
REQUIRED = {
    'filesystem_read', 'filesystem_write', 'shell_exec',
    'binary_analyze', 'analysis_get_results', 'cargo_test',
}


def post(method: str, request_id: int | None, params: dict | None = None) -> dict:
    payload = {'jsonrpc': '2.0', 'method': method}
    if request_id is not None:
        payload['id'] = request_id
    if params is not None:
        payload['params'] = params
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        URL, data=data, method='POST',
        headers={
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'MCP-Protocol-Version': '2025-06-18',
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read().decode('utf-8')
    if not body.strip():
        return {}
    if body.lstrip().startswith('{'):
        return json.loads(body)
    events = [line[5:].strip() for line in body.splitlines() if line.startswith('data:')]
    if not events:
        raise RuntimeError('No JSON-RPC response received from MCP server')
    return json.loads(events[-1])


def main() -> int:
    init = post('initialize', 1, {
        'protocolVersion': '2025-06-18',
        'capabilities': {},
        'clientInfo': {'name': 'wai-rollout-smoke', 'version': '1.0'},
    })
    if 'error' in init or 'result' not in init:
        raise RuntimeError('MCP initialization failed: ' + repr(init.get('error')))
    post('notifications/initialized', None)
    listed = post('tools/list', 2)
    if 'error' in listed:
        raise RuntimeError('MCP tools/list failed: ' + repr(listed['error']))
    names = {item['name'] for item in listed.get('result', {}).get('tools', [])}
    missing = REQUIRED - names
    print('MCP tools detected:', len(names))
    if missing:
        print('Missing:', ', '.join(sorted(missing)), file=sys.stderr)
        return 1
    print('Analysis tool discovery passed:', ', '.join(sorted(REQUIRED)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
