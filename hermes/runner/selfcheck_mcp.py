"""Tiny MCP server (streamable HTTP) used by the configuration attestation. It
exposes one tool named like the knowledge tools and records whether the
Authorization header carried the expected bearer. No knowledge data."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EXPECTED = os.environ.get("SELFCHECK_TOKEN", "")
TOOLS = [
    {
        "name": "search_knowledge",
        "description": "self-check",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]
seen: dict = {"auth_ok": False, "calls": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # quiet
        return

    def _send(self, status: int, payload: dict | None = None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/selfcheck/seen":
            return self._send(200, seen)
        return self._send(405)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {EXPECTED}" and EXPECTED:
            seen["auth_ok"] = True
        method = msg.get("method")
        req_id = msg.get("id")
        if method == "initialize":
            result = {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "selfcheck", "version": "0"},
            }
            return self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": result})
        if method == "notifications/initialized":
            return self._send(202)
        if method == "tools/list":
            return self._send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        if method == "tools/call":
            seen["calls"] += 1
            return self._send(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": "SELFCHECK-OK"}],
                        "isError": False,
                    },
                },
            )
        return self._send(
            200,
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": "unknown method"},
            },
        )


def main():
    port = int(os.environ.get("SELFCHECK_PORT", "8799"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"event": "selfcheck.listening", "port": port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
