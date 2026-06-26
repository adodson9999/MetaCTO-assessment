"""Local webhook receiver for the webhook-delivery testing task.

Stdlib-only HTTP receiver that logs every inbound request (method, path, full
headers, and the raw request-body BYTES — raw bytes are required so the HMAC is
computed over exactly what was sent, never a re-serialized copy). It binds to
127.0.0.1 on an EPHEMERAL port so four agents can each run their own receiver in
parallel without colliding, and it stays air-gapped — nothing leaves the loopback
interface.

This replaces the task's "custom Express.js script behind an ngrok tunnel" with the
air-gapped equivalent for a LOCAL target: when the API under test is on localhost it
can reach a localhost receiver directly, so no public tunnel is needed (and a public
ngrok tunnel would violate the foundry's air-gapped invariant). The Express+ngrok
variant is documented in task_spec for the case of a remote SaaS target.

Retry support: the receiver can be told to answer the first K matching deliveries
with HTTP 500 (to exercise the producer's retry path) and 200 thereafter.
"""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Recorder:
    """Thread-safe in-memory log of inbound deliveries shared with the handler."""

    def __init__(self, fail_first: int = 0):
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._fail_remaining = fail_first  # respond 500 to this many deliveries first

    def record(self, method: str, path: str, headers: dict, body: bytes) -> int:
        """Append one delivery; return the HTTP status the receiver should answer."""
        with self._lock:
            status = 200
            if self._fail_remaining > 0:
                status = 500
                self._fail_remaining -= 1
            self._events.append({
                "method": method,
                "path": path,
                "headers": {k: v for k, v in headers.items()},
                "raw_body": body,                       # exact bytes as received
                "recv_monotonic": time.monotonic(),
                "responded_status": status,
            })
            return status

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._events)


def _make_handler(recorder: _Recorder):
    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            status = recorder.record(self.command, self.path, self.headers, body)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"received":true}' if status == 200 else b'{"error":true}')

        # webhooks are POSTs, but accept any verb so nothing is silently dropped
        do_POST = _handle
        do_PUT = _handle
        do_GET = _handle

        def log_message(self, *args):  # silence default stderr logging
            return

    return Handler


class WebhookReceiver:
    """Context-managed local receiver. `url` is the public-to-the-target base URL
    (loopback) to register with the API."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, path: str = "/hook",
                 fail_first: int = 0):
        self.host = host
        self.path = path
        self.recorder = _Recorder(fail_first=fail_first)
        self._server = ThreadingHTTPServer((host, port), _make_handler(self.recorder))
        self.port = self._server.server_address[1]   # resolved ephemeral port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{self.path}"

    def start(self) -> "WebhookReceiver":
        self._thread.start()
        return self

    def events(self) -> list[dict]:
        return self.recorder.snapshot()

    def stop(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:  # noqa
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
