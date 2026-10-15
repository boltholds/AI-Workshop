import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time


def test_rea_smoke_waits_for_slow_discovery(monkeypatch, capsys):
    """A healthy gateway can take longer than the old 12-second smoke budget."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            method = request['method']
            if method == 'tools/list':
                result = {'tools': [{'name': name} for name in (
                    'mcp.servers_list', 'mcp.tools_list', 'mcp.tool_call', 'git_status') ]}
            elif method == 'tools/call':
                time.sleep(13)
                result = {'content': [{'type': 'text', 'text': json.dumps({
                    'name': 'sample', 'inputSchema': {'type': 'object'}})}]}
            else:
                result = {}
            body = json.dumps({'jsonrpc': '2.0', 'id': request.get('id'), 'result': result}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec = importlib.util.spec_from_file_location('rea_smoke', Path('scripts/mcp-rea-smoke.py'))
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        monkeypatch.setattr('sys.argv', ['mcp-rea-smoke.py', '--url', f'http://127.0.0.1:{server.server_port}/mcp'])
        smoke.main()
        assert '1 tools with input schemas' in capsys.readouterr().out
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
