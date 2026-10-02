from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import ssl
import threading

from ai_workshop.certificates.local_ca import LocalCertificateAuthority


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"workshop-tls-ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def test_local_ca_certificate_completes_trusted_tls_handshake(tmp_path: Path):
    ca = LocalCertificateAuthority(state_root=tmp_path / "pki")
    issued = ca.issue("workshop.local")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(
        certfile=str(issued.certificate_path),
        keyfile=str(issued.private_key_path),
    )
    server.socket = server_context.wrap_socket(
        server.socket,
        server_side=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        context = ssl.create_default_context(
            cafile=str(ca.ca_certificate_path),
        )
        with socket.create_connection(
            ("127.0.0.1", server.server_address[1]),
            timeout=5,
        ) as raw:
            with context.wrap_socket(
                raw,
                server_hostname="workshop.local",
            ) as tls:
                tls.sendall(
                    b"GET /health HTTP/1.1\r\n"
                    b"Host: workshop.local\r\n"
                    b"Connection: close\r\n\r\n"
                )
                response = bytearray()
                while True:
                    chunk = tls.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
        assert b"200 OK" in response
        assert b"workshop-tls-ok" in response
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
