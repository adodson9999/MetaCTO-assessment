#!/usr/bin/env python3
"""Minimal, local, air-gapped BULK-OPERATION target for the test-bulk-operation-endpoints task.

Why this exists: DummyJSON exposes NO bulk/batch endpoints. It has no Multi-Status
(207) response, no per-item result array, and its write controllers never persist
(addNewProduct returns {id: frozenData.products.length + 1, ...echoedBody} and writes
nothing). So the task's core assertions — response code exactly 207, a per-item status
array, and COUNT_AFTER - COUNT_BEFORE = the valid-item count — are structurally
unverifiable against DummyJSON. Per the standing owner decision, DummyJSON is left
100% untouched; this purpose-built endpoint provides a real, spec-conformant bulk
contract with a real persistence layer so the bulk assertions run for real.

Documented contract (this is the "documented bulk endpoint" under test):
  POST /bulk/<resource>
      body: a JSON array of item objects.
      - If the array length exceeds MAX_BATCH_SIZE (default 100) -> 413 Payload Too
        Large, body {"error": "...", "max_batch_size": N, "received": M}, nothing
        persisted.
      - Otherwise -> 207 Multi-Status, body = a JSON array of exactly one per-item
        result per input item, in input order:
          valid item  -> {"index": i, "status": 201, "id": <new row id>}
          invalid item-> {"index": i, "status": 400,
                          "error": "<message that NAMES the offending field>",
                          "fields": ["<field name>", ...]}
        Each item is valid iff every required field is present AND each present
        required field has the documented JSON type. Only valid items are inserted.
  GET  /bulk/<resource>/count   -> 200 {"count": N}   (rows currently in the table)
  GET  /health                  -> 200 {"ok": true}

Required-field contract for the default resource "products":
  title    : string   (required)
  price    : number   (required; int or float accepted)
  category : string   (required)

Design notes that make the bulk test meaningful:
  - Per-item validation is independent: 8 valid + 2 invalid yields 8x201 + 2x400 in
    ONE 207 envelope, and exactly 8 new rows. A buggy server that 400s a valid item,
    201s an invalid item, or persists the wrong count surfaces as a scenario mismatch.
  - All-invalid batch still returns 207 with every per-item status 400 and inserts 0
    rows (documented behavior for all-invalid batches).
  - Oversize batch is rejected wholesale (413) and inserts 0 rows.
  - One sqlite3 connection per request (connections are not thread-safe). UNIQUE not
    used here — bulk inserts of distinct valid items must all succeed.

stdlib only. Binds 127.0.0.1 (loopback) — never a public interface.

Usage:
    BULK_DB_PATH=/abs/records.db BULK_TARGET_PORT=8920 BULK_MAX_BATCH_SIZE=100 \
        python tools/bulk_target/app.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("BULK_TARGET_PORT", "8920"))
MAX_BATCH_SIZE = int(os.environ.get("BULK_MAX_BATCH_SIZE", "100"))
DB_PATH = Path(
    os.environ.get(
        "BULK_DB_PATH",
        str(Path(__file__).resolve().parents[2]
            / "data" / "test-bulk-operation-endpoints" / "records.db"),
    )
).resolve()

# Documented required fields for the "products" resource, with their JSON types.
# "number" accepts int or float; "string" accepts str.
REQUIRED_FIELDS = [("title", "string"), ("price", "number"), ("category", "string")]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=True)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  scope TEXT,"
            "  title TEXT,"
            "  price REAL,"
            "  category TEXT,"
            "  payload TEXT,"
            "  created_at TEXT DEFAULT (datetime('now'))"
            ");"
        )
        conn.commit()
    finally:
        conn.close()


def _type_ok(value, json_type: str) -> bool:
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "number":
        # bool is a subclass of int in Python; exclude it explicitly.
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if json_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if json_type == "boolean":
        return isinstance(value, bool)
    return True


def _validate_item(item) -> tuple[bool, str, list]:
    """Return (is_valid, error_message, offending_fields). The message NAMES every
    offending field so a tester can assert on the field name."""
    if not isinstance(item, dict):
        return False, "item must be a JSON object", []
    bad: list[str] = []
    reasons: list[str] = []
    for name, jtype in REQUIRED_FIELDS:
        if name not in item:
            bad.append(name)
            reasons.append(f"missing required field '{name}'")
        elif not _type_ok(item[name], jtype):
            bad.append(name)
            reasons.append(f"field '{name}' must be of type {jtype}")
    if bad:
        return False, "; ".join(reasons), bad
    return True, "", []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _scope(self) -> str:
        # Optional per-(run,agent) namespace header so parallel agents never collide
        # on COUNT() — each scopes its own rows. Absent => global scope "".
        return self.headers.get("X-Bulk-Scope", "") or ""

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path.startswith("/bulk/") and self.path.endswith("/count"):
            conn = _connect()
            try:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM records WHERE scope = ?", (self._scope(),)
                )
                self._send(200, {"count": int(cur.fetchone()[0])})
            finally:
                conn.close()
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not (self.path.startswith("/bulk/") and not self.path.endswith("/count")):
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"null")
        except Exception:  # noqa
            self._send(400, {"error": "invalid JSON body"})
            return
        if not isinstance(data, list):
            self._send(400, {"error": "bulk body must be a JSON array of items"})
            return
        if len(data) > MAX_BATCH_SIZE:
            self._send(413, {"error": "batch exceeds maximum size",
                             "max_batch_size": MAX_BATCH_SIZE, "received": len(data)})
            return

        scope = self._scope()
        results = []
        conn = _connect()
        try:
            for i, item in enumerate(data):
                ok, msg, bad = _validate_item(item)
                if not ok:
                    results.append({"index": i, "status": 400, "error": msg, "fields": bad})
                    continue
                cur = conn.execute(
                    "INSERT INTO records (scope, title, price, category, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (scope, item.get("title"), item.get("price"),
                     item.get("category"), json.dumps(item)),
                )
                results.append({"index": i, "status": 201, "id": cur.lastrowid})
            conn.commit()
        finally:
            conn.close()
        # 207 Multi-Status — the documented bulk response code.
        self._send(207, results)


def main() -> int:
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print(f"[bulk-target] listening on http://{HOST}:{PORT}  db={DB_PATH}  "
          f"max_batch_size={MAX_BATCH_SIZE}", file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
