"""Shared, deterministic plumbing for the four caching-headers testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint catalogue from
    data/verify-caching-headers/caching_spec.json
  - build the compact per-endpoint brief handed to the agent
  - execute whatever plan the agent emitted, in this fixed order:
      1. GET  the cacheable resource           -> status, Cache-Control, ETag (ETAG_1)
      2. GET  with If-None-Match: ETAG_1        -> status (304?), body byte length
      3. PUT  the update_request (changed field)-> status (200?)
      4. GET  the cacheable resource again      -> status, ETag (ETAG_2)
      5. GET  with If-None-Match: ETAG_1 (stale)-> status (200 or 304?)
      6. for each mutation_request              -> status, Cache-Control (no-store?)
  - evaluate every scenario (shared caching_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

WRITES NOTE — this task issues PUT/PATCH/POST/DELETE. It is safe because the DummyJSON
target's data is deepFrozen and its controllers RETURN computed objects without
persisting (verified in src/controllers/*.js and live: GET after the writes shows the
record + ETag unchanged). All requests go to the LOCAL target only (host guard) and stay
within the sandbox.

The framework-specific part — turning one endpoint's brief into the caching test plan
via the backend LLM — is injected as `generate(cfg) -> plan dict`.
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
SPEC_PATH = WORKSPACE / "data" / "verify-caching-headers" / "caching_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import caching_spec  # noqa: E402


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
    """Compact, unambiguous caching contract handed to the LLM."""
    return "\n".join([
        f"collection_path: {cfg['collection']}",
        f"id_field: {cfg['id_field']}        # each item's unique id is under this key",
        f"target_id: {cfg['target_id']}       # the single existing record the plan exercises",
        "note: the plan declares the cacheable GET for this record, one PUT update request "
        "that changes a field, and the four mutation requests (POST add, PUT, PATCH, DELETE) "
        "whose responses are checked for a no-store directive; the executor sends them, "
        "records the real Cache-Control/ETag headers, statuses, and the conditional-GET body "
        "length, and scores them. The agent never sends anything and never guesses a response.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (header + body capture) + plan execution
# --------------------------------------------------------------------------- #
def _send(method: str, path: str, body, extra_headers: dict | None = None, _retries: int = 2):
    """Send one request to the LOCAL target. Returns (status, headers_dict, body_bytes).
    headers_dict is case-insensitive-keyed (lowercased). Small retry on transient
    connection failure only; real HTTP error codes are returned as-is."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = None
    headers = dict(extra_headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                return r.getcode(), {k.lower(): v for k, v in r.getheaders()}, raw
        except urllib.error.HTTPError as e:  # a real response from the API
            try:
                raw = e.read()
            except Exception:  # noqa
                raw = b""
            return e.code, {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}, raw
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return None, {}, b""


def _get(path: str, extra_headers: dict | None = None):
    return _send("GET", path, None, extra_headers)


def _exec_plan(cfg: dict, plan: dict):
    """Execute the AGENT's plan in the fixed caching-probe order. Tolerant of
    missing/malformed keys — whatever the agent omits is simply not sent and the
    dependent scenarios score 'missing'."""
    reqlog = []
    if not isinstance(plan, dict):
        plan = {}

    get_obs = {"status": None, "cache_control": None, "etag": None}
    conditional_obs = {"status": None, "body_len": None}
    update_obs = {"status": None}
    reget_obs = {"status": None, "etag": None}
    stale_obs = {"status": None}
    mutation_obs: dict[str, dict] = {}

    # 1. cacheable GET -> ETAG_1 + Cache-Control
    cg = plan.get("cacheable_get")
    etag1 = None
    if isinstance(cg, dict) and cg.get("path"):
        status, hdrs, raw = _get(cg["path"])
        etag1 = hdrs.get("etag")
        get_obs = {"status": status, "cache_control": hdrs.get("cache-control"), "etag": etag1}
        reqlog.append({"label": "get", "method": "GET", "path": cg["path"], "status": status,
                       "cache_control": hdrs.get("cache-control"), "etag": etag1,
                       "body_len": len(raw)})

        # 2. conditional GET with If-None-Match: ETAG_1
        if etag1:
            cstatus, _chdrs, craw = _get(cg["path"], {"If-None-Match": etag1})
            conditional_obs = {"status": cstatus, "body_len": len(craw)}
            reqlog.append({"label": "conditional_get", "method": "GET", "path": cg["path"],
                           "if_none_match": etag1, "status": cstatus, "body_len": len(craw)})

    # 3. PUT the update_request (changed field)
    ur = plan.get("update_request")
    if isinstance(ur, dict) and ur.get("method") and ur.get("path"):
        ustatus, _uh, _ub = _send(ur["method"], ur["path"], ur.get("body"))
        update_obs = {"status": ustatus}
        reqlog.append({"label": "update", "method": ur["method"], "path": ur["path"],
                       "status": ustatus})

        # 4. fresh GET -> ETAG_2
        if isinstance(cg, dict) and cg.get("path"):
            rstatus, rhdrs, _rb = _get(cg["path"])
            etag2 = rhdrs.get("etag")
            reget_obs = {"status": rstatus, "etag": etag2}
            reqlog.append({"label": "reget", "method": "GET", "path": cg["path"],
                           "status": rstatus, "etag": etag2,
                           "etag_changed": (etag1 is not None and etag2 is not None and etag2 != etag1)})

            # 5. stale conditional GET with the old ETAG_1
            if etag1:
                sstatus, _sh, _sb = _get(cg["path"], {"If-None-Match": etag1})
                stale_obs = {"status": sstatus}
                reqlog.append({"label": "stale_conditional_get", "method": "GET", "path": cg["path"],
                               "if_none_match": etag1, "status": sstatus})

    # 6. mutation no-store probes
    muts = plan.get("mutation_requests")
    if isinstance(muts, list):
        for req in muts:
            if not isinstance(req, dict) or "label" not in req or not req.get("method") or not req.get("path"):
                continue
            mstatus, mh, _mb = _send(req["method"], req["path"], req.get("body"))
            cc = mh.get("cache-control")
            mutation_obs[req["label"]] = {"status": mstatus, "cache_control": cc}
            reqlog.append({"label": f"mutation_{req['label']}", "method": req["method"],
                           "path": req["path"], "status": mstatus, "cache_control": cc})

    return get_obs, conditional_obs, update_obs, reget_obs, stale_obs, mutation_obs, reqlog


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
def run_caching_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the caching plan object (see caching_spec): a dict with
        `cacheable_get`, `update_request`, and `mutation_requests`. The harness executes
        the AGENT's planned requests, captures the real headers/statuses/body lengths,
        and evaluates every scenario. Whatever the agent fails to emit scores as
        'missing'. generate may raise; recorded per-endpoint.
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

        get_obs, cond_obs, upd_obs, reget_obs, stale_obs, mut_obs, reqlog = _exec_plan(cfg, plan)
        observed = caching_spec.evaluate(get_obs, cond_obs, upd_obs, reget_obs, stale_obs, mut_obs)
        observed_by_collection[cfg["collection"]] = observed

        scenarios = []
        for label in caching_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = caching_spec.correct(label, tok)
            scenarios.append({"collection": cfg["collection"], "scenario": label,
                              "ideal": caching_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"collection": cfg["collection"], "target_id": cfg["target_id"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

    comp = caching_spec.compliance(observed_by_collection)
    correctness_rate = round(100.0 * correct / total, 2) if total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "caching_header_compliance_rate_pct": comp["rate_pct"],
           "caching_correctness_rate_pct": correctness_rate,
           "compliance_cases": comp,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "collections": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, comp["rate_pct"], str(cases_path), extra={
        "caching_header_compliance_rate_pct": comp["rate_pct"],
        "caching_correctness_rate_pct": correctness_rate,
        "scenarios_total": total})

    everos_note(agent, f"caching-headers-test run: compliance_rate={comp['rate_pct']}% "
                       f"({comp['passing']}/{comp['total']} cacheable endpoints) over "
                       f"{len(cfgs)} collections ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Caching Header Compliance Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "verify-caching-headers" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "caching_header_compliance_rate_pct"),
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
