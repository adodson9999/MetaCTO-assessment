#!/usr/bin/env python3
"""Local API gateway fixture — the air-gapped stand-in for a Kong/AWS API Gateway /
CloudFront routing layer fronting one WireMock instance per downstream service.

For each documented route it forwards the request to exactly one backend over real
TCP, with method, path, headers, and body unchanged, and returns the backend's
response to the caller unchanged. Two routes carry seeded defects so the test suite
has real, catchable findings (exactly like the timeout-gateway's one non-compliant
endpoint):
  - GET /api/orders/7  is MISROUTED to payments-mock (documented: orders-mock).
  - PUT /api/payments/9 has its JSON body MUTATED in transit (a field injected).

When the target backend is unreachable (stopped — the service-down test) the gateway
returns exactly 503 and forwards to no one.

Control plane (mirrors stopping/starting a WireMock instance):
  - PUT    /__control/down  {"service": "<name>"}  -> stop that backend
  - DELETE /__control/down  {"service": "<name>"}  -> restart that backend
These delegate to the FixtureController owned by the launcher (run_fixture.py).

Stdlib only. Binds 127.0.0.1 (air-gapped).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_config  # noqa: E402

ROUTES = fixture_config.route_map()

# Hop-by-hop headers the gateway must not blindly forward (urllib sets Host/Length).
_DROP_HEADERS = {"host", "content-length", "connection", "accept-encoding"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa
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

    def _send_raw(self, code: int, raw: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(n) if n else b""

    def _forward_headers(self) -> dict:
        return {k: v for k, v in self.headers.items() if k.lower() not in _DROP_HEADERS}

    @property
    def _controller(self):
        return getattr(self.server, "controller", None)

    # --- control plane ---
    def _maybe_control(self, method: str) -> bool:
        path = self.path.split("?", 1)[0]
        if path != "/__control/down":
            return False
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:  # noqa
            payload = {}
        service = payload.get("service")
        ctrl = self._controller
        if not service or service not in fixture_config.service_names():
            self._send_json(400, {"message": "unknown or missing service"})
            return True
        if ctrl is None:
            self._send_json(501, {"message": "no fixture controller attached"})
            return True
        if method == "PUT":
            ctrl.down(service)
            self._send_json(200, {"service": service, "down": True})
        elif method == "DELETE":
            ctrl.up(service)
            self._send_json(200, {"service": service, "down": False})
        else:
            self._send_json(405, {"message": "method not allowed"})
        return True

    # --- data plane (routing/proxy) ---
    def _route(self, method: str) -> None:
        path = self.path  # forwarded verbatim, query string included
        body = self._read_body()
        route = ROUTES.get((method.upper(), path.split("?", 1)[0]))
        if route is None:
            self._send_json(404, {"message": "no route", "method": method, "path": path})
            return

        target = route["actual_backend"]
        # In-transit body mutation defect: inject a field into the JSON body.
        fwd_body = body
        if route.get("mutate_body") and body:
            try:
                obj = json.loads(body)
                if isinstance(obj, dict):
                    obj["gateway_tampered"] = True
                    fwd_body = json.dumps(obj).encode()
            except Exception:  # noqa
                pass

        url = f"http://127.0.0.1:{fixture_config.backend_port(target)}{path}"
        req = urllib.request.Request(
            url, data=(fwd_body if method.upper() not in ("GET", "DELETE") or fwd_body else None),
            method=method.upper(), headers=self._forward_headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                ct = r.headers.get("Content-Type", "application/json")
                self._send_raw(r.getcode(), raw, ct)
        except urllib.error.HTTPError as e:
            # Backend answered with an error status — return it unchanged.
            raw = e.read()
            self._send_raw(e.code, raw, e.headers.get("Content-Type", "application/json"))
        except Exception:  # noqa  -- connection refused/reset/timeout: backend is down
            self._send_json(503, {"message": "Service Unavailable",
                                  "upstream_unreachable": target})

    # --- method entry points ---
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] in ("/__health", "/health"):
            self._send_json(200, {"status": "ok"})
            return
        self._route("GET")

    def do_DELETE(self) -> None:
        if not self._maybe_control("DELETE"):
            self._route("DELETE")

    def do_PUT(self) -> None:
        if not self._maybe_control("PUT"):
            self._route("PUT")

    def do_POST(self) -> None:
        self._route("POST")

    def do_PATCH(self) -> None:
        self._route("PATCH")


def build_gateway(host: str, port: int, controller=None) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    srv.allow_reuse_address = True
    srv.controller = controller  # type: ignore[attr-defined]
    return srv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=fixture_config.GATEWAY_PORT)
    a = ap.parse_args()
    srv = build_gateway(a.host, a.port)
    print(f"routing-gateway listening on http://{a.host}:{a.port} "
          f"(routes={list(ROUTES)})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
