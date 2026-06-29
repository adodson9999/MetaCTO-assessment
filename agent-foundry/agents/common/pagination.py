"""Shared, deterministic plumbing for the four pagination-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the collection catalogue from data/test-pagination-behavior/pagination_spec.json
  - build the compact per-collection brief handed to the agent
  - designate the 25-record window via a READ-ONLY GET ?limit=25&skip=0
  - execute whatever plan the agent emitted with READ-ONLY GET requests to the
    LOCAL target only (sandbox + host + method guards)
  - evaluate every scenario (shared pagination_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified: GET only, no body, no mutation.

The framework-specific part — turning one collection's brief into the pagination
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
SPEC_PATH = WORKSPACE / "data" / "test-pagination-behavior" / "pagination_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import pagination_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host + method guards
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
            "list_field": c["list_field"],
            "id_field": spec.get("id_field", "id"),
            "limit_param": spec.get("limit_param", "limit"),
            "offset_param": spec.get("offset_param", "skip"),
            "page_size": spec.get("page_size", 10),
            "window_size": spec.get("window_size", 25),
        })
    only = os.environ.get("FORGE_ONLY_COLLECTIONS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["collection"] in wanted or c["list_field"] in wanted]
    return out


def collection_brief(cfg: dict) -> str:
    """Compact, unambiguous pagination contract handed to the LLM."""
    return "\n".join([
        f"collection_path: {cfg['collection']}",
        f"list_field: {cfg['list_field']}   # response items live under this key",
        f"id_field: {cfg['id_field']}        # each item's unique id is under this key",
        f"page_size_param: {cfg['limit_param']}   # query param that sets page size",
        f"offset_param: {cfg['offset_param']}     # query param that sets the row offset",
        f"page_size: {cfg['page_size']}",
        f"window_size: {cfg['window_size']}   # the first {cfg['window_size']} records form the window under test",
        "response_shape: the body is a JSON object with the items under list_field "
        "plus a sibling integer 'total'; there is no cursor field.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (read-only GET) + plan execution
# --------------------------------------------------------------------------- #
def _get(path: str, params: dict, _retries: int = 2):
    """Read-only GET with a small retry on transient connection failure (status -1)
    so a momentary target hiccup during a long parallel run does not corrupt a whole
    collection. HTTP error codes (e.g. 400) are real responses and are returned as-is."""
    qs = urllib.parse.urlencode(params)
    url = f"{TARGET_BASE_URL}{path}?{qs}" if qs else f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    last = -1
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method="GET")  # GET only — never mutate the target
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                try:
                    return r.getcode(), json.loads(body)
                except Exception:  # noqa
                    return r.getcode(), None
        except urllib.error.HTTPError as e:
            return e.code, None  # a real response from the API, not a transient failure
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            last = -1
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return last, None


def _window_ids(cfg: dict) -> list:
    status, body = _get(cfg["collection"],
                        {cfg["limit_param"]: cfg["window_size"], cfg["offset_param"]: 0})
    if status == 200 and isinstance(body, dict):
        items = body.get(cfg["list_field"], [])
        if isinstance(items, list):
            return [it.get(cfg["id_field"]) for it in items][:cfg["window_size"]]
    return []


def _exec_plan(cfg: dict, plan: dict):
    """Execute the AGENT's plan (read-only). Tolerant of missing/malformed keys —
    whatever the agent omits simply does not get sent and scores as 'missing'."""
    page_obs, invalid_obs, reqlog = {}, {}, []
    lf, idf = cfg["list_field"], cfg["id_field"]
    lp, op = cfg["limit_param"], cfg["offset_param"]

    for pg in plan.get("pages", []) if isinstance(plan, dict) else []:
        if not isinstance(pg, dict) or "label" not in pg:
            continue
        # Accept either explicit limit/skip or a params object.
        if "params" in pg and isinstance(pg["params"], dict):
            params = pg["params"]
            skip = _to_int(params.get(op))
        else:
            params = {lp: pg.get("limit"), op: pg.get("skip")}
            skip = _to_int(pg.get("skip"))
        params = {k: v for k, v in params.items() if v is not None}
        status, body = _get(cfg["collection"], params)
        ids, total = None, None
        if status == 200 and isinstance(body, dict):
            items = body.get(lf, [])
            ids = [it.get(idf) for it in items] if isinstance(items, list) else None
            total = body.get("total")
        page_obs[pg["label"]] = {"status": status, "ids": ids,
                                 "skip": skip if skip is not None else 0, "total": total}
        reqlog.append({"label": pg["label"], "params": params, "status": status,
                       "returned_count": (len(ids) if ids is not None else None), "total": total})

    for iv in plan.get("invalid", []) if isinstance(plan, dict) else []:
        if not isinstance(iv, dict) or "label" not in iv:
            continue
        params = iv.get("params") if isinstance(iv.get("params"), dict) else {}
        status, _ = _get(cfg["collection"], params)
        invalid_obs[iv["label"]] = {"status": status}
        reqlog.append({"label": iv["label"], "params": params, "status": status})

    return page_obs, invalid_obs, reqlog


def _to_int(v):
    try:
        return int(v)
    except Exception:  # noqa
        return None


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
def run_pagination_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the pagination plan object (see pagination_spec): a dict
        with `pages` (each {label, limit, skip}) and `invalid` (each {label, params}).
        The harness designates the 25-record window itself (read-only), executes the
        AGENT's planned requests, and evaluates every scenario. Whatever the agent
        fails to emit scores as 'missing'. generate may raise; recorded per-collection.
    """
    cfgs = collection_cfgs()
    all_cases = []
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        window = _window_ids(cfg)
        page_obs, invalid_obs, reqlog = _exec_plan(cfg, plan)
        observed = pagination_spec.evaluate(window, page_obs, invalid_obs)

        scenarios = []
        for label in pagination_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = pagination_spec.correct(label, tok)
            scenarios.append({"collection": cfg["collection"], "scenario": label,
                              "ideal": pagination_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"collection": cfg["collection"], "list_field": cfg["list_field"],
                          "expected_ids": window, "emitted_plan": plan,
                          "request_log": reqlog, "scenarios": scenarios,
                          "error": gen_error})

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

    rate = round(100.0 * correct / total, 2) if total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "pagination_correctness_rate_pct": rate,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "collections": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "pagination_correctness_rate_pct": rate,
        "scenarios_total": total})

    everos_note(agent, f"pagination-test run: correctness_rate={rate}% "
                       f"over {len(cfgs)} collections ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    pagination-correctness rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-pagination-behavior" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "pagination_correctness_rate_pct"),
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
