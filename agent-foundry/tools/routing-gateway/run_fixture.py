#!/usr/bin/env python3
"""Launcher for the local API-gateway-routing fixture.

Starts, in one process, the gateway plus one WireMock-equivalent mock backend per
downstream service (each on its own loopback port, each with its own request journal).
Owns a FixtureController the gateway uses to stop/restart a backend on demand — the
control-plane stand-in for stopping a WireMock instance during the service-down test.

All servers bind 127.0.0.1 (air-gapped). Run this once; the gold builder and the four
agents then drive the gateway over HTTP and read each backend's /__admin/requests.

Usage:
    python run_fixture.py [--host 127.0.0.1] [--gateway-port 8920]
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_config  # noqa: E402
import mock_backend  # noqa: E402
import gateway as gw  # noqa: E402


class FixtureController:
    """Owns the live backend servers and can stop/restart any of them by name.

    'down' really stops the server (closes its listening socket) so the gateway gets a
    genuine connection refusal and must answer 503 — the faithful service-down signal.
    """

    def __init__(self, host: str) -> None:
        self.host = host
        self._servers: dict[str, object] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def _start(self, name: str) -> None:
        port = fixture_config.backend_port(name)
        srv = mock_backend.build_server(name, self.host, port)
        t = threading.Thread(target=srv.serve_forever, name=f"backend-{name}", daemon=True)
        t.start()
        self._servers[name] = srv
        self._threads[name] = t

    def start_all(self) -> None:
        with self._lock:
            for name in fixture_config.service_names():
                if name not in self._servers:
                    self._start(name)

    def down(self, name: str) -> None:
        with self._lock:
            srv = self._servers.pop(name, None)
            if srv is not None:
                srv.shutdown()
                srv.server_close()
                self._threads.pop(name, None)

    def up(self, name: str) -> None:
        with self._lock:
            if name not in self._servers:
                # brief pause so the previous socket fully releases before rebind
                time.sleep(0.05)
                self._start(name)

    def stop_all(self) -> None:
        with self._lock:
            for name, srv in list(self._servers.items()):
                try:
                    srv.shutdown()
                    srv.server_close()
                except Exception:  # noqa
                    pass
            self._servers.clear()
            self._threads.clear()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--gateway-port", type=int, default=fixture_config.GATEWAY_PORT)
    a = ap.parse_args()

    controller = FixtureController(a.host)
    controller.start_all()

    server = gw.build_gateway(a.host, a.gateway_port, controller=controller)
    ports = {n: fixture_config.backend_port(n) for n in fixture_config.service_names()}
    print(f"routing-gateway up on http://{a.host}:{a.gateway_port}  "
          f"backends={ports}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
