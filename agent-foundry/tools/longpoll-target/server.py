#!/usr/bin/env python3
"""Local longpoll-target fixture — the air-gapped stand-in for a real long-poll /
hanging-GET backend.

Each channel exposes a long-poll GET that holds an event-less connection open for the
documented poll_timeout_s and then, per the COMPLIANT contract, closes with 204 and an
empty body; when an event is published to that channel (separate POST) the GET closes
immediately with 200 and the event JSON (event_type + a non-empty secondary field).

One channel (`inventory`) is deliberately NON-COMPLIANT — on an event-less poll it
returns 200 with a non-empty body (never 204), and on an event it stalls ~3 s after the
publish (breaking the documented 2 s bound) and emits the WRONG event_type — so the test
suite has a real defect to catch.

Concurrency: waiters are keyed by (channel, key). The harness adds a unique `key` query
param per poll and triggers exactly that key, so parallel agent runs never cross-talk and
an event-less poll's key is simply never published. Stdlib only. Binds 127.0.0.1.

Usage:
    python server.py --host 127.0.0.1 --port 8921
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_config  # noqa: E402

POLL_ROUTES = fixture_config.poll_route_map()
TRIGGER_ROUTES = fixture_config.trigger_route_map()

# (channel, key) -> {"published": bool}. Guarded by COND.
_COND = threading.Condition()
_PENDING: dict[tuple[str, str], dict] = {}


def _event_body(cfg: dict) -> dict:
    """The event a compliant channel emits on publish: correct event_type plus a
    non-empty secondary field."""
    sec = cfg["secondary_field"]
    sample = {"order_id": "ORD-1001", "sku": "SKU-42", "user_id": "USR-7"}.get(sec, "VAL-1")
    return {"event_type": cfg["expected_event_type"], sec: sample,
            "channel": cfg["channel"], "id": "evt-1"}


def _noncompliant_event_body(cfg: dict) -> dict:
    """The non-compliant channel's event: WRONG event_type (but a present secondary
    field) — emitted only after an extra post-publish stall."""
    sec = cfg["secondary_field"]
    sample = {"sku": "SKU-42"}.get(sec, "VAL-1")
    return {"event_type": "message", sec: sample, "channel": cfg["channel"], "id": "evt-1"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa  -- keep test output clean
        return

    # --- response helpers ---
    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(payload)

    def _send_empty(self, code: int) -> None:
        """A genuinely empty body: Content-Length: 0, no bytes written."""
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

    # --- query helpers ---
    def _query(self) -> dict:
        q = urllib.parse.urlparse(self.path).query
        return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}

    # --- data plane ---
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/__health", "/health"):
            self._send_json(200, {"status": "ok"})
            return
        cfg = POLL_ROUTES.get(path)
        if cfg is None:
            self._send_json(404, {"message": "unknown poll channel"})
            return

        q = self._query()
        try:
            timeout_s = float(q.get("timeout", cfg["poll_timeout_s"]))
        except ValueError:
            timeout_s = float(cfg["poll_timeout_s"])
        key = q.get("key", "default")
        ckey = (cfg["channel"], key)

        # Long-poll wait: block up to timeout_s for a publish on (channel, key).
        published = False
        with _COND:
            state = _PENDING.setdefault(ckey, {"published": False})
            deadline = time.monotonic() + timeout_s
            while not state["published"]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                _COND.wait(remaining)
            published = state["published"]
            _PENDING.pop(ckey, None)

        if published:
            if cfg["compliant"]:
                self._send_json(200, _event_body(cfg))
            else:
                # Defect: stall past the 2 s bound, then 200 with the wrong event_type.
                time.sleep(fixture_config.NONCOMPLIANT_EVENT_STALL_S)
                self._send_json(200, _noncompliant_event_body(cfg))
        else:
            # No event within the window.
            if cfg["compliant"]:
                self._send_empty(204)               # documented: 204 + empty body
            else:
                # Defect: 200 with a non-empty body instead of 204 empty.
                self._send_json(200, {"status": "empty", "channel": cfg["channel"]})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        cfg = TRIGGER_ROUTES.get(path)
        if cfg is None:
            self._send_json(404, {"message": "unknown trigger channel"})
            return
        # Drain any request body (ignored; the server owns the event content).
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n:
            self.rfile.read(n)
        key = self._query().get("key", "default")
        ckey = (cfg["channel"], key)
        with _COND:
            state = _PENDING.setdefault(ckey, {"published": False})
            state["published"] = True
            _COND.notify_all()
        self._send_json(200, {"published": True, "channel": cfg["channel"]})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8921)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"longpoll-target listening on http://{a.host}:{a.port} "
          f"(channels={list(POLL_ROUTES)})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
