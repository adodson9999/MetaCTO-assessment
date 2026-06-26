#!/usr/bin/env python3
"""Local IP-allowlist gateway fixture — the air-gapped stand-in for an AWS-WAF IP-set
(or an nginx `allow/deny` block) fronting a set of restricted resource endpoints.

Why this exists: DummyJSON ships no IP allowlist and must never be modified, and all
loopback test traffic shares peer 127.0.0.1, so there is no way to exercise distinct
source IPs against it. This gateway models the real control instead, deterministically
and without root:

  Trust model (mirrors an app sitting behind a WAF / reverse proxy):
    - `X-Edge-Verified-IP`  — the client's TRUE source IP as verified by the edge/WAF
       after inspecting the real TCP connection. This is the TRUSTED channel; the test
       harness acts as the edge and sets it to the client's real outbound IP
       (ALLOW_IP or BLOCK_IP). A real client cannot forge it because the edge overwrites
       it. When absent, the gateway falls back to the real TCP peer address.
    - `X-Forwarded-For`     — a client-supplied, UNTRUSTED hop list. A COMPLIANT endpoint
       must IGNORE it for allowlist decisions; honoring it is the classic IP-allowlist
       bypass (OWASP "IP allowlist bypass via X-Forwarded-For").
    - `X-Waf-Scope`         — selects which IP set this request is evaluated against
       (models distinct AWS-WAF IP-set ARNs). Lets parallel agents keep isolated
       allowlist state on one shared gateway.

  Endpoints under /restricted/<name>:
    - COMPLIANT endpoints (orders, invoices, audit-log, billing) enforce the allowlist
      on the edge-verified IP ONLY and never consult X-Forwarded-For -> a spoofed XFF is
      correctly rejected with 403.
    - DELIBERATELY-VULNERABLE endpoints (legacy-reports, partner-feed) prefer
      X-Forwarded-For when present -> an XFF-spoofing non-allowlisted client is wrongly
      let through with 200. These are seeded defects so the test suite has a real,
      critical bypass to CATCH (mirrors timeout-gateway's one-non-compliant endpoint).

  Allowed -> 200 + resource data. Blocked -> 403 + {"message":"Forbidden"} and NO
  resource data (so the test's body-leak assertion has a clean negative).

  Management plane (models the AWS-WAF CLI / nginx management API):
    - POST   /__waf/reset      {"scope": s, "ips": [...]}  set the IP set for a scope
    - PUT    /__waf/allowlist  {"scope": s, "ip": "..."}   add one IP to the set
    - DELETE /__waf/allowlist  {"scope": s, "ip": "..."}   remove one IP from the set
    - GET    /__waf/allowlist?scope=s                      read the current set
    - GET    /__health

Stdlib only. Binds 127.0.0.1 (air-gapped). Reads never mutate resource data; only the
management plane mutates allowlist state, and only for the named scope.

Usage:
    python gateway.py --host 127.0.0.1 --port 8913
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Resource catalogue. COMPLIANT enforce on the edge-verified IP only; VULNERABLE
# prefer the spoofable X-Forwarded-For when present (the seeded bypass defect).
COMPLIANT_RESOURCES = ("orders", "invoices", "audit-log", "billing")
VULNERABLE_RESOURCES = ("legacy-reports", "partner-feed")
ALL_RESOURCES = COMPLIANT_RESOURCES + VULNERABLE_RESOURCES

EDGE_IP_HEADER = "X-Edge-Verified-IP"
XFF_HEADER = "X-Forwarded-For"
SCOPE_HEADER = "X-Waf-Scope"


def _resource_data(name: str) -> dict:
    """The protected payload returned ONLY on an allowed (200) request. Its presence is
    what the test's data-exposure assertion keys on; a 403 must never contain it."""
    return {
        "resource": name,
        "records": [
            {"id": 1, "name": f"{name}-record-1", "secret": f"{name}-confidential-A"},
            {"id": 2, "name": f"{name}-record-2", "secret": f"{name}-confidential-B"},
        ],
        "count": 2,
    }


class _AllowlistStore:
    """Per-scope IP sets (the WAF IP-sets). Scope isolation lets parallel agents run
    independent add/remove sequences against one gateway without clobbering each other."""

    def __init__(self) -> None:
        self._sets: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def reset(self, scope: str, ips: list[str]) -> list[str]:
        with self._lock:
            self._sets[scope] = {str(ip) for ip in (ips or []) if ip}
            return sorted(self._sets[scope])

    def add(self, scope: str, ip: str) -> list[str]:
        with self._lock:
            self._sets.setdefault(scope, set()).add(str(ip))
            return sorted(self._sets[scope])

    def remove(self, scope: str, ip: str) -> list[str]:
        with self._lock:
            self._sets.setdefault(scope, set()).discard(str(ip))
            return sorted(self._sets[scope])

    def contains(self, scope: str, ip: str) -> bool:
        with self._lock:
            return ip in self._sets.get(scope, set())

    def get(self, scope: str) -> list[str]:
        with self._lock:
            return sorted(self._sets.get(scope, set()))


STORE = _AllowlistStore()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa  -- keep test output clean
        return

    # --- helpers ---------------------------------------------------------------
    def _send_json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa
            return {}

    def _scope(self) -> str:
        return self.headers.get(SCOPE_HEADER) or "default"

    def _edge_verified_ip(self) -> str:
        """The TRUSTED source IP: the edge/WAF-verified value, else the real TCP peer."""
        hdr = self.headers.get(EDGE_IP_HEADER)
        if hdr:
            return hdr.strip()
        return self.client_address[0]

    # --- management plane ------------------------------------------------------
    def do_POST(self) -> None:
        if urlparse(self.path).path == "/__waf/reset":
            body = self._read_body()
            ips = STORE.reset(str(body.get("scope") or "default"), body.get("ips") or [])
            self._send_json(200, {"scope": body.get("scope") or "default", "allowlist": ips})
            return
        self._send_json(404, {"message": "not found"})

    def do_PUT(self) -> None:
        if urlparse(self.path).path == "/__waf/allowlist":
            body = self._read_body()
            scope, ip = str(body.get("scope") or "default"), body.get("ip")
            if not ip:
                self._send_json(400, {"message": "ip required"})
                return
            self._send_json(200, {"scope": scope, "allowlist": STORE.add(scope, ip)})
            return
        self._send_json(404, {"message": "not found"})

    def do_DELETE(self) -> None:
        if urlparse(self.path).path == "/__waf/allowlist":
            body = self._read_body()
            scope, ip = str(body.get("scope") or "default"), body.get("ip")
            if not ip:
                self._send_json(400, {"message": "ip required"})
                return
            self._send_json(200, {"scope": scope, "allowlist": STORE.remove(scope, ip)})
            return
        self._send_json(404, {"message": "not found"})

    # --- data plane ------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/__health", "/health"):
            self._send_json(200, {"status": "ok", "resources": list(ALL_RESOURCES)})
            return

        if path == "/__waf/allowlist":
            scope = (parse_qs(parsed.query).get("scope", ["default"]) or ["default"])[0]
            self._send_json(200, {"scope": scope, "allowlist": STORE.get(scope)})
            return

        if not path.startswith("/restricted/"):
            self._send_json(404, {"message": "unknown endpoint"})
            return

        name = path[len("/restricted/"):]
        if name not in ALL_RESOURCES:
            self._send_json(404, {"message": "unknown resource"})
            return

        scope = self._scope()
        verified_ip = self._edge_verified_ip()

        # The allowlist-decision IP. COMPLIANT: the trusted verified IP, XFF ignored.
        # VULNERABLE (seeded defect): prefer the client-supplied X-Forwarded-For when
        # present -> the spoofable header overrides the verified IP.
        if name in VULNERABLE_RESOURCES:
            xff = self.headers.get(XFF_HEADER)
            decision_ip = xff.split(",")[0].strip() if xff else verified_ip
        else:
            decision_ip = verified_ip

        if STORE.contains(scope, decision_ip):
            self._send_json(200, _resource_data(name))
        else:
            # 403 carries NO resource data — only a generic message.
            self._send_json(403, {"message": "Forbidden"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8913)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"ip-allowlist-gateway listening on http://{a.host}:{a.port} "
          f"(compliant={list(COMPLIANT_RESOURCES)} vulnerable={list(VULNERABLE_RESOURCES)})",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
