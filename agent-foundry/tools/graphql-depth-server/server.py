#!/usr/bin/env python3
"""Local GraphQL depth-limit SUT — the air-gapped stand-in for a depth-limited
GraphQL API.

Exposes two POST /graphql-style endpoints, each enforcing a documented maximum
query depth (the count of nested field selection sets):

    POST /graphql          max_depth = 7   (primary)
    POST /graphql-strict   max_depth = 4   (held-out set for the staged evolution gate)

The contract enforced (the documented depth-limit behavior under test):
  - depth <= max_depth  -> 200 with a non-null "data" object and NO "errors" key.
  - depth >  max_depth  -> 400 with an "errors" array (>=1 element) whose first
                           message mentions both "depth" and "complexity", and NO
                           non-null "data". The depth check runs BEFORE any
                           resolution, so a too-deep query is rejected in O(len)
                           time — a deep (e.g. depth-15) query returns far inside
                           one second, never triggering expensive work (the DoS the
                           limit exists to prevent).
  - a malformed / unparseable / empty query -> 400 with an "errors" array.

Depth is computed from selection-set ({ }) nesting, ignoring braces inside string
literals; the operation's outermost selection set is level 1, so
`query { node { child { name } } }` has depth 3 — exactly the count of nested field
selection sets (NOT character or token count).

The recursive schema the queries exercise: a `node` field returns a Node; Node has a
scalar `name` and a recursive `child: Node`, so a query can nest to any depth.

Stdlib only. Binds 127.0.0.1 (air-gapped). Read-only: a GraphQL query never mutates
server state, and there are NO mutation resolvers, so the server is immutable for the
process life. DummyJSON is never used or modified by this task.

Usage:
    python server.py --host 127.0.0.1 --port 8940
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE = "graphql-depth-server"

# endpoint path -> documented maximum allowed query depth.
MAX_DEPTH_BY_PATH: dict[str, int] = {
    "/graphql": 7,
    "/graphql-strict": 4,
}


def query_depth(query: str) -> int:
    """Maximum nesting depth of field selection sets, counting the operation's
    outermost selection set as level 1. Braces inside string literals are ignored.
    O(len) — runs before any resolution so a too-deep query is rejected cheaply."""
    depth = 0
    max_depth = 0
    in_str = False
    esc = False
    quote = ""
    for ch in query:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch == "}":
            depth = max(0, depth - 1)
    return max_depth


def _balanced(query: str) -> bool:
    """True if selection-set braces are balanced (ignoring string literals)."""
    depth = 0
    in_str = False
    esc = False
    quote = ""
    for ch in query:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _resolve(depth: int) -> dict:
    """A representative non-null resolved payload for an accepted query. The contract
    only requires data to be non-null with no errors; the shape mirrors the recursive
    node->child->name chain the query walked."""
    node: dict = {"name": "leaf"}
    for _ in range(max(0, depth - 2)):
        node = {"name": "branch", "child": node}
    return {"queryDepth": depth, "node": {"name": "root", "child": node} if depth >= 2 else {"name": "root"}}


def handle_query(path: str, query) -> tuple[int, dict]:
    """Apply the documented depth-limit contract. Returns (status_code, body)."""
    max_depth = MAX_DEPTH_BY_PATH[path]
    if not isinstance(query, str) or not query.strip():
        return 400, {"errors": [{"message": "Request must carry a non-empty GraphQL "
                                            "'query' string.",
                                 "extensions": {"code": "BAD_REQUEST"}}]}
    if not _balanced(query):
        return 400, {"errors": [{"message": "Malformed GraphQL query: unbalanced "
                                            "selection-set braces.",
                                 "extensions": {"code": "GRAPHQL_PARSE_FAILED"}}]}

    depth = query_depth(query)

    # Depth check FIRST — before any resolution — so too-deep queries are cheap to reject.
    if depth > max_depth:
        return 400, {"errors": [{
            "message": (f"Query depth {depth} exceeds the maximum allowed depth of "
                        f"{max_depth}; the query was rejected for excessive complexity."),
            "extensions": {"code": "DEPTH_LIMIT_EXCEEDED",
                           "depth": depth, "maxDepth": max_depth}}]}

    # Accepted: non-null data, no errors key.
    return 200, {"data": _resolve(depth)}


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
        path = urllib.parse.urlparse(self.path).path
        if path in ("/__health", "/health", "/test"):
            self._send_json(200, {"status": "ok", "service": SERVICE,
                                  "endpoints": MAX_DEPTH_BY_PATH})
            return
        self._send_json(405, {"errors": [{"message": "Use POST with a JSON "
                                                    "{\"query\": ...} body."}]})

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path not in MAX_DEPTH_BY_PATH:
            self._send_json(404, {"errors": [{"message": f"Unknown GraphQL endpoint '{path}'."}]})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            body = json.loads(raw or b"{}")
        except Exception:  # noqa
            self._send_json(400, {"errors": [{"message": "Request body is not valid JSON."}]})
            return
        query = body.get("query") if isinstance(body, dict) else None
        code, out = handle_query(path, query)
        self._send_json(code, out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8940)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"{SERVICE} listening on http://{a.host}:{a.port} "
          f"(endpoints={MAX_DEPTH_BY_PATH})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
