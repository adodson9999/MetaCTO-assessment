#!/usr/bin/env python3
"""Local /resources search-and-filter SUT — the air-gapped stand-in for a seeded
search/filter API.

Seeded with EXACTLY the 20 records from the task spec (see seed.py): 15 active
(8 category A, 7 category B) + 5 inactive. A second small /widgets collection is the
held-out set for the staged evolution gate. The server NEVER touches DummyJSON.

It enforces the documented filter contract (see seed.py docstring):
  GET /<collection>?status=&category=
    - status   : enum {active, inactive}; out-of-enum -> 400 referencing "status".
    - category : free-form exact-match; an unmatched value -> 200 + empty list.
    - AND across recognized filters; unknown params -> 400 referencing the param.
    - body: {"<list_field>": [...], "total": N}

Stdlib only. Binds 127.0.0.1 (air-gapped). Read-only: GET never mutates the seed;
there are NO write endpoints, so the 20 records are immutable for the process life.

Usage:
    python server.py --host 127.0.0.1 --port 8920
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed  # noqa: E402


def _filter(collection: str, params: dict):
    """Apply the documented filter contract. Returns (status_code, body_dict).
    Pure read: never mutates the seed."""
    list_field, records = seed.COLLECTIONS[collection]

    # 1. Unknown-parameter check first (STRICT policy -> 400 referencing the param).
    for name in params:
        if name not in seed.RECOGNIZED_PARAMS:
            return 400, {"message": f"Unknown query parameter '{name}' is not a "
                                    f"recognized filter for this endpoint."}

    # 2. Enum validation of the status filter (out-of-enum -> 400 referencing "status").
    if "status" in params and params["status"] not in seed.STATUS_ENUM:
        return 400, {"message": f"Invalid value for the 'status' parameter: "
                                f"'{params['status']}'. Allowed values are "
                                f"{list(seed.STATUS_ENUM)}."}

    # 3. AND-filter across recognized filters (category is free-form exact match).
    out = list(records)
    if "status" in params:
        out = [r for r in out if r.get("status") == params["status"]]
    if "category" in params:
        out = [r for r in out if r.get("category") == params["category"]]

    return 200, {list_field: out, "total": len(out)}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa - keep test output clean
        return

    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/__health", "/health", "/test"):
            self._send_json(200, {"status": "ok",
                                  "service": "filter-resource-server",
                                  "collections": list(seed.COLLECTIONS)})
            return
        if path not in seed.COLLECTIONS:
            self._send_json(404, {"message": f"Unknown collection '{path}'."})
            return
        # Last value wins for repeated keys; keep_blank_values so ?x= is seen.
        raw = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        params = {k: v[-1] for k, v in raw.items()}
        code, body = _filter(path, params)
        self._send_json(code, body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8920)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    counts = {c: len(recs) for c, (_, recs) in seed.COLLECTIONS.items()}
    print(f"filter-resource-server listening on http://{a.host}:{a.port} "
          f"(seeded collections={counts})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
