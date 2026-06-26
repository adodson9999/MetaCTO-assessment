#!/usr/bin/env python3
"""Minimal, local, air-gapped EVENT-DRIVEN service for the Test-Event-Driven-API-Triggers task.

Why this exists: DummyJSON is a plain REST API. It consumes NO message topics, ships
NO consumer, NO dead-letter queue, and NO consumer-liveness signal (its only AWS usage
is S3 object storage). So the task's assertions — "a well-formed event drives the target
resource to the correct state within 5s", "a malformed event is logged ERROR + lands in
the DLQ within 30s without crashing the consumer" — are structurally unverifiable against
DummyJSON (an event published nowhere changes nothing). Per the owner decision, DummyJSON
is left 100% untouched; THIS purpose-built service provides a real event-driven system so
the full trigger lifecycle runs for real and the metric is genuinely measured.

It is the air-gapped, stdlib-only equivalent of a Kafka/RabbitMQ/SQS consumer: the named
CLIs (kafka-console-producer / rabbitmqadmin publish / aws sqs send-message) are the
production publish paths; here `POST /publish` is the loopback publish path. The consumer
contract it implements is the IDEAL one the agents are briefed from, so a correctly-built
consumer yields Event Processing Success Rate = 100% and DLQ Delivery Rate = 100%.

HTTP surface (all on 127.0.0.1 — never a public interface):
  POST /publish              body {"topic","event"}        -> 202 {"message_id","offset","topic"}
  GET  /<resource>/<id>                                     -> 200 {resource state} | 404
  GET  /health                                              -> 200 {"ok": true, "consumer_alive": true}
  POST /admin/reset          body {"resource","resource_id","state_field","state"} -> 200 (test setup)
  POST /dlq/consume          body {"topic"}                 -> 200 {"message"|null} (consume one DLQ msg)
  GET  /dlq?topic=...                                       -> 200 {"messages":[...]} (peek DLQ)
  GET  /logs?since=<unix_float>                             -> 200 {"lines":[...]} (consumer log tail)

Consumer contract (the behavior under test):
  - A background consumer thread drains each topic's queue. For an event whose payload
    contains every required field for that topic, it APPLIES the documented state
    transition to the resource store (SQLite) and logs an INFO line.
  - For a MALFORMED event (any required field missing) it (a) NEVER crashes — the
    processing loop catches the validation failure; (b) logs an ERROR line naming the
    message_id/offset and a parsing/validation error; (c) routes the raw message to the
    DLQ; (d) changes NO resource state.

Design notes that make the test meaningful:
  - One sqlite3 connection per request/thread (connections are not thread-safe); WAL +
    busy_timeout so the consumer thread and HTTP threads serialize cleanly.
  - The consumer logs to a JSON-lines file so the harness can grep it exactly like a real
    consumer's stdout, filtering by timestamp and severity.
  - Topic contracts (required fields + transition) are loaded from a config the gold
    builder and harness share, so there is one source of truth for "what each topic does".

stdlib only. Usage:
    EVENTBUS_DB_PATH=/abs/eventbus.db EVENTBUS_LOG_PATH=/abs/consumer_log.jsonl \
    EVENTBUS_TOPICS_PATH=/abs/topics.json EVENTBUS_PORT=8930 \
        python tools/eventbus_target/app.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = int(os.environ.get("EVENTBUS_PORT", "8930"))
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get(
    "EVENTBUS_DB_PATH",
    str(ROOT / "data" / "test-event-driven-api-triggers" / "eventbus.db"))).resolve()
LOG_PATH = Path(os.environ.get(
    "EVENTBUS_LOG_PATH",
    str(ROOT / "data" / "test-event-driven-api-triggers" / "consumer_log.jsonl"))).resolve()
TOPICS_PATH = Path(os.environ.get(
    "EVENTBUS_TOPICS_PATH",
    str(ROOT / "data" / "test-event-driven-api-triggers" / "topics.json"))).resolve()

# How fast the consumer drains the queue. Small, but non-zero, so the well-formed
# state change is a REAL asynchronous transition the harness observes by polling
# (well under the 5s SLA), not a synchronous side effect of publish.
CONSUMER_POLL_SECONDS = float(os.environ.get("EVENTBUS_CONSUMER_POLL_SECONDS", "0.1"))

_log_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=True)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS resources (
              resource     TEXT NOT NULL,
              resource_id  TEXT NOT NULL,
              state_field  TEXT NOT NULL,
              state        TEXT,
              updated_at   TEXT DEFAULT (datetime('now')),
              PRIMARY KEY (resource, resource_id)
            );
            CREATE TABLE IF NOT EXISTS topic_queue (
              offset     INTEGER PRIMARY KEY AUTOINCREMENT,
              topic      TEXT NOT NULL,
              message_id TEXT NOT NULL,
              payload    TEXT NOT NULL,
              status     TEXT NOT NULL DEFAULT 'pending',  -- pending|done|dlq
              created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS dlq (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              topic      TEXT NOT NULL,
              message_id TEXT NOT NULL,
              offset     INTEGER,
              payload    TEXT NOT NULL,
              reason     TEXT NOT NULL,
              consumed   INTEGER NOT NULL DEFAULT 0,
              created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def load_topics() -> dict:
    """topic -> {resource, resource_id, state_field, pre_state, expected_state,
                 event_type, required_fields:[...]}."""
    try:
        data = json.loads(TOPICS_PATH.read_text())
    except Exception:  # noqa
        return {}
    return {t["topic"]: t for t in data.get("topics", [])}


def log_line(level: str, topic: str, message_id, msg: str, **extra) -> None:
    rec = {"ts": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
           "level": level, "topic": topic, "message_id": message_id, "msg": msg}
    rec.update(extra)
    with _log_lock:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")


# --------------------------------------------------------------------------- #
# The consumer (the behavior under test)
# --------------------------------------------------------------------------- #
class Consumer(threading.Thread):
    """Drains every topic queue. Applies state transitions for well-formed events;
    DLQ-routes + ERROR-logs malformed events WITHOUT crashing."""

    daemon = True

    def __init__(self, topics: dict):
        super().__init__(name="eventbus-consumer")
        self._topics = topics
        self._stop = threading.Event()
        self.alive = True  # flips False only if the loop itself dies (it must not)

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self._drain_once()
            except Exception as e:  # noqa  -- the loop itself must never die
                # A failure here would be a real bug: log it but keep the consumer alive.
                log_line("ERROR", "_consumer_", None,
                         f"consumer loop error (recovered): {type(e).__name__}: {e}")
            time.sleep(CONSUMER_POLL_SECONDS)

    def _drain_once(self):
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT offset, topic, message_id, payload FROM topic_queue "
                "WHERE status = 'pending' ORDER BY offset ASC LIMIT 50"
            ).fetchall()
        finally:
            conn.close()
        for offset, topic, message_id, payload in rows:
            self._process_one(offset, topic, message_id, payload)

    def _process_one(self, offset: int, topic: str, message_id: str, payload: str):
        # Per-message try/except: a single malformed message can NEVER take the
        # consumer down. This is exactly the robustness the task asserts.
        try:
            contract = self._topics.get(topic)
            if contract is None:
                raise ValueError(f"unknown topic '{topic}'")
            event = json.loads(payload)
            missing = [f for f in contract["required_fields"]
                       if f not in event or event.get(f) in (None, "")]
            if missing:
                raise ValueError(f"schema validation failed: missing required field(s) "
                                 f"{missing} for topic '{topic}'")
            # Well-formed: apply the documented state transition.
            self._apply_transition(contract, event)
            self._mark(offset, "done")
            log_line("INFO", topic, message_id,
                     f"processed event; {contract['resource']}/{event.get('resource_id')}"
                     f" -> {contract['state_field']}={contract['expected_state']}")
        except Exception as e:  # noqa  -- malformed / unprocessable => DLQ, never crash
            self._to_dlq(offset, topic, message_id, payload, f"{type(e).__name__}: {e}")
            self._mark(offset, "dlq")
            log_line("ERROR", topic, message_id,
                     f"parse/validation error for message_id={message_id} offset={offset}: {e}")

    def _apply_transition(self, contract: dict, event: dict):
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO resources (resource, resource_id, state_field, state) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(resource, resource_id) DO UPDATE SET "
                "  state = excluded.state, state_field = excluded.state_field, "
                "  updated_at = datetime('now')",
                (contract["resource"], str(event.get("resource_id")),
                 contract["state_field"], contract["expected_state"]),
            )
            conn.commit()
        finally:
            conn.close()

    def _to_dlq(self, offset, topic, message_id, payload, reason):
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO dlq (topic, message_id, offset, payload, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (topic, message_id, offset, payload, reason),
            )
            conn.commit()
        finally:
            conn.close()

    def _mark(self, offset, status):
        conn = _connect()
        try:
            conn.execute("UPDATE topic_queue SET status = ? WHERE offset = ?", (status, offset))
            conn.commit()
        finally:
            conn.close()


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #
def _make_handler(topics: dict, consumer: Consumer):
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

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw or b"{}")
            except Exception:  # noqa
                return {}

        # ---- GET --------------------------------------------------------- #
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                self._send(200, {"ok": True, "consumer_alive": consumer.is_alive()})
                return
            if path == "/logs":
                since = float((parse_qs(parsed.query).get("since", ["0"]) or ["0"])[0])
                lines = []
                try:
                    for ln in LOG_PATH.read_text().splitlines():
                        try:
                            rec = json.loads(ln)
                        except Exception:  # noqa
                            continue
                        if rec.get("ts", 0) >= since:
                            lines.append(rec)
                except FileNotFoundError:
                    pass
                self._send(200, {"lines": lines})
                return
            if path == "/dlq":
                topic = (parse_qs(parsed.query).get("topic", [""]) or [""])[0]
                conn = _connect()
                try:
                    q = ("SELECT topic, message_id, offset, payload, reason, consumed "
                         "FROM dlq WHERE 1=1")
                    args: list = []
                    if topic:
                        q += " AND topic = ?"
                        args.append(topic)
                    rows = conn.execute(q + " ORDER BY id ASC", args).fetchall()
                finally:
                    conn.close()
                msgs = [{"topic": r[0], "message_id": r[1], "offset": r[2],
                         "payload": json.loads(r[3]) if r[3] else None,
                         "reason": r[4], "consumed": bool(r[5])} for r in rows]
                self._send(200, {"messages": msgs})
                return
            # GET /<resource>/<id>
            parts = [p for p in path.split("/") if p]
            if len(parts) == 2:
                resource, rid = parts[0], parts[1]
                conn = _connect()
                try:
                    row = conn.execute(
                        "SELECT resource, resource_id, state_field, state, updated_at "
                        "FROM resources WHERE resource = ? AND resource_id = ?",
                        (resource, rid)).fetchone()
                finally:
                    conn.close()
                if not row:
                    self._send(404, {"error": f"{resource}/{rid} not found"})
                    return
                self._send(200, {"resource": row[0], "resource_id": row[1],
                                 row[2]: row[3], "state_field": row[2],
                                 "updated_at": row[4]})
                return
            self._send(404, {"error": "not found"})

        # ---- POST -------------------------------------------------------- #
        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/publish":
                data = self._read_body()
                topic = data.get("topic")
                event = data.get("event")
                if not isinstance(topic, str) or not isinstance(event, (dict, list, str, int, float)):
                    self._send(400, {"error": "publish requires 'topic' (str) and 'event'"})
                    return
                message_id = (event.get("event_id") if isinstance(event, dict)
                              and event.get("event_id") else f"msg-{uuid.uuid4().hex[:12]}")
                conn = _connect()
                try:
                    cur = conn.execute(
                        "INSERT INTO topic_queue (topic, message_id, payload) VALUES (?, ?, ?)",
                        (topic, str(message_id), json.dumps(event)))
                    conn.commit()
                    offset = cur.lastrowid
                finally:
                    conn.close()
                self._send(202, {"message_id": str(message_id), "offset": offset, "topic": topic})
                return
            if path == "/admin/reset":
                data = self._read_body()
                resource = data.get("resource")
                rid = data.get("resource_id")
                state_field = data.get("state_field", "status")
                state = data.get("state")
                if not resource or rid is None:
                    self._send(400, {"error": "reset requires 'resource' and 'resource_id'"})
                    return
                conn = _connect()
                try:
                    conn.execute(
                        "INSERT INTO resources (resource, resource_id, state_field, state) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(resource, resource_id) DO UPDATE SET "
                        "  state = excluded.state, state_field = excluded.state_field, "
                        "  updated_at = datetime('now')",
                        (resource, str(rid), state_field, state))
                    conn.commit()
                finally:
                    conn.close()
                self._send(200, {"ok": True, "resource": resource, "resource_id": str(rid),
                                 "state_field": state_field, "state": state})
                return
            if path == "/dlq/consume":
                data = self._read_body()
                topic = data.get("topic")
                conn = _connect()
                try:
                    q = "SELECT id, topic, message_id, offset, payload, reason FROM dlq WHERE consumed = 0"
                    args: list = []
                    if topic:
                        q += " AND topic = ?"
                        args.append(topic)
                    row = conn.execute(q + " ORDER BY id ASC LIMIT 1", args).fetchone()
                    if row:
                        conn.execute("UPDATE dlq SET consumed = 1 WHERE id = ?", (row[0],))
                        conn.commit()
                finally:
                    conn.close()
                if not row:
                    self._send(200, {"message": None})
                    return
                self._send(200, {"message": {
                    "topic": row[1], "message_id": row[2], "offset": row[3],
                    "payload": json.loads(row[4]) if row[4] else None, "reason": row[5]}})
                return
            self._send(404, {"error": "not found"})

    return Handler


def main() -> int:
    init_db()
    topics = load_topics()
    consumer = Consumer(topics)
    consumer.start()
    httpd = ThreadingHTTPServer((HOST, PORT), _make_handler(topics, consumer))
    httpd.daemon_threads = True
    print(f"[eventbus-target] listening on http://{HOST}:{PORT}  db={DB_PATH}  "
          f"topics={list(topics)}", file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        consumer.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
