"""Shared, deterministic plumbing for the four long-polling testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the channel catalogue from data/test-long-polling-support/longpoll_spec.json
  - build the compact per-channel brief handed to the agent
  - execute whatever plan the agent emitted with a raw HTTP/1.1 socket client that
    measures wall-clock latency: a no-event long-poll (never triggered) and an event
    long-poll whose event is published ~1.5 s in by a BACKGROUND THREAD (the documented
    "requests stream=True + background trigger" pattern), recording T_POLL_START, T_EVENT,
    and the response timing
  - evaluate every scenario (shared longpoll_spec.evaluate_*), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The fixture is the air-gapped local stand-in for a real long-poll backend; the
framework-specific part — turning one channel's brief into the plan via the model — is
injected as `generate(cfg) -> plan dict`. A per-poll unique `key` isolates concurrent
polls so parallel agent runs never cross-talk.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8921").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-long-polling-support" / "longpoll_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import longpoll_spec  # noqa: E402

# How long after a poll opens the harness publishes the event (well within poll_timeout_s
# and the task's 10 s trigger bound). Kept in sync with the fixture's TRIGGER_DELAY_S.
TRIGGER_DELAY_S = float(os.environ.get("FORGE_TRIGGER_DELAY_S", "1.5"))


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
# G1 staging write
# --------------------------------------------------------------------------- #
def _write_staging_findings(
    agent: str,
    item_id: str,
    item_label: str,
    step_results: list[dict],
) -> None:
    """Write per-item step findings to the G1 staging directory.

    Path: results/runs/{RUN_ID}/staging/{agent}/{item_id}-findings.json

    Called once per item (endpoint / collection / scenario) after all steps
    for that item are complete. The G1b orchestration step reads these files
    and passes them to test-case-creator as evidence of what this agent observed.
    """
    staging_dir = WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{item_id}-findings.json"
    _assert_sandbox(out_path)

    findings = []
    for i, r in enumerate(step_results, start=1):
        findings.append({
            "step_number": i,
            "item_id": item_id,
            "item_label": item_label,
            **r,
        })

    out_path.write_text(json.dumps({
        "agent": agent,
        "item_id": item_id,
        "item_label": item_label,
        "run_id": RUN_ID,
        "findings": findings,
    }, indent=2))


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def channel_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for c in spec["channels"]:
        out.append({
            "channel": c["channel"],
            "poll_path": c["poll_path"],
            "trigger_path": c["trigger_path"],
            "poll_timeout_s": c["poll_timeout_s"],
            "expected_event_type": c["expected_event_type"],
        })
    only = os.environ.get("FORGE_ONLY_CHANNELS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [c for c in out if c["channel"] in wanted]
    return out


def channel_brief(cfg: dict) -> str:
    """Compact, unambiguous long-poll contract handed to the model."""
    return "\n".join([
        f"channel: {cfg['channel']}",
        f"poll_path: {cfg['poll_path']}                 # GET path that opens the long-poll connection",
        f"trigger_path: {cfg['trigger_path']}           # path of the separate call that publishes one event",
        f"poll_timeout_s: {cfg['poll_timeout_s']}       # documented whole-second hold before an event-less poll closes",
        f"expected_event_type: {cfg['expected_event_type']}   # exact value the event's \"event_type\" must equal",
    ])


# --------------------------------------------------------------------------- #
# Raw HTTP/1.1 socket client — measures long-poll timing
# --------------------------------------------------------------------------- #
def _recv_head(sock: socket.socket, cap: int = 65536) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < cap:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def _parse_response(head: bytes, sock: socket.socket) -> dict:
    """Parse a raw HTTP response already partially read into `head`. Returns
    {status, content_length, body}."""
    header_blob, _, rest = head.partition(b"\r\n\r\n")
    lines = header_blob.split(b"\r\n")
    status = None
    try:
        status = int(lines[0].split(b" ")[1])
    except Exception:  # noqa
        status = None
    content_length = 0
    have_cl = False
    for h in lines[1:]:
        k, _, v = h.partition(b":")
        if k.strip().lower() == b"content-length":
            try:
                content_length = int(v.strip())
                have_cl = True
            except ValueError:
                pass
    body_bytes = rest
    while have_cl and len(body_bytes) < content_length:
        chunk = sock.recv(min(4096, content_length - len(body_bytes)))
        if not chunk:
            break
        body_bytes += chunk
    body = None
    if content_length:
        try:
            body = json.loads(body_bytes[:content_length] or b"null")
        except Exception:  # noqa
            body = None
    return {"status": status, "content_length": content_length if have_cl else None,
            "body": body}


def _send_get(sock: socket.socket, host: str, port: int, path: str) -> None:
    req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n").encode()
    sock.sendall(req)


def poll_no_event(poll_path: str, poll_timeout_s, client_max_time_s) -> dict:
    """Open a long-poll that is never triggered. Returns
    {status, content_length, elapsed_s}. status None on a client-side timeout (a hang)."""
    host, port = _host_port()
    key = "noevt-" + uuid.uuid4().hex[:10]
    path = f"{poll_path}?timeout={poll_timeout_s}&key={key}"
    read_to = float(client_max_time_s)
    t0 = time.monotonic()
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=read_to)
        sock.settimeout(read_to)
        _send_get(sock, host, port, path)
        head = _recv_head(sock)
        if not head:
            return {"status": None, "content_length": None, "elapsed_s": time.monotonic() - t0}
        parsed = _parse_response(head, sock)
        return {"status": parsed["status"], "content_length": parsed["content_length"],
                "elapsed_s": time.monotonic() - t0}
    except (socket.timeout, TimeoutError):
        return {"status": None, "content_length": None, "elapsed_s": time.monotonic() - t0}
    except Exception:  # noqa
        return {"status": None, "content_length": None, "elapsed_s": time.monotonic() - t0}
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa
                pass


def poll_with_event(poll_path: str, trigger_path: str, poll_timeout_s,
                    client_max_time_s) -> dict:
    """Open a long-poll and publish one event ~TRIGGER_DELAY_S in via a background thread.
    Returns {status, body, elapsed_s, response_after_event_s, event_offset_s}."""
    host, port = _host_port()
    key = "evt-" + uuid.uuid4().hex[:10]
    path = f"{poll_path}?timeout={poll_timeout_s}&key={key}"
    read_to = float(client_max_time_s)
    t_event = {"v": None}

    def _trigger() -> None:
        time.sleep(TRIGGER_DELAY_S)
        url = f"http://{host}:{port}{trigger_path}?key={key}"
        req = urllib.request.Request(url, data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:  # noqa
            pass
        t_event["v"] = time.monotonic()

    sock = None
    t0 = None
    th = threading.Thread(target=_trigger, daemon=True)
    try:
        sock = socket.create_connection((host, port), timeout=read_to)
        sock.settimeout(read_to)
        t0 = time.monotonic()
        _send_get(sock, host, port, path)
        th.start()
        head = _recv_head(sock)
        t_resp = time.monotonic()
        th.join(timeout=10)
        if not head:
            return {"status": None, "body": None, "elapsed_s": t_resp - t0,
                    "response_after_event_s": None, "event_offset_s": None}
        parsed = _parse_response(head, sock)
        te = t_event["v"]
        raf = (t_resp - te) if te is not None else None
        return {"status": parsed["status"], "body": parsed["body"],
                "elapsed_s": t_resp - t0,
                "response_after_event_s": (round(max(0.0, raf), 3) if raf is not None else None),
                "event_offset_s": (round(te - t0, 3) if te is not None else None)}
    except (socket.timeout, TimeoutError):
        te = t_event["v"]
        return {"status": None, "body": None, "elapsed_s": read_to,
                "response_after_event_s": None,
                "event_offset_s": (round(te - t0, 3) if (te is not None and t0 is not None) else None)}
    except Exception:  # noqa
        return {"status": None, "body": None, "elapsed_s": None,
                "response_after_event_s": None, "event_offset_s": None}
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa
                pass


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
def run_longpoll_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the long-poll plan object for one channel: a dict with the
    seven keys (channel, poll_path, trigger_path, poll_timeout_s, expected_event_type,
    client_max_time_s, cases). The harness opens the planned no-event + event polls,
    triggers the event, evaluates status/timing/body, and scores every scenario.
    Whatever the agent omits or miscopies scores as 'missing' or a divergent token.
    """
    cfgs = channel_cfgs()

    # 1) elicit a plan per channel (the framework-specific step)
    plans, gen_errors = {}, {}
    for cfg in cfgs:
        try:
            plans[cfg["channel"]] = generate(cfg) or {}
        except Exception as e:  # noqa
            plans[cfg["channel"]] = {}
            gen_errors[cfg["channel"]] = f"{type(e).__name__}: {e}"

    all_cases = []
    cases_total = cases_passed = 0          # headline: Long-Poll Response Accuracy
    scenarios_total = scenarios_correct = 0
    reqlog = []

    for cfg in cfgs:
        ch = cfg["channel"]
        plan = plans[ch] if isinstance(plans[ch], dict) else {}
        cases = plan.get("cases") if isinstance(plan.get("cases"), list) else []
        kinds = {c.get("kind") for c in cases if isinstance(c, dict)}

        poll_path = plan.get("poll_path")
        trigger_path = plan.get("trigger_path")
        agent_poll_timeout = plan.get("poll_timeout_s")
        agent_cmt = plan.get("client_max_time_s")

        ne_obs = ev_obs = None
        # 2) execute the no-event poll the agent planned
        if "no_event" in kinds and poll_path and agent_poll_timeout is not None and agent_cmt is not None:
            r = poll_no_event(poll_path, agent_poll_timeout, agent_cmt)
            ne_obs = r
            reqlog.append({"channel": ch, "case": "no_event", "status": r.get("status"),
                           "content_length": r.get("content_length"),
                           "elapsed_s": round(r.get("elapsed_s") or 0.0, 3)})
        # 3) execute the event poll the agent planned
        if "event" in kinds and poll_path and trigger_path and agent_poll_timeout is not None and agent_cmt is not None:
            r = poll_with_event(poll_path, trigger_path, agent_poll_timeout, agent_cmt)
            ev_obs = r
            reqlog.append({"channel": ch, "case": "event", "status": r.get("status"),
                           "elapsed_s": round(r.get("elapsed_s") or 0.0, 3),
                           "response_after_event_s": r.get("response_after_event_s"),
                           "event_offset_s": r.get("event_offset_s")})

        # 4) evaluate every scenario against the shared scheme (window vs the documented
        #    poll_timeout_s, a property of the target — identical for gold and every agent)
        ne_tok = longpoll_spec.evaluate_no_event(ne_obs, cfg["poll_timeout_s"])
        ev_tok = longpoll_spec.evaluate_event(ev_obs, cfg["expected_event_type"])
        ch_tok = longpoll_spec.evaluate_channel(plan, cfg)

        scenarios = []
        for label in longpoll_spec.NO_EVENT_SCENARIO_LABELS:
            tok = ne_tok.get(label, "missing")
            ok = longpoll_spec.correct(label, tok)
            scenarios.append({"channel": ch, "scenario": label,
                              "ideal": longpoll_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            scenarios_total += 1
            scenarios_correct += 1 if ok else 0
        for label in longpoll_spec.EVENT_SCENARIO_LABELS:
            tok = ev_tok.get(label, "missing")
            ok = longpoll_spec.correct(label, tok)
            scenarios.append({"channel": ch, "scenario": label,
                              "ideal": longpoll_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            scenarios_total += 1
            scenarios_correct += 1 if ok else 0
        for label in longpoll_spec.CHANNEL_SCENARIO_LABELS:
            tok = ch_tok.get(label, "missing")
            ok = longpoll_spec.correct(label, tok)
            scenarios.append({"channel": ch, "scenario": label,
                              "ideal": longpoll_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            scenarios_total += 1
            scenarios_correct += 1 if ok else 0

        # headline accuracy: two cases per channel
        cases_total += 2
        cases_passed += 1 if longpoll_spec.no_event_case_pass(ne_tok) else 0
        cases_passed += 1 if longpoll_spec.event_case_pass(ev_tok) else 0

        all_cases.append({"channel": ch, "emitted_plan": plan, "scenarios": scenarios,
                          "error": gen_errors.get(ch)})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(ch).strip("/").replace("/", "-") or "channel",
            item_label=str(ch),
            step_results=[
                {
                    "assertion_result": "PASS" if s.get("api_correct") else "FAIL",
                    "assertion_detail": (
                        f"scenario={s.get('scenario')} ideal={s.get('ideal')} "
                        f"observed={s.get('observed_token')}"
                    ),
                    **s,
                }
                for s in scenarios
            ],
        )

    accuracy = round(100.0 * cases_passed / cases_total, 2) if cases_total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "longpoll_response_accuracy_pct": accuracy,
           "cases_total": cases_total, "cases_passed": cases_passed,
           "scenarios_total": scenarios_total, "scenarios_api_correct": scenarios_correct,
           "request_log": reqlog, "channels": all_cases}

    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, accuracy, str(cases_path), extra={
        "longpoll_response_accuracy_pct": accuracy,
        "cases_total": cases_total, "cases_passed": cases_passed})

    everos_note(agent, f"long-polling run: response_accuracy={accuracy}% "
                       f"over {len(cfgs)} channels ({cases_passed}/{cases_total} cases passed)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Long-Poll Response Accuracy; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-long-polling-support" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "longpoll_response_accuracy_pct"),
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
