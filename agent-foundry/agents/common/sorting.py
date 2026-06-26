"""Shared, deterministic plumbing for the four sorting-behavior agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the resource catalogue + documented sort contract from
    data/verify-sorting-behavior/sorting_spec.json
  - build the compact per-collection brief handed to the agent
  - stand up an ISOLATED, loopback-only reference resource (sortserver.py), seed it
    with the AGENT's emitted seed records, and execute the agent's sort plan against
    it with READ-ONLY GET requests (sandbox + host + method guards)
  - evaluate every scenario (shared sorting_spec.evaluate), compute the headline
    Sorting Accuracy Rate, record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is NOT used or touched by this task: it cannot be seeded read-only and has
no created_at field, so the idealized seed-and-sort contract runs against the
in-process reference resource instead. The reference resource serves GET only — no
plan an agent emits can mutate it.

The framework-specific part — turning the resource brief into the sort test plan via
the backend LLM — is injected as `generate(cfg) -> plan dict`.
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
SPEC_PATH = WORKSPACE / "data" / "verify-sorting-behavior" / "sorting_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import sorting_spec  # noqa: E402
from sortserver import ReferenceServer  # noqa: E402


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
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    if SPEC_PATH.exists():
        return json.loads(SPEC_PATH.read_text())
    # Self-contained fallback so a framework run never hard-depends on build_gold.
    return {
        "resource_path": "/resources",
        "list_field": "resources",
        "name_field": "name",
        "timestamp_field": "created_at",
        "sortable_fields": sorting_spec.SORTABLE_FIELDS,
        "valid_orders": sorting_spec.VALID_ORDERS,
    }


def resource_cfg() -> dict:
    spec = load_spec()
    return {
        "resource_path": spec.get("resource_path", "/resources"),
        "list_field": spec.get("list_field", "resources"),
        "name_field": spec.get("name_field", "name"),
        "timestamp_field": spec.get("timestamp_field", "created_at"),
        "sortable_fields": spec.get("sortable_fields", sorting_spec.SORTABLE_FIELDS),
        "valid_orders": spec.get("valid_orders", sorting_spec.VALID_ORDERS),
    }


def resource_brief(cfg: dict) -> str:
    """Compact, unambiguous sort contract handed to the LLM."""
    return "\n".join([
        f"resource_path: {cfg['resource_path']}      # the list route under test",
        f"list_field: {cfg['list_field']}   # response items live under this key",
        f"name_field: {cfg['name_field']}        # each record's sortable name is under this key",
        f"timestamp_field: {cfg['timestamp_field']}   # each record's creation instant is under this key",
        f"sortable_fields: {', '.join(cfg['sortable_fields'])}   # the only fields the sort param may select",
        "sort_contract: the 'sort' query parameter selects one sortable field; the 'order' "
        f"query parameter is one of {', '.join(cfg['valid_orders'])}; an unknown sort field or an "
        "out-of-enum order value each returns 400.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (read-only GET) + plan execution against the seeded reference resource
# --------------------------------------------------------------------------- #
def _get(base_url: str, path: str, params: dict, _retries: int = 2):
    """Read-only GET with a small retry on transient connection failure (status -1).
    HTTP error codes (e.g. 400) are real responses and are returned as-is."""
    qs = urllib.parse.urlencode(params)
    url = f"{base_url}{path}?{qs}" if qs else f"{base_url}{path}"
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
            try:
                parsed = json.loads(e.read())
            except Exception:  # noqa
                parsed = None
            return e.code, parsed  # a real response from the API, not a transient failure
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            last = -1
            if attempt < _retries:
                time.sleep(0.3 * (attempt + 1))
    return last, None


def _seed_meta(plan: dict) -> dict:
    seed = plan.get("seed") if isinstance(plan, dict) else None
    seed = seed if isinstance(seed, list) else []
    names = [r.get("name") for r in seed if isinstance(r, dict)]
    distinct = len({n for n in names if isinstance(n, str)})
    return {"emitted": len(seed), "distinct": distinct}


def _exec_plan(base_url: str, cfg: dict, plan: dict):
    """Execute the AGENT's plan (read-only) against the seeded reference resource.
    Tolerant of missing/malformed keys — whatever the agent omits simply does not
    get sent and scores as 'missing'."""
    case_obs, reqlog = {}, []
    lf = cfg["list_field"]
    path = cfg["resource_path"]

    for case in plan.get("sort_cases", []) if isinstance(plan, dict) else []:
        if not isinstance(case, dict) or "label" not in case:
            continue
        params = case.get("params") if isinstance(case.get("params"), dict) else {}
        params = {k: v for k, v in params.items() if v is not None}
        status, body = _get(base_url, path, params)
        records, message = None, None
        if status == 200 and isinstance(body, dict):
            items = body.get(lf)
            records = items if isinstance(items, list) else None
        elif isinstance(body, dict):
            message = body.get("message")
        case_obs[case["label"]] = {"status": status, "records": records, "message": message}
        reqlog.append({"label": case["label"], "type": case.get("type"),
                       "path": path, "params": params, "status": status,
                       "returned_count": (len(records) if records is not None else None)})

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
def run_sorting_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the sort test plan object (see sorting_spec): a dict with
        `seed` (20 {name, created_at} objects) and `sort_cases` (six {label, type,
        params, expect_status, ...} objects). The harness seeds an isolated reference
        resource with the agent's seed, executes the agent's planned requests
        (read-only), and evaluates every scenario. Whatever the agent fails to emit
        scores as 'missing'. generate may raise; recorded.
    """
    cfg = resource_cfg()
    try:
        plan = generate(cfg) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    seed = plan.get("seed") if isinstance(plan.get("seed"), list) else []
    seed_meta = _seed_meta(plan)

    with ReferenceServer(seed, cfg["name_field"], cfg["timestamp_field"]) as server:
        case_obs, reqlog = _exec_plan(server.base_url, cfg, plan)
        target = server.base_url

    observed = sorting_spec.evaluate(case_obs, seed_meta,
                                     cfg["name_field"], cfg["timestamp_field"])

    scenarios = []
    total = correct = 0
    ordering_total = ordering_correct = 0
    for label in sorting_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = sorting_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": sorting_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0
        if label in sorting_spec.ORDERING_SCENARIOS:
            ordering_total += 1
            ordering_correct += 1 if ok else 0

    # Headline metric: Sorting Accuracy Rate = sort requests with all adjacent pairs
    # correctly ordered / total sort test cases * 100.
    sorting_accuracy = round(100.0 * ordering_correct / ordering_total, 2) if ordering_total else 0.0
    scenario_accuracy = round(100.0 * correct / total, 2) if total else 0.0

    raw = {"agent": agent, "run_id": RUN_ID, "target": target,
           "sorting_accuracy_rate_pct": sorting_accuracy,
           "sort_cases_total": ordering_total, "sort_cases_in_order": ordering_correct,
           "scenario_accuracy_pct": scenario_accuracy,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "seed": {"emitted": seed_meta["emitted"], "distinct": seed_meta["distinct"]},
           "emitted_plan": plan, "request_log": reqlog,
           "scenarios": scenarios, "error": gen_error}

    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, sorting_accuracy, str(cases_path), extra={
        "sorting_accuracy_rate_pct": sorting_accuracy,
        "sort_cases_total": ordering_total})

    everos_note(agent, f"sorting-behavior run: sorting_accuracy={sorting_accuracy}% "
                       f"over {ordering_total} sort cases, scenario_accuracy={scenario_accuracy}%")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Sorting Accuracy Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "verify-sorting-behavior" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "sorting_accuracy_rate_pct"),
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
