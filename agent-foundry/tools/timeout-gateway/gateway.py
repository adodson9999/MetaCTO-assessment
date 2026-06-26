#!/usr/bin/env python3
"""Local timeout-gateway fixture — the air-gapped stand-in for a WireMock upstream
stub fronted by a Toxiproxy latency toxic.

It fronts a (simulated) upstream service for several documented endpoints and is
documented to enforce a per-service upstream timeout: when the upstream takes longer
than upstream_timeout_s, a COMPLIANT endpoint gives up at ~upstream_timeout_s and
returns 504 with a safe JSON body and `Connection: close` (it never hangs for the
full injected delay). One endpoint is deliberately NON-COMPLIANT (returns 500, leaks
the upstream URL + a stack frame, and holds the connection open) so the test suite
has a real defect to catch.

Delay injection (Toxiproxy "latency" toxic) is modeled two ways:
  - Per-request header `X-Upstream-Delay-Ms` (used by the harness; concurrency-safe,
    so parallel agents never corrupt each other's toxic state).
  - Control endpoints `PUT /__control/toxic` {"latency_ms": N} and
    `DELETE /__control/toxic` set/clear a global default (mirrors the documented
    Toxiproxy add/delete-toxic REST lifecycle). The per-request header overrides it.

Stdlib only. Binds 127.0.0.1 (air-gapped). Read-only: GET endpoints never mutate
anything; the control endpoints only toggle the injected delay.

Usage:
    python gateway.py --host 127.0.0.1 --port 8911
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_config  # noqa: E402

PATHS = fixture_config.path_map()

# Safe timeout body — no path, no stack, no URL. The compliant contract.
SAFE_TIMEOUT_BODY = {"message": "Upstream request timed out. Please retry shortly."}


def _leaky_500_body(path: str) -> dict:
    """The NON-COMPLIANT endpoint's body: deliberately leaks an internal upstream
    URL, a filesystem path, and a stack frame — the kind of error-detail leak the
    test's body-safety assertion must catch."""
    return {
        "message": "Internal error while contacting upstream",
        "error": f"ETIMEDOUT contacting http://upstream.internal:9000{path}",
        "trace": "at UpstreamClient.call (/srv/app/src/upstream/client.js:42:17)",
    }


class _GlobalToxic:
    """Process-wide default injected delay (the Toxiproxy add/delete-toxic state).
    Overridden per-request by the X-Upstream-Delay-Ms header."""
    def __init__(self) -> None:
        self.latency_ms = 0
        self.lock = threading.Lock()

    def set(self, ms: int) -> None:
        with self.lock:
            self.latency_ms = max(0, int(ms))

    def clear(self) -> None:
        with self.lock:
            self.latency_ms = 0

    def get(self) -> int:
        with self.lock:
            return self.latency_ms


TOXIC = _GlobalToxic()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # --- silence default logging (keeps test output clean) ---
    def log_message(self, *a):  # noqa
        return

    # --- helpers ---
    def _send_json(self, code: int, body: dict, *, close: bool) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        # Connection semantics: compliant timeouts close immediately; the
        # non-compliant endpoint keeps the socket open (the defect under test).
        self.send_header("Connection", "close" if close else "keep-alive")
        self.close_connection = bool(close)
        self.end_headers()
        self.wfile.write(payload)

    def _injected_delay_s(self) -> float:
        hdr = self.headers.get("X-Upstream-Delay-Ms")
        if hdr is not None:
            try:
                return max(0, int(hdr)) / 1000.0
            except ValueError:
                pass
        return TOXIC.get() / 1000.0

    # --- control plane (Toxiproxy-style) ---
    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa
            return {}

    def do_PUT(self) -> None:
        if self.path == "/__control/toxic":
            body = self._read_body()
            TOXIC.set(body.get("latency_ms", fixture_config.INJECTED_DELAY_S * 1000))
            self._send_json(200, {"toxic": "latency", "latency_ms": TOXIC.get()}, close=True)
            return
        self._send_json(404, {"message": "not found"}, close=True)

    def do_DELETE(self) -> None:
        if self.path == "/__control/toxic":
            TOXIC.clear()
            self._send_json(200, {"removed": True}, close=True)
            return
        self._send_json(404, {"message": "not found"}, close=True)

    # --- data plane ---
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/__health", "/health"):
            self._send_json(200, {"status": "ok"}, close=True)
            return
        route = PATHS.get(path)
        if route is None:
            self._send_json(404, {"message": "unknown endpoint"}, close=True)
            return

        timeout_s = route["upstream_timeout_s"]
        delay_s = self._injected_delay_s()

        if delay_s > timeout_s:
            # Upstream is slower than the documented timeout: the gateway must give
            # up at ~timeout_s. It waits the timeout, NOT the full injected delay.
            time.sleep(timeout_s)
            if route["compliant"]:
                self._send_json(504, dict(SAFE_TIMEOUT_BODY), close=True)
            else:
                # Defect: 500 instead of 504, leaky body, connection left open.
                self._send_json(500, _leaky_500_body(path), close=False)
            return

        # Upstream answered within the timeout (or no delay): heal to a fast 200.
        if delay_s > 0:
            time.sleep(delay_s)
        self._send_json(200, {"message": "ok", "service": route["service"], "path": path},
                        close=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8911)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"timeout-gateway listening on http://{a.host}:{a.port} "
          f"(endpoints={list(PATHS)})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
