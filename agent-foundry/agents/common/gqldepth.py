"""Shared, deterministic plumbing for the four GraphQL-depth-limit agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint catalogue + documented max_depth per endpoint from
    data/validate-graphql-depth-limits/gqldepth_spec.json
  - build the compact per-endpoint brief handed to the agent (endpoint + max_depth +
    the four required probe rules; never the answers)
  - the deterministic query-generator: turn each case's requested depth into a real
    GraphQL query (gqldepth_spec.build_query)
  - execute the agent's plan by POSTing each query to the LOCAL GraphQL SUT only
    (sandbox + host + endpoint guards), capturing the status, whether data is non-null,
    the errors array, the first error message, and the wall-clock response time
  - evaluate every scenario (shared gqldepth_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

A GraphQL query is read-only (no mutation resolvers exist on the SUT); DummyJSON is
never contacted or modified by this task.

The framework-specific part — turning one endpoint's brief into the depth test plan
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
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8940").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "validate-graphql-depth-limits" / "gqldepth_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import gqldepth_spec  # noqa: E402


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


def endpoint_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for e in spec["endpoints"]:
        out.append({"endpoint": e["endpoint"], "max_depth": e["max_depth"]})
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["endpoint"] in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous depth-limit contract handed to the LLM. Carries the
    endpoint, its documented max_depth, and the four required probe rules — but NO
    answers (no resolved depths for at_limit/one_over, no status codes)."""
    return "\n".join([
        f"endpoint: {cfg['endpoint']}            # the GraphQL endpoint under test (POST)",
        f"max_depth: {cfg['max_depth']}                 # documented maximum allowed query depth",
        f"depth_unit: {gqldepth_spec.DEPTH_UNIT}",
        "required_probes (emit these four cases, in this order):",
        "  - depth_3   : a query of depth 3            -> expected ACCEPT (3 is at/below max_depth)",
        "  - at_limit  : a query of depth = max_depth  -> expected ACCEPT (exactly the limit)",
        "  - one_over  : a query of depth = max_depth+1 -> expected REJECT (one over the limit)",
        "  - deep_15   : a query of depth 15           -> expected REJECT, quickly",
    ])


# --------------------------------------------------------------------------- #
# HTTP (POST GraphQL query) + plan execution
# --------------------------------------------------------------------------- #
def _post_query(path: str, query: str, _retries: int = 2):
    """POST a GraphQL {"query": ...} body. Returns (status_code, parsed_json|None,
    elapsed_seconds). A GraphQL query is read-only; the SUT has no mutation resolvers.
    HTTP error codes (e.g. 400) are real responses and are returned with their parsed
    body so the error message can be inspected. Small retry only on transient
    connection failure (status -1)."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    body = json.dumps({"query": query}).encode()
    last = (-1, None, None)
    for attempt in range(_retries + 1):
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                elapsed = time.perf_counter() - start
                try:
                    return r.getcode(), json.loads(raw), elapsed
                except Exception:  # noqa
                    return r.getcode(), None, elapsed
        except urllib.error.HTTPError as e:
            elapsed = time.perf_counter() - start
            try:
                return e.code, json.loads(e.read()), elapsed
            except Exception:  # noqa
                return e.code, None, elapsed
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            last = (-1, None, None)
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return last


def _observe(path: str, depth: int) -> dict:
    """Build the depth-`depth` GraphQL query (deterministic), POST it, and record the
    raw observation the scenario evaluator consumes."""
    query = gqldepth_spec.build_query(depth)
    status, body, elapsed = _post_query(path, query)
    data_present, errors, message = False, None, None
    if isinstance(body, dict):
        data_present = body.get("data") is not None
        errs = body.get("errors")
        if isinstance(errs, list):
            errors = errs
            if errs and isinstance(errs[0], dict):
                msg = errs[0].get("message")
                message = msg if isinstance(msg, str) else None
    return {"status": status, "data_present": data_present, "errors": errors,
            "message": message, "elapsed": elapsed, "sent_depth": depth, "query": query}


def _exec_plan(cfg: dict, plan: dict):
    """Execute the AGENT's plan. Tolerant of missing/malformed keys — whatever the
    agent omits simply does not get sent and scores as 'missing'."""
    case_obs, reqlog = {}, []
    path = cfg["endpoint"]
    for case in plan.get("cases", []) if isinstance(plan, dict) else []:
        if not isinstance(case, dict) or "label" not in case:
            continue
        depth = case.get("depth")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 1:
            # No usable depth -> the case is effectively un-sendable; record nothing
            # so its scenarios score as 'missing'.
            reqlog.append({"label": case["label"], "type": case.get("type"),
                           "path": path, "depth": depth, "status": None,
                           "note": "invalid or missing integer depth; not sent"})
            continue
        rec = _observe(path, depth)
        case_obs[case["label"]] = rec
        reqlog.append({"label": case["label"], "type": case.get("type"), "path": path,
                       "sent_depth": depth, "status": rec["status"],
                       "data_present": rec["data_present"],
                       "errors_count": (len(rec["errors"]) if isinstance(rec["errors"], list) else None),
                       "message": rec["message"],
                       "elapsed_s": round(rec["elapsed"], 4) if rec["elapsed"] is not None else None})
    return case_obs, reqlog


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
def run_gqldepth_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the depth test plan object (see gqldepth_spec): a dict with
        `cases` (each {label, type, depth}). The harness builds + sends the queries
        (read-only) and evaluates every scenario. Whatever the agent fails to emit
        scores as 'missing'. generate may raise; recorded per-endpoint.
    """
    cfgs = endpoint_cfgs()
    all_cases = []
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        case_obs, reqlog = _exec_plan(cfg, plan)
        observed = gqldepth_spec.evaluate(case_obs)

        scenarios = []
        for label in gqldepth_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = gqldepth_spec.correct(label, tok)
            scenarios.append({"endpoint": cfg["endpoint"], "scenario": label,
                              "ideal": gqldepth_spec.ideal_for(label),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"endpoint": cfg["endpoint"], "max_depth": cfg["max_depth"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(cfg["endpoint"]).strip("/").replace("/", "-") or "graphql",
            item_label=f"POST {cfg['endpoint']} (max_depth={cfg['max_depth']})",
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
           "depth_enforcement_pct": rate,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "depth_enforcement_pct": rate, "scenarios_total": total})

    everos_note(agent, f"graphql-depth run: enforcement={rate}% "
                       f"over {len(cfgs)} endpoints ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    GraphQL Depth Enforcement Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "validate-graphql-depth-limits" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "depth_enforcement_pct"),
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
