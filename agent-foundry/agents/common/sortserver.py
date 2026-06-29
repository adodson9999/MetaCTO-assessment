"""Isolated, in-process, loopback-only reference resource for the sorting task.

This is deterministic harness substrate — NOT an agent and NOT a debate-gated
prompt line. It exists so the sorting task can be exercised end-to-end (seed -> sort
-> verify, including the 400 cases) WITHOUT ever touching DummyJSON, which every
other agent in this foundry tests read-only and which must never be modified.

It implements the idealized sort contract on one collection:
    GET /resources?sort=<field>&order=<asc|desc>
      - sort in {name, created_at}        -> 200 {"resources":[...sorted...],"total":N}
      - sort is any other value           -> 400 {"message":"Invalid sort field: <field>"}
      - order present and not in {asc,desc}-> 400 {"message":"Invalid order direction: <order>"}
      - order absent                       -> defaults to asc
      - name sorts case-insensitively; created_at sorts as ISO-8601 instants.

The server is seeded with whatever records the AGENT emitted, binds 127.0.0.1 on an
ephemeral port, and is torn down by the harness. It is read-only over HTTP: only GET
is served; there is no mutation endpoint, so an agent's plan can never change it.
Stdlib only. Air-gapped.
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sorting_spec import SORTABLE_FIELDS, VALID_ORDERS, parse_iso


class _Resource:
    """Holds the seeded records and answers idealized sort queries deterministically."""

    def __init__(self, records: list[dict], name_field: str, timestamp_field: str):
        # Defensive copy so the served data is never aliased to the caller's list.
        self.records = [dict(r) for r in records if isinstance(r, dict)]
        self.name_field = name_field
        self.timestamp_field = timestamp_field

    def _key(self, field: str):
        if field == self.timestamp_field:
            return lambda r: parse_iso(r.get(field))
        return lambda r: str(r.get(field, "")).lower()

    def query(self, sort: str | None, order: str | None):
        """Return (status_code, body_dict)."""
        if sort is None:
            sort = self.name_field
        if sort not in SORTABLE_FIELDS:
            return 400, {"message": f"Invalid sort field: {sort}"}
        if order is not None and order not in VALID_ORDERS:
            return 400, {"message": f"Invalid order direction: {order}"}
        reverse = (order == "desc")
        try:
            ordered = sorted(self.records, key=self._key(sort), reverse=reverse)
        except Exception:  # noqa  -- a malformed seed value should not 500 the harness
            return 400, {"message": f"Unsortable values for field: {sort}"}
        return 200, {"resources": ordered, "total": len(ordered)}


def _make_handler(resource: _Resource):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path.rstrip("/") not in ("/resources", ""):
                self._send(404, {"message": "Not found"})
                return
            qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            sort = qs.get("sort", [None])[0]
            order = qs.get("order", [None])[0]
            status, body = resource.query(sort, order)
            self._send(status, body)

        # Only GET is served; no other verb can mutate the reference resource.
        def _send(self, status: int, body: dict):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # silence the default stderr access log
            return

    return Handler


class ReferenceServer:
    """Context manager that serves a seeded reference resource on 127.0.0.1:<ephemeral>."""

    def __init__(self, records: list[dict], name_field: str = "name",
                 timestamp_field: str = "created_at"):
        self._resource = _Resource(records, name_field, timestamp_field)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self._resource))
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address
        return f"http://127.0.0.1:{port}"

    def __enter__(self) -> "ReferenceServer":
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)
        return False
