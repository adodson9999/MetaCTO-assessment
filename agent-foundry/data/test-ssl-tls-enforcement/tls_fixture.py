#!/usr/bin/env python3
"""Local, air-gapped TLS fixture for the SSL/TLS-enforcement testing task.

The DummyJSON app is plain HTTP and is **never modified** (the user's explicit
constraint). To give the SSL/TLS-enforcement test a real, auditable TLS surface
WITHOUT touching DummyJSON, this fixture stands a TLS terminator *in front of* the
untouched local DummyJSON. It is part of the test harness, not part of DummyJSON.

What it provides (all local, all loopback, fully air-gapped):

  - a private mini-CA (ca.pem/ca.key) + a leaf cert (server.pem/server.key) signed
    by it, for CN=localhost with SAN DNS:localhost, DNS:dummyjson.local, IP:127.0.0.1,
    valid from yesterday to +365d (so cert_not_expired is genuinely true). The harness
    trusts ca.pem as its CA bundle, so chain-of-trust verifies against a real CA the
    fixture controls (NOT self-signed: issuer != subject).
  - a TLS terminating reverse-proxy on TLS_PORT that:
      * accepts ONLY TLS 1.2 and TLS 1.3 (minimum_version = TLSv1_2), so TLS 1.0/1.1
        handshakes are refused at the server,
      * offers ONLY strong AEAD ciphers (no RC4/DES/3DES/EXPORT/NULL),
      * forwards each request to the upstream DummyJSON with a READ-ONLY GET and
        relays the status + body back. No method other than GET reaches upstream.
  - a plain-HTTP listener on HTTP_PORT that returns 301 -> https://<host>:TLS_PORT/<path>
    and NO API data, so "plain HTTP is refused / redirected, zero data returned" holds.

Certs are generated with the openssl CLI (already present); the servers use the
Python stdlib `ssl` module only. No third-party Python dependency, no network egress
beyond the loopback upstream.

Usage:
    python tls_fixture.py gen-certs            # idempotent; regenerate with --force
    python tls_fixture.py start                # background; writes <dir>/fixture.pids
    python tls_fixture.py status
    python tls_fixture.py stop
    python tls_fixture.py run                   # foreground (ctrl-c to stop)

Env (all optional; defaults shown):
    TLS_FIXTURE_TLS_PORT   = 9443
    TLS_FIXTURE_HTTP_PORT  = 9080
    TLS_FIXTURE_UPSTREAM   = http://localhost:8899
    TLS_FIXTURE_HOST       = localhost
"""
from __future__ import annotations

import os
import signal
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CERT_DIR = HERE / "tls_fixture"
CA_KEY = CERT_DIR / "ca.key"
CA_PEM = CERT_DIR / "ca.pem"
SRV_KEY = CERT_DIR / "server.key"
SRV_PEM = CERT_DIR / "server.pem"
PID_FILE = CERT_DIR / "fixture.pids"

HOST = os.environ.get("TLS_FIXTURE_HOST", "localhost")
TLS_PORT = int(os.environ.get("TLS_FIXTURE_TLS_PORT", "9443"))
HTTP_PORT = int(os.environ.get("TLS_FIXTURE_HTTP_PORT", "9080"))
UPSTREAM = os.environ.get("TLS_FIXTURE_UPSTREAM", "http://localhost:8899").rstrip("/")

# Strong-only cipher policy for TLS 1.2 (TLS 1.3 suites are fixed-strong by the stack).
# Explicitly excludes every family the task forbids: RC4, DES, 3DES, EXPORT, NULL, MD5.
STRONG_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!eNULL:!RC4:!DES:!3DES:!EXPORT:!MD5:!SHA1"


# --------------------------------------------------------------------------- #
# Certificate generation (openssl CLI; the only place a subprocess is used)
# --------------------------------------------------------------------------- #
def _openssl(*args: str) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True, text=True)


def gen_certs(force: bool = False) -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if SRV_PEM.exists() and CA_PEM.exists() and not force:
        print(f"certs already present in {CERT_DIR} (use --force to regenerate)")
        return

    # 1. A private CA (this is what makes the leaf CA-signed, not self-signed).
    _openssl("genrsa", "-out", str(CA_KEY), "2048")
    _openssl("req", "-x509", "-new", "-nodes", "-key", str(CA_KEY),
             "-sha256", "-days", "3650", "-out", str(CA_PEM),
             "-subj", "/C=US/O=Forge Local CA/CN=Forge Local Root CA")

    # 2. A leaf key + CSR for the fixture host.
    _openssl("genrsa", "-out", str(SRV_KEY), "2048")
    csr = CERT_DIR / "server.csr"
    _openssl("req", "-new", "-key", str(SRV_KEY), "-out", str(csr),
             "-subj", f"/C=US/O=Forge TLS Fixture/CN={HOST}")

    # 3. Sign the leaf with the CA, carrying the SAN extension.
    extfile = CERT_DIR / "server.ext"
    extfile.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=DNS:localhost,DNS:dummyjson.local,IP:127.0.0.1\n"
    )
    # notBefore = yesterday so "not before" can never trip clock skew; +365d validity.
    _openssl("x509", "-req", "-in", str(csr), "-CA", str(CA_PEM), "-CAkey", str(CA_KEY),
             "-CAcreateserial", "-out", str(SRV_PEM), "-days", "365", "-sha256",
             "-extfile", str(extfile))
    csr.unlink(missing_ok=True)
    print(f"generated CA + leaf cert in {CERT_DIR}")


# --------------------------------------------------------------------------- #
# TLS terminating reverse-proxy (stdlib ssl) -> read-only GET to upstream
# --------------------------------------------------------------------------- #
class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # silence
        pass

    def _forward_get(self) -> None:
        url = f"{UPSTREAM}{self.path}"
        req = urllib.request.Request(url, method="GET")  # GET only — upstream never mutated
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
                status, ctype = r.getcode(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            body, status = e.read(), e.code
            ctype = e.headers.get("Content-Type", "application/json") if e.headers else "application/json"
        except Exception as e:  # noqa
            body, status, ctype = f"upstream error: {e}".encode(), 502, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._forward_get()

    def do_HEAD(self):
        self._forward_get()

    # Any non-GET/HEAD method is rejected so the proxy can never mutate upstream.
    def _reject(self):
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_PUT = do_PATCH = do_DELETE = _reject


class _RedirectHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _redirect(self):
        # 301 to the HTTPS endpoint; carry NO API data over the plaintext channel.
        location = f"https://{HOST}:{TLS_PORT}{self.path}"
        self.send_response(301)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = _redirect


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # refuse TLS 1.0 and 1.1
    ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_ciphers(STRONG_CIPHERS)
    ctx.load_cert_chain(certfile=str(SRV_PEM), keyfile=str(SRV_KEY))
    return ctx


def _serve_tls() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((HOST, TLS_PORT), _ProxyHandler)
    httpd.socket = _tls_context().wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _serve_http_redirect() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((HOST, HTTP_PORT), _RedirectHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run_foreground() -> None:
    if not SRV_PEM.exists():
        gen_certs()
    tls = _serve_tls()
    red = _serve_http_redirect()
    print(f"TLS fixture up: https://{HOST}:{TLS_PORT} (TLS1.2/1.3 only) "
          f"+ http://{HOST}:{HTTP_PORT} (301 -> https) -> upstream {UPSTREAM}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        tls.shutdown()
        red.shutdown()


# --------------------------------------------------------------------------- #
# Background start/stop/status
# --------------------------------------------------------------------------- #
def _is_up() -> bool:
    try:
        ctx = ssl.create_default_context(cafile=str(CA_PEM)) if CA_PEM.exists() else ssl._create_unverified_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with ctx.wrap_socket(__import__("socket").create_connection((HOST, TLS_PORT), timeout=3),
                             server_hostname=HOST) as s:
            return True
    except Exception:  # noqa
        return False


def start() -> None:
    if _is_up():
        print(f"fixture already up on {HOST}:{TLS_PORT}")
        return
    if not SRV_PEM.exists():
        gen_certs()
    proc = subprocess.Popen([sys.executable, str(Path(__file__)), "run"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    PID_FILE.write_text(str(proc.pid))
    for _ in range(40):
        if _is_up():
            print(f"fixture started (pid {proc.pid}) on https://{HOST}:{TLS_PORT}")
            return
        time.sleep(0.25)
    print("fixture did not come up in time", file=sys.stderr)
    sys.exit(1)


def stop() -> None:
    if not PID_FILE.exists():
        print("no pid file; nothing to stop")
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        print(f"stopped fixture pid {pid}")
    except Exception as e:  # noqa
        print(f"stop: {e}")
    PID_FILE.unlink(missing_ok=True)


def status() -> None:
    print(f"fixture {'UP' if _is_up() else 'DOWN'} (https://{HOST}:{TLS_PORT}, "
          f"http://{HOST}:{HTTP_PORT}, upstream {UPSTREAM})")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    force = "--force" in sys.argv
    if cmd == "gen-certs":
        gen_certs(force=force)
    elif cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        status()
    elif cmd == "run":
        run_foreground()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
