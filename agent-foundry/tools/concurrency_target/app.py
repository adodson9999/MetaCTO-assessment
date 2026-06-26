#!/usr/bin/env python3
"""Minimal, local, air-gapped WRITE target for the concurrent-request-handling task.

Why this exists: DummyJSON is deliberately stateless — its `addNewProduct`
controller returns `{id: frozenData.products.length + 1, ...echoedBody}` and never
persists a record, so the task's write-side assertions (COUNT_AFTER - COUNT_BEFORE
= 50, zero duplicates, zero missing) are structurally unverifiable against it. Per
the Phase-2 owner decision, DummyJSON is left 100% untouched and used read-only for
the concurrent-READ test; this purpose-built endpoint provides a REAL persistence
layer so the concurrent-WRITE test runs for real.

Contract:
  POST /records     body {"test_id": str, ...}  -> 201 {"id", "test_id"} on insert
                                                 -> 409 on duplicate test_id (UNIQUE)
                                                 -> 400 on missing/invalid test_id
  GET  /records/<id>                             -> 200 row | 404
  GET  /health                                   -> 200 {"ok": true}

Design notes that make the concurrency test meaningful:
  - SQLite opened in WAL mode with busy_timeout so 50 concurrent writers serialize
    correctly instead of erroring with "database is locked" — a CORRECT client that
    sends 50 distinct test_ids gets exactly 50 rows (no lost writes); a buggy client
    that sends a duplicate test_id surfaces as a 409 + a count delta != 50.
  - `test_id` carries a UNIQUE constraint so duplicate writes are caught at the DB
    layer, not just by the client.
  - One sqlite3 connection PER request/thread (connections are not thread-safe).

stdlib only. Binds 127.0.0.1 (loopback) — never a public interface.

Usage:
    CONCURRENCY_DB_PATH=/abs/records.db CONCURRENCY_TARGET_PORT=8910 \
        python tools/concurrency_target/app.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("CONCURRENCY_TARGET_PORT", "8910"))
DB_PATH = Path(
    os.environ.get(
        "CONCURRENCY_DB_PATH",
        str(Path(__file__).resolve().parents[2]
            / "data" / "test-concurrent-request-handling" / "records.db"),
    )
).resolve()


def _connect() -> sqlite3.Connection:
    """A fresh connection (WAL + busy_timeout) so concurrent writers serialize
    cleanly rather than raising 'database is locked'."""
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
            "  test_id TEXT NOT NULL UNIQUE,"
            "  payload TEXT,"
            "  created_at TEXT DEFAULT (datetime('now'))"
            ");"
        )
        conn.commit()
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence default stderr logging
        pass

    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path.startswith("/records/"):
            ident = self.path.rsplit("/", 1)[-1]
            conn = _connect()
            try:
                cur = conn.execute(
                    "SELECT id, test_id, payload, created_at FROM records WHERE id = ?",
                    (ident,),
                )
                row = cur.fetchone()
            finally:
                conn.close()
            if not row:
                self._send(404, {"error": f"record '{ident}' not found"})
                return
            self._send(200, {"id": row[0], "test_id": row[1],
                             "payload": row[2], "created_at": row[3]})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/records":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except Exception:  # noqa
            self._send(400, {"error": "invalid JSON body"})
            return
        test_id = data.get("test_id")
        if not isinstance(test_id, str) or not test_id:
            self._send(400, {"error": "missing or invalid 'test_id'"})
            return
        conn = _connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS records ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  test_id TEXT NOT NULL UNIQUE,"
                "  payload TEXT,"
                "  created_at TEXT DEFAULT (datetime('now'))"
                ");"
            )
            cur = conn.execute(
                "INSERT INTO records (test_id, payload) VALUES (?, ?)",
                (test_id, json.dumps(data)),
            )
            conn.commit()
            self._send(201, {"id": cur.lastrowid, "test_id": test_id})
        except sqlite3.IntegrityError:
            # UNIQUE(test_id) violated => a duplicate write was attempted.
            self._send(409, {"error": f"duplicate test_id '{test_id}'"})
        finally:
            conn.close()


def main() -> int:
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print(f"[concurrency-target] listening on http://{HOST}:{PORT}  db={DB_PATH}",
          file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
