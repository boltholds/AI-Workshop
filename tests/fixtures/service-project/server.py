from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path


DATA_DIR = Path("/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
COUNT_FILE = DATA_DIR / "start-count"
try:
    count = int(COUNT_FILE.read_text(encoding="utf-8").strip()) + 1
except (FileNotFoundError, ValueError):
    count = 1
COUNT_FILE.write_text(str(count), encoding="utf-8")
print(f"started {count}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps({"status": "ok", "start_count": count}).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
