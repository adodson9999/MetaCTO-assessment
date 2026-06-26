"""Shared, deterministic plumbing for the four timeout-handling testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It
is the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the service catalogue from data/test-timeout-handling/timeout_spec.json
  - build the compact per-service brief handed to the agent
  - inject the upstream delay (Toxiproxy-style: a per-request X-Upstream-Delay-Ms
    header, plus the documented PUT/DELETE /__control/toxic lifecycle) ONLY at the
    one local gateway
  - execute whatever plan the agent emitted with a raw HTTP/1.1 socket client that
    measures wall-clock latency, parses the status, and verifies whether the server
    closed the TCP connection (the netstat-equivalent check, done deterministically)
  - evaluate every scenario (shared timeout_spec.evaluate_*), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The gateway is the air-gapped local stand-in for a WireMock upstream stub fronted by
a Toxiproxy latency toxic; the framework-specific part — turning one service's brief
into the timeout plan via the model — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8911").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-timeout-handling" / "timeout_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import timeout_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _host_port() -> tuple[str, int]:
    u = urllib.parse.urlparse(TARGET_BASE_URL)
    host = u.hostname or "127.0.0.1"
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")
    return host, (u.port or 80)


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def service_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for s in spec["services"]:
        out.append({
            "service": s["service"],
            "upstream_timeout_s": s["upstream_timeout_s"],
            "buffer_s": s["buffer_s"],
            "restore_max_ms": s["restore_max_ms"],
            "endpoints": [{"method": e["method"], "path": e["path"]} for e in s["endpoints"]],
        })
    only = os.environ.get("FORGE_ONLY_SERVICES", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [c for c in out if c["service"] in wanted]
    return out


def service_brief(cfg: dict) -> str:
    """Compact, unambiguous timeout contract handed to the model."""
    lines = [
        f"service: {cfg['service']}",
        f"upstream_timeout_s: {cfg['upstream_timeout_s']}   # documented upstream timeout, whole seconds",
        f"buffer_s: {cfg['buffer_s']}                       # fixed grace allowance, whole seconds",
        f"restore_max_ms: {cfg['restore_max_ms']}           # post-recovery latency budget, whole ms",
        "endpoints (each calls the upstream service):",
    ]
    for e in cfg["endpoints"]:
        lines.append(f"  - {e['method'].upper()} {e['path']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Toxiproxy-style control lifecycle (documented flow; behavior driven per-request)
# --------------------------------------------------------------------------- #
def _control(method: str, latency_ms: int | None = None) -> bool:
    host, port = _host_port()
    url = f"http://{host}:{port}/__control/toxic"
    data = json.dumps({"latency_ms": latency_ms}).encode() if latency_ms is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.getcode() == 200
    except Exception:  # noqa  -- control plane is best-effort; per-request header drives behavior
        return False


def inject_toxic(latency_ms: int) -> bool:
    return _control("PUT", latency_ms)


def remove_toxic() -> bool:
    return _control("DELETE")


# --------------------------------------------------------------------------- #
# Raw HTTP/1.1 socket client — measures latency + verifies TCP closure
# --------------------------------------------------------------------------- #
def _recv_until(sock: socket.socket, marker: bytes, cap: int = 65536) -> bytes:
    buf = b""
    while marker not in buf and len(buf) < cap:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def http_probe(method: str, path: str, *, delay_ms: int | None, read_timeout_s: float) -> dict:
    """One raw HTTP/1.1 request. Returns:
        {status:int|None, elapsed_s:float, elapsed_ms:float, conn_closed:bool|None,
         server_connection:str|None, body:dict|None}
    status is None on a client-side timeout (a hang — the failure mode the test guards
    against). conn_closed is determined by an actual post-response recv: EOF => the
    server closed the socket; a short keep-alive wait => still open.
    """
    host, port = _host_port()
    headers = [f"Host: {host}:{port}"]
    if delay_ms is not None:
        headers.append(f"X-Upstream-Delay-Ms: {int(delay_ms)}")
    # Client does NOT force-close: we observe the server's own connection behavior.
    request = (f"{method.upper()} {path} HTTP/1.1\r\n" + "\r\n".join(headers) + "\r\n\r\n").encode()

    t0 = time.monotonic()
    status = None
    server_connection = None
    conn_closed = None
    body = None
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=read_timeout_s)
        sock.settimeout(read_timeout_s)
        sock.sendall(request)
        head = _recv_until(sock, b"\r\n\r\n")
        if not head:
            return {"status": None, "elapsed_s": time.monotonic() - t0,
                    "elapsed_ms": (time.monotonic() - t0) * 1000.0,
                    "conn_closed": True, "server_connection": None, "body": None}
        header_blob, _, rest = head.partition(b"\r\n\r\n")
        lines = header_blob.split(b"\r\n")
        try:
            status = int(lines[0].split(b" ")[1])
        except Exception:  # noqa
            status = None
        content_length = 0
        for h in lines[1:]:
            k, _, v = h.partition(b":")
            key = k.strip().lower()
            val = v.strip()
            if key == b"content-length":
                try:
                    content_length = int(val)
                except ValueError:
                    content_length = 0
            elif key == b"connection":
                server_connection = val.decode(errors="replace").lower()
        # read remaining body bytes
        body_bytes = rest
        while len(body_bytes) < content_length:
            chunk = sock.recv(min(4096, content_length - len(body_bytes)))
            if not chunk:
                break
            body_bytes += chunk
        elapsed = time.monotonic() - t0
        try:
            body = json.loads(body_bytes[:content_length] or b"null")
        except Exception:  # noqa
            body = None
        # Closure probe: did the server actually close the TCP connection?
        try:
            sock.settimeout(1.0)
            tail = sock.recv(1)
            conn_closed = (tail == b"")          # EOF => server closed
        except socket.timeout:
            conn_closed = False                  # still open => keep-alive (the defect)
        except Exception:  # noqa
            conn_closed = True
        return {"status": status, "elapsed_s": elapsed, "elapsed_ms": elapsed * 1000.0,
                "conn_closed": conn_closed, "server_connection": server_connection, "body": body}
    except (socket.timeout, TimeoutError):
        # No response within read_timeout: a hang (open connection that never answered).
        elapsed = time.monotonic() - t0
        return {"status": None, "elapsed_s": elapsed, "elapsed_ms": elapsed * 1000.0,
                "conn_closed": False, "server_connection": None, "body": None}
    except Exception:  # noqa
        elapsed = time.monotonic() - t0
        return {"status": None, "elapsed_s": elapsed, "elapsed_ms": elapsed * 1000.0,
                "conn_closed": None, "server_connection": None, "body": None}
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa
                pass


def _delayed_observation(probe: dict) -> dict:
    mn, nl = timeout_spec.body_is_safe(probe.get("body"))
    return {"status": probe.get("status"), "elapsed_s": probe.get("elapsed_s"),
            "conn_closed": probe.get("conn_closed"),
            "message_nonempty": mn, "no_leak": nl}


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            data = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=data,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_timeout_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the timeout plan object for one service: a dict with
        max_wait_s and `delayed`/`restore` arrays (each {label, method, path}). The
        harness injects the upstream delay, executes the AGENT's planned probes,
        verifies status/latency/closure, removes the delay, re-probes for recovery,
        and evaluates every scenario. Whatever the agent omits scores as 'missing'.
    """
    cfgs = service_cfgs()
    injected = int(load_spec().get("injected_delay_s", 60)) * 1000
    documented_max_wait = {c["service"]: c["upstream_timeout_s"] + c["buffer_s"] for c in cfgs}

    # 1) elicit a plan per service (the framework-specific step)
    plans, gen_errors = {}, {}
    for cfg in cfgs:
        try:
            plans[cfg["service"]] = generate(cfg) or {}
        except Exception as e:  # noqa
            plans[cfg["service"]] = {}
            gen_errors[cfg["service"]] = f"{type(e).__name__}: {e}"

    delayed_obs, restore_obs, reqlog = {}, {}, []

    # 2) inject the toxic (documented Toxiproxy lifecycle) and run the delayed phase
    inject_toxic(injected)
    for cfg in cfgs:
        svc = cfg["service"]
        rt = documented_max_wait[svc] + 5.0   # client cap = curl --max-time, a touch over max_wait
        for probe in plans[svc].get("delayed", []) if isinstance(plans[svc], dict) else []:
            if not isinstance(probe, dict) or "path" not in probe:
                continue
            method = str(probe.get("method", "GET"))
            p = http_probe(method, probe["path"], delay_ms=injected, read_timeout_s=rt)
            delayed_obs[(svc, probe["path"])] = _delayed_observation(p)
            reqlog.append({"phase": "delayed", "service": svc, "label": probe.get("label"),
                           "method": method, "path": probe["path"], "status": p.get("status"),
                           "elapsed_s": round(p.get("elapsed_s", 0.0), 3),
                           "conn_closed": p.get("conn_closed"),
                           "server_connection": p.get("server_connection")})

    # 3) remove the toxic and run the restore phase
    remove_toxic()
    for cfg in cfgs:
        svc = cfg["service"]
        for probe in plans[svc].get("restore", []) if isinstance(plans[svc], dict) else []:
            if not isinstance(probe, dict) or "path" not in probe:
                continue
            method = str(probe.get("method", "GET"))
            p = http_probe(method, probe["path"], delay_ms=0, read_timeout_s=5.0)
            restore_obs[(svc, probe["path"])] = {"status": p.get("status"),
                                                 "elapsed_ms": p.get("elapsed_ms")}
            reqlog.append({"phase": "restore", "service": svc, "label": probe.get("label"),
                           "method": method, "path": probe["path"], "status": p.get("status"),
                           "elapsed_ms": round(p.get("elapsed_ms", 0.0), 1)})

    # 4) evaluate every scenario against the shared scheme
    all_cases = []
    endpoints_total = endpoints_enforced = 0
    scenarios_total = scenarios_correct = 0
    for cfg in cfgs:
        svc = cfg["service"]
        plan = plans[svc] if isinstance(plans[svc], dict) else {}
        agent_max_wait = plan.get("max_wait_s")
        scenarios = []

        svc_obs = timeout_spec.evaluate_service(plan, cfg)
        for label in timeout_spec.SERVICE_SCENARIO_LABELS:
            tok = svc_obs.get(label, "missing")
            ok = timeout_spec.correct(label, tok)
            scenarios.append({"service": svc, "scenario": label,
                              "ideal": timeout_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            scenarios_total += 1
            scenarios_correct += 1 if ok else 0

        for ep in cfg["endpoints"]:
            d = delayed_obs.get((svc, ep["path"]))
            r = restore_obs.get((svc, ep["path"]))
            ep_eval = timeout_spec.evaluate_endpoint(d, r, agent_max_wait, cfg["restore_max_ms"])
            for label in timeout_spec.ENDPOINT_SCENARIO_LABELS:
                tok = ep_eval.get(label, "missing")
                ok = timeout_spec.correct(label, tok)
                scenarios.append({"service": svc, "scenario": f"{ep['path']}::{label}",
                                  "ideal": timeout_spec.IDEAL[label], "observed_token": tok,
                                  "api_correct": ok})
                scenarios_total += 1
                scenarios_correct += 1 if ok else 0
            endpoints_total += 1
            if timeout_spec.enforcement_pass(ep_eval):
                endpoints_enforced += 1

        all_cases.append({"service": svc, "max_wait_emitted": agent_max_wait,
                          "emitted_plan": plan, "scenarios": scenarios,
                          "error": gen_errors.get(svc)})

    enforcement_rate = round(100.0 * endpoints_enforced / endpoints_total, 2) if endpoints_total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "timeout_enforcement_rate_pct": enforcement_rate,
           "endpoints_total": endpoints_total, "endpoints_enforced": endpoints_enforced,
           "scenarios_total": scenarios_total, "scenarios_api_correct": scenarios_correct,
           "request_log": reqlog, "services": all_cases}

    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, enforcement_rate, str(cases_path), extra={
        "timeout_enforcement_rate_pct": enforcement_rate,
        "endpoints_total": endpoints_total, "endpoints_enforced": endpoints_enforced})

    everos_note(agent, f"timeout-handling run: enforcement_rate={enforcement_rate}% "
                       f"over {len(cfgs)} services ({endpoints_enforced}/{endpoints_total} endpoints enforced)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Timeout Enforcement Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-timeout-handling" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "timeout_enforcement_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary model text."""
    import re
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except Exception:  # noqa
        return None
