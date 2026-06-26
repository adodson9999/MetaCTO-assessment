#!/usr/bin/env python3
"""A WireMock-equivalent mock backend — the air-gapped local stand-in for one
WireMock instance fronted by the API gateway.

Every received data-plane request is appended to an in-memory journal and can be
read back via the admin API (mirrors WireMock's request journal):

  - GET    /__admin/requests   -> {"service": <name>, "requests": [ {method, path,
                                    headers, body} ... ]}  (every request since the
                                    last reset, in arrival order)
  - DELETE /__admin/requests   -> {"reset": true}  (clears the journal — WireMock's
                                    journal-reset semantics)
  - GET    /__admin/health     -> {"status": "ok", "service": <name>}

Any other path/method is treated as a stubbed data-plane request: it is logged and
answered with this backend's uniquely identifiable body {"service": <name>} and 200.
The raw request body is stored verbatim (a decoded string) so a caller can assert it
was forwarded byte-for-byte; headers are stored as a case-normalized dict.

Stdlib only. Binds 127.0.0.1 (air-gapped). The data plane never mutates anything
outside the in-memory journal.

Usage (standalone, one backend):
    python mock_backend.py --name users-mock --host 127.0.0.1 --port 8921
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Journal:
    """Thread-safe append-only request log (reset via DELETE /__admin/requests)."""

    def __init__(self) -> None:
        self._items: list[dict] = []
        self._lock = threading.Lock()

    def append(self, item: dict) -> None:
        with self._lock:
            self._items.append(item)

    def reset(self) -> None:
        with self._lock:
            self._items = []

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [dict(i) for i in self._items]


def make_handler(name: str, journal: _Journal):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # noqa  -- silence default logging
            return

        # --- helpers ---
        def _send_json(self, code: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            self.wfile.write(payload)

        def _read_body(self) -> str:
            n = int(self.headers.get("Content-Length", 0) or 0)
            if not n:
                return ""
            return self.rfile.read(n).decode("utf-8", errors="replace")

        def _headers_dict(self) -> dict:
            # Case-normalized to Title-Case keys; last value wins on duplicates.
            return {k.title(): v for k, v in self.headers.items()}

        # --- admin plane ---
        def _admin(self, method: str) -> bool:
            path = self.path.split("?", 1)[0]
            if path == "/__admin/requests":
                if method == "GET":
                    self._send_json(200, {"service": name, "requests": journal.snapshot()})
                elif method == "DELETE":
                    journal.reset()
                    self._send_json(200, {"reset": True, "service": name})
                else:
                    self._send_json(405, {"message": "method not allowed on /__admin/requests"})
                return True
            if path in ("/__admin/health", "/health"):
                self._send_json(200, {"status": "ok", "service": name})
                return True
            return False

        # --- data plane: log the request, return this backend's identity body ---
        def _record_and_reply(self, method: str) -> None:
            body = self._read_body()
            path = self.path  # full path incl. query string, logged verbatim
            journal.append({
                "method": method,
                "path": path,
                "headers": self._headers_dict(),
                "body": body,
            })
            self._send_json(200, {"service": name})

        def do_GET(self) -> None:
            if not self._admin("GET"):
                self._record_and_reply("GET")

        def do_DELETE(self) -> None:
            if not self._admin("DELETE"):
                self._record_and_reply("DELETE")

        def do_POST(self) -> None:
            if not self._admin("POST"):
                self._record_and_reply("POST")

        def do_PUT(self) -> None:
            if not self._admin("PUT"):
                self._record_and_reply("PUT")

        def do_PATCH(self) -> None:
            if not self._admin("PATCH"):
                self._record_and_reply("PATCH")

    return Handler


def build_server(name: str, host: str, port: int) -> ThreadingHTTPServer:
    """Construct (but do not start) a mock backend server with its own journal."""
    journal = _Journal()
    srv = ThreadingHTTPServer((host, port), make_handler(name, journal))
    srv.daemon_threads = True
    srv.allow_reuse_address = True
    srv._mock_name = name        # type: ignore[attr-defined]
    srv._mock_journal = journal  # type: ignore[attr-defined]
    return srv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args()
    srv = build_server(a.name, a.host, a.port)
    print(f"mock backend {a.name} listening on http://{a.host}:{a.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
