"""KTS 5.0 server probe: a tiny HTTP server that reports the Python it runs on."""
import http.server
import json
import os
import platform
import socketserver
import sys

PORT = int(os.environ.get("HTTP_PLATFORM_PORT", "8907"))


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        info = {
            "status": "HttpPlatformHandler works and started Python",
            "python": sys.version,
            "executable": sys.executable,
            "version_ok": sys.version_info >= (3, 11),
            "os": platform.platform(),
            "cwd": os.getcwd(),
            "user": os.environ.get("USERNAME", ""),
            "port": PORT,
            "web_config_processPath": sys.executable,
            "web_config_arguments": os.path.join(os.getcwd(), "serve.py"),
            "next": "If the portal later answers 502.3, put these two values into its web.config (processPath / arguments).",
        }
        body = json.dumps(info, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as server:
    server.serve_forever()
