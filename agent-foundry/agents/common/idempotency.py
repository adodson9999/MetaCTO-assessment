"""Shared, deterministic plumbing for the four idempotency-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the collection catalogue from
    data/test-idempotency-of-endpoints/idempotency_spec.json
  - build the compact per-collection brief handed to the agent
  - execute whatever plan the agent emitted: send each idempotent request its
    declared number of times with the declared Idempotency-Key, capture every
    response code AND raw body byte-for-byte; send the create request's replays and
    a fresh-key request; run read-only state-effect probes (GET) for the record count
  - evaluate every scenario (shared idempotency_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

WRITES NOTE — this is the one task that issues PUT/DELETE/POST. It is safe because
the DummyJSON target's data is deepFrozen and its controllers RETURN computed objects
without persisting (verified in src/controllers/*.js and live: GET after the writes
shows the record unchanged and the collection `total` unchanged). All requests still
go to the LOCAL target only (host guard) and stay within the sandbox.

The framework-specific part — turning one collection's brief into the idempotency
test plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-idempotency-of-endpoints" / "idempotency_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import idempotency_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


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


def collection_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for c in spec["collections"]:
        out.append({
            "collection": c["collection"],
            "id_field": spec.get("id_field", "id"),
            "target_id": spec.get("target_id", 1),
        })
    only = os.environ.get("FORGE_ONLY_COLLECTIONS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["collection"] in wanted]
    return out


def collection_brief(cfg: dict) -> str:
    """Compact, unambiguous idempotency contract handed to the LLM."""
    return "\n".join([
        f"collection_path: {cfg['collection']}",
        f"id_field: {cfg['id_field']}        # each item's unique id is under this key",
        f"target_id: {cfg['target_id']}       # the single existing record the plan exercises",
        "note: the plan probes idempotency of the PUT and DELETE endpoints for this "
        "record and the POST add endpoint for the collection; the executor sends each "
        "request the planned number of times with the planned Idempotency-Key and "
        "compares responses byte-for-byte.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (with writes) + plan execution
# --------------------------------------------------------------------------- #
def _send(method: str, path: str, body, idem_key: str | None, _retries: int = 2):
    """Send one request to the LOCAL target. Returns (status_code, raw_body_str).
    raw_body_str is the EXACT response text (for byte-for-byte comparison). Small
    retry on transient connection failure (status -1) only; real HTTP error codes
    are returned as-is."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if idem_key is not None:
        headers[idempotency_spec.HEADER_NAME] = idem_key
    last = (-1, None)
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:  # a real response from the API
            try:
                return e.code, e.read().decode("utf-8", "replace")
            except Exception:  # noqa
                return e.code, None
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            last = (-1, None)
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return last


def _get(path: str, _retries: int = 2):
    return _send("GET", path, None, None, _retries=_retries)


def _replay(req: dict):
    """Send one planned request `replays` times with its Idempotency-Key, capturing
    every code and raw body. Tolerant of a missing/malformed request (returns None)."""
    if not isinstance(req, dict):
        return None
    method = req.get("method")
    path = req.get("path")
    if not method or not path:
        return None
    body = req.get("body")
    key = req.get("idempotency_key")
    n = req.get("replays", idempotency_spec.REPLAYS)
    try:
        n = int(n)
    except Exception:  # noqa
        n = idempotency_spec.REPLAYS
    n = max(1, min(n, 10))  # bound: never an unbounded flood, regardless of plan
    codes, bodies = [], []
    for i in range(n):
        if i:
            time.sleep(idempotency_spec.INTER_REPLAY_DELAY_S)  # surface time-varying fields
        code, raw = _send(method, path, body, key)
        codes.append(code)
        bodies.append(raw)
    return {"method": method, "path": path, "idempotency_key": key,
            "replays": n, "codes": codes, "bodies": bodies}


def _record_count(path: str) -> int | None:
    """State-effect probe: does exactly one record exist at this resource path?
    GET path -> 200 => 1 (present), 404 => 0 (absent), anything else => None."""
    code, _ = _get(path)
    if code == 200:
        return 1
    if code == 404:
        return 0
    return None


def _exec_plan(cfg: dict, plan: dict):
    """Execute the AGENT's plan. Tolerant of missing/malformed keys — whatever the
    agent omits is simply not sent and scores as 'missing'."""
    write_obs, create_obs, reqlog, state = {}, {}, [], {}
    if not isinstance(plan, dict):
        plan = {}

    for req in plan.get("idempotent_requests", []) if isinstance(plan.get("idempotent_requests"), list) else []:
        if not isinstance(req, dict) or "label" not in req:
            continue
        rec = _replay(req)
        if rec is None:
            continue
        write_obs[req["label"]] = rec
        reqlog.append({"label": req["label"], "method": rec["method"], "path": rec["path"],
                       "idempotency_key": rec["idempotency_key"], "replays": rec["replays"],
                       "codes": rec["codes"], "bodies_identical": _ident(rec["bodies"])})

    cr = plan.get("create_request")
    if isinstance(cr, dict) and "method" in cr and "path" in cr:
        rec = _replay(cr)
        if rec is not None:
            second_key = cr.get("second_key")
            scode, sbody = _send(cr.get("method"), cr.get("path"), cr.get("body"), second_key)
            rec["second"] = {"code": scode, "body": sbody, "second_key": second_key}
            create_obs = rec
            reqlog.append({"label": cr.get("label", "post"), "method": rec["method"],
                           "path": rec["path"], "idempotency_key": rec["idempotency_key"],
                           "replays": rec["replays"], "codes": rec["codes"],
                           "bodies_identical": _ident(rec["bodies"]),
                           "second_key": second_key, "second_code": scode,
                           "second_distinct_from_first": (sbody is not None
                                                          and sbody != rec["bodies"][0])})

    # read-only state-effect probes for the "exactly one record" assertion
    put, dele = write_obs.get("put"), write_obs.get("delete")
    state["put_record_count"] = _record_count(put["path"]) if put else None
    state["delete_record_count"] = _record_count(dele["path"]) if dele else None

    return write_obs, create_obs, reqlog, state


def _ident(bodies):
    return bool(bodies) and all(b == bodies[0] for b in bodies)


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
            body = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=body,
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
def run_idempotency_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the idempotency plan object (see idempotency_spec): a dict
        with `idempotent_requests` (put + delete, each {label, method, path, body,
        idempotency_key, replays}) and `create_request` (the post add, plus second_key).
        The harness executes the AGENT's planned requests, captures raw bodies, runs
        the read-only state probes, and evaluates every scenario. Whatever the agent
        fails to emit scores as 'missing'. generate may raise; recorded per-collection.
    """
    cfgs = collection_cfgs()
    all_cases = []
    observed_by_collection = {}
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        write_obs, create_obs, reqlog, state = _exec_plan(cfg, plan)
        observed = idempotency_spec.evaluate(write_obs, create_obs, state)
        observed_by_collection[cfg["collection"]] = observed

        scenarios = []
        for label in idempotency_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = idempotency_spec.correct(label, tok)
            scenarios.append({"collection": cfg["collection"], "scenario": label,
                              "ideal": idempotency_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"collection": cfg["collection"], "target_id": cfg["target_id"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "state_probe": state, "scenarios": scenarios, "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=cfg["collection"].strip("/").replace("/", "-") or "root",
            item_label=cfg["collection"],
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

    comp = idempotency_spec.compliance(observed_by_collection)
    correctness_rate = round(100.0 * correct / total, 2) if total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "idempotency_compliance_rate_pct": comp["rate_pct"],
           "idempotency_correctness_rate_pct": correctness_rate,
           "compliance_cases": comp,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "collections": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, comp["rate_pct"], str(cases_path), extra={
        "idempotency_compliance_rate_pct": comp["rate_pct"],
        "idempotency_correctness_rate_pct": correctness_rate,
        "scenarios_total": total})

    everos_note(agent, f"idempotency-test run: compliance_rate={comp['rate_pct']}% "
                       f"({comp['passing']}/{comp['total']} endpoint cases) over "
                       f"{len(cfgs)} collections ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Idempotency Compliance Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-idempotency-of-endpoints" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "idempotency_compliance_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
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
