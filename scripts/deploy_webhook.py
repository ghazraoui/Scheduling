#!/usr/bin/env python3
"""Lightweight deploy webhook listener.

Runs on localhost:9000 behind Nginx. GitHub Actions sends a POST with
a shared secret to trigger git pull on the deploy branch.
"""

import hmac
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

DEPLOY_SECRET = os.environ.get("DEPLOY_SECRET", "")
DEPLOY_DIR = "/opt/slg/scheduling"
PORT = 9000


class DeployHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deploy":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_length)

        token = self.headers.get("X-Deploy-Token", "")
        if not hmac.compare_digest(token, DEPLOY_SECRET):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return

        try:
            result = subprocess.run(
                ["git", "pull", "origin", "deploy"],
                cwd=DEPLOY_DIR,
                capture_output=True,
                text=True,
                timeout=30,
            )
            response = {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
            code = 200 if result.returncode == 0 else 500
        except Exception as e:
            response = {"status": "error", "message": str(e)}
            code = 500

        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    if not DEPLOY_SECRET:
        print("ERROR: DEPLOY_SECRET environment variable required")
        sys.exit(1)
    server = HTTPServer(("127.0.0.1", PORT), DeployHandler)
    print(f"Deploy webhook listening on 127.0.0.1:{PORT}")
    server.serve_forever()
