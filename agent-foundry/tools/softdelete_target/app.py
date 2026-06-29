#!/usr/bin/env python3
"""Minimal, local, air-gapped SOFT-DELETE target for the test-soft-delete-behavior task.

Why this exists: the task requires a resource API whose DELETE performs a *soft* delete
(the row survives in the database with a non-null `deleted_at` timestamp and
`is_deleted = true`, while GET-by-id returns 404 and the record disappears from the
collection listing) AND a directly-queryable database to confirm that survival.
DummyJSON cannot satisfy this — it is deliberately stateless (its DELETE controller
echoes `{...item, isDeleted:true, deletedOn:<ts>}` but persists nothing and exposes no
queryable DB), so the task's DB-row / deleted_at / collection-exclusion assertions are
structurally unverifiable against it. Per the Phase-2 owner decision and the user's
note, DummyJSON is left 100% untouched; this purpose-built endpoint provides the REAL
soft-delete semantics + the SQLite file the harness queries directly.

Contract:
  POST   /resources                 body {<fields>}          -> 201 {"id", <fields>, "deleted_at":null, "is_deleted":false}
  GET    /resources/<id>                                     -> 200 {row} if live | 404 {"error"} if soft-deleted or missing
  GET    /resources                                          -> 200 {"resources":[live rows only], "total"}
  GET    /resources?include_deleted=true                     -> 200 {"resources":[live + deleted], "total"} (deleted carry non-null deleted_at)
  DELETE /resources/<id>                                     -> 200 {"id","is_deleted":true,"deleted_at":<iso8601>} (soft) | 404 if missing/already-deleted
  GET    /health                                             -> 200 {"ok":true}

Design notes that make the soft-delete test meaningful:
  - `resources` table keeps EVERY row forever. DELETE never removes a row; it sets
    is_deleted=1 and deleted_at=<UTC ISO-8601, set at delete time>. So a direct
    `SELECT id, deleted_at, is_deleted FROM resources WHERE id = ?` after a DELETE
    returns exactly one row with a non-null deleted_at and is_deleted=1 — the heart of
    the test.
  - The 404 body for a soft-deleted resource carries NO field values (just
    {"error":"resource not found"}), so the "GET-by-id leaks no resource data" check
    passes for a correct server.
  - The default collection listing EXCLUDES soft-deleted rows; only
    ?include_deleted=true re-includes them. No pagination, so "iterate all records"
    is exact.
  - Server-generated string ids (UUID hex) so concurrent agents never collide and the
    SELECT id = '<RESOURCE_ID>' form (quoted string id) matches the spec.

stdlib only. Binds 127.0.0.1 (loopback) — never a public interface.

Usage:
    SOFTDELETE_DB_PATH=/abs/resources.db SOFTDELETE_TARGET_PORT=8950 \
        python tools/softdelete_target/app.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = int(os.environ.get("SOFTDELETE_TARGET_PORT", "8950"))
DB_PATH = Path(
    os.environ.get(
        "SOFTDELETE_DB_PATH",
        str(Path(__file__).resolve().parents[2]
            / "data" / "test-soft-delete-behavior" / "resources.db"),
    )
).resolve()

# Reserved keys that are never treated as caller-supplied "fields".
_RESERVED = {"id", "deleted_at", "is_deleted", "created_at"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=True)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS resources ("
        "  id TEXT PRIMARY KEY,"
        "  body TEXT NOT NULL,"
        "  created_at TEXT DEFAULT (datetime('now')),"
        "  deleted_at TEXT,"            # NULL until soft-deleted
        "  is_deleted INTEGER NOT NULL DEFAULT 0"
        ");"
    )


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        _ensure_table(conn)
        conn.commit()
    finally:
        conn.close()


def _row_to_obj(row: tuple, *, include_flags: bool) -> dict:
    """row = (id, body, created_at, deleted_at, is_deleted)."""
    rid, body, created_at, deleted_at, is_deleted = row
    try:
        fields = json.loads(body) if body else {}
    except Exception:  # noqa
        fields = {}
    fields = {k: v for k, v in fields.items() if k not in _RESERVED}
    obj = {"id": rid, **fields,
           "deleted_at": deleted_at,
           "is_deleted": bool(is_deleted)}
    if not include_flags:
        # live single-resource view still carries the (null) flags for transparency
        pass
    return obj


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence default stderr logging
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ----- GET ----------------------------------------------------------- #
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self._send(200, {"ok": True})
            return
        if path.startswith("/resources/"):
            self._get_one(path.rsplit("/", 1)[-1])
            return
        if path == "/resources":
            qs = parse_qs(parsed.query)
            include = _truthy(qs.get("include_deleted", ["false"])[0])
            self._get_collection(include)
            return
        self._send(404, {"error": "not found"})

    def _get_one(self, rid: str) -> None:
        conn = _connect()
        try:
            _ensure_table(conn)
            cur = conn.execute(
                "SELECT id, body, created_at, deleted_at, is_deleted "
                "FROM resources WHERE id = ?", (rid,))
            row = cur.fetchone()
        finally:
            conn.close()
        # 404 for a missing OR soft-deleted resource — body carries NO field values.
        if not row or int(row[4]) == 1:
            self._send(404, {"error": "resource not found"})
            return
        self._send(200, _row_to_obj(row, include_flags=False))

    def _get_collection(self, include_deleted: bool) -> None:
        conn = _connect()
        try:
            _ensure_table(conn)
            if include_deleted:
                cur = conn.execute(
                    "SELECT id, body, created_at, deleted_at, is_deleted "
                    "FROM resources ORDER BY created_at")
            else:
                cur = conn.execute(
                    "SELECT id, body, created_at, deleted_at, is_deleted "
                    "FROM resources WHERE is_deleted = 0 ORDER BY created_at")
            rows = cur.fetchall()
        finally:
            conn.close()
        items = [_row_to_obj(r, include_flags=include_deleted) for r in rows]
        self._send(200, {"resources": items, "total": len(items)})

    # ----- POST ---------------------------------------------------------- #
    def do_POST(self) -> None:
        if self.path != "/resources":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except Exception:  # noqa
            self._send(400, {"error": "invalid JSON body"})
            return
        if not isinstance(data, dict):
            self._send(400, {"error": "body must be a JSON object"})
            return
        fields = {k: v for k, v in data.items() if k not in _RESERVED}
        rid = "res-" + uuid.uuid4().hex
        conn = _connect()
        try:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO resources (id, body, created_at, deleted_at, is_deleted) "
                "VALUES (?, ?, ?, NULL, 0)",
                (rid, json.dumps(fields), _now_iso()))
            conn.commit()
        finally:
            conn.close()
        self._send(201, {"id": rid, **fields,
                         "deleted_at": None, "is_deleted": False})

    # ----- DELETE -------------------------------------------------------- #
    def do_DELETE(self) -> None:
        if not self.path.startswith("/resources/"):
            self._send(404, {"error": "not found"})
            return
        rid = self.path.rsplit("/", 1)[-1]
        ts = _now_iso()
        conn = _connect()
        try:
            _ensure_table(conn)
            cur = conn.execute(
                "SELECT is_deleted FROM resources WHERE id = ?", (rid,))
            row = cur.fetchone()
            if not row or int(row[0]) == 1:
                self._send(404, {"error": "resource not found"})
                return
            # SOFT delete: keep the row, set the tombstone fields.
            conn.execute(
                "UPDATE resources SET is_deleted = 1, deleted_at = ? WHERE id = ?",
                (ts, rid))
            conn.commit()
        finally:
            conn.close()
        self._send(200, {"id": rid, "is_deleted": True, "deleted_at": ts})


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print(f"[softdelete-target] listening on http://{HOST}:{PORT}  db={DB_PATH}",
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
