"""Shared, deterministic plumbing for the four versioning-behavior agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint catalogue + documented versioning contract + per-version
    response schemas from data/validate-api-versioning-behavior/versioning_spec.json
  - build the compact per-endpoint brief handed to the agent
  - execute whatever plan the agent emitted with READ-ONLY GET requests to the LOCAL
    target only (sandbox + host + method guards), capturing per case the status, the
    JSON body, and the Deprecation response header
  - run the real ajv v8 validator (tools/ajv/ajv_validate.mjs) against the documented
    per-version schema whenever a version answers 200 with a JSON body
  - evaluate every scenario (shared versioning_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified: GET only, no body, no mutation.

The framework-specific part — turning one endpoint's brief into the versioning test
plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
TODAY = os.environ.get("FORGE_TODAY") or datetime.now(timezone.utc).date().isoformat()
AJV = WORKSPACE / "tools" / "ajv" / "ajv_validate.mjs"
SPEC_PATH = WORKSPACE / "data" / "validate-api-versioning-behavior" / "versioning_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import versioning_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host + method guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def endpoint_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for e in spec["endpoints"]:
        out.append({
            "endpoint": e["endpoint"],
            "list_field": e["list_field"],
            "schema_diff_field": e.get("schema_diff_field", spec.get("schema_diff_field",
                                                                     versioning_spec.SCHEMA_DIFF_FIELD)),
            "supported_versions": spec.get("supported_versions", versioning_spec.SUPPORTED_VERSIONS),
            "unsupported_versions": spec.get("unsupported_versions", versioning_spec.UNSUPPORTED_VERSIONS),
            "documented_deprecation_date": spec.get("documented_deprecation_date",
                                                    versioning_spec.DOCUMENTED_DEPRECATION_DATE),
        })
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [e for e in out if e["endpoint"] in wanted or e["list_field"] in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous versioning contract handed to the LLM."""
    lines = [
        f"endpoint_path: {cfg['endpoint']}      # the unversioned resource path",
        f"list_field: {cfg['list_field']}   # response collection items live under this key",
        f"schema_diff_field: {cfg['schema_diff_field']}   "
        "# present in the v2 response schema, absent from the v1 response schema",
        "supported_versions:",
    ]
    for v in cfg["supported_versions"]:
        lines.append(f"  - version={v['version']} status={v['status']}")
    lines.append(f"unsupported_versions: {[v for v in cfg['unsupported_versions']]}")
    lines.append(f"documented_deprecation_date: {cfg['documented_deprecation_date']}   "
                 "# the future ISO-8601 date the deprecated version's Deprecation header should carry")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTTP (read-only GET) + plan execution
# --------------------------------------------------------------------------- #
def _get(path: str, _retries: int = 2):
    """Read-only GET. Returns (status, json_body_or_None, deprecation_header_or_None).
    Small retry on transient connection failure (status None); HTTP error codes are
    real responses and returned as-is with their headers."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method="GET")  # GET only — never mutate the target
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                dep = r.headers.get("Deprecation")
                try:
                    return r.getcode(), json.loads(body), dep
                except Exception:  # noqa
                    return r.getcode(), None, dep
        except urllib.error.HTTPError as e:
            dep = e.headers.get("Deprecation") if e.headers else None
            try:
                parsed = json.loads(e.read()) if e.fp else None
            except Exception:  # noqa
                parsed = None
            return e.code, parsed, dep  # a real response from the API
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return None, None, None


def _ajv_validate(schema, data):
    """Run the real ajv v8 validator. Returns error_count (0 = conforms)."""
    payload = json.dumps({"schema": schema, "data": data, "draft": "draft-07"}).encode()
    try:
        proc = subprocess.run(["node", str(AJV)], input=payload, capture_output=True, timeout=30)
        out = json.loads(proc.stdout.decode() or "{}")
        return out.get("error_count", 1)
    except Exception:  # noqa
        return 1


def _exec_plan(cfg: dict, plan: dict):
    """Execute the AGENT's plan (read-only). Tolerant of missing/malformed keys —
    whatever the agent omits simply does not get sent and scores as 'missing'."""
    case_obs, reqlog = {}, []
    lf, sdf = cfg["list_field"], cfg["schema_diff_field"]

    for case in plan.get("cases", []) if isinstance(plan, dict) else []:
        if not isinstance(case, dict) or "label" not in case:
            continue
        path = case.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        status, body, dep = _get(path)

        schema_documented = False
        ajv_errors = None
        version = case.get("version")
        if status == 200 and isinstance(body, dict) and version in ("v1", "v2"):
            schema = versioning_spec.schema_for(version, lf, sdf)
            schema_documented = True
            ajv_errors = _ajv_validate(schema, body)

        rec = {"status": status, "body": body, "deprecation": dep,
               "schema_documented": schema_documented, "ajv_error_count": ajv_errors}
        case_obs[case["label"]] = rec
        reqlog.append({"label": case["label"], "path": path,
                       "version": version, "version_status": case.get("version_status"),
                       "status": status, "deprecation": dep,
                       "ajv_error_count": ajv_errors})

    return case_obs, reqlog


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = (cfg.get("everos_base_url") or "http://127.0.0.1:8000").rstrip("/")
    payload = {"session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
               "project_id": cfg.get("project_id", "agent-foundry"),
               "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                             "content": text, "timestamp": int(time.time())}]}
    try:
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            b = json.dumps(payload if ep.endswith("add") else
                           {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            urllib.request.urlopen(urllib.request.Request(
                base + ep, data=b, headers={"Content-Type": "application/json"}), timeout=5).read()
    except Exception:  # noqa  -- EverOS optional; never block a run
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_versioning_test(agent: str, generate, usage=None) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the versioning test plan object (see versioning_spec):
        a dict with `cases` (each {label, path, version, version_status}). The harness
        executes the AGENT's planned GETs (read-only), captures status + body +
        Deprecation header, runs ajv against the documented per-version schema on any
        200, and evaluates every scenario. Whatever the agent fails to emit scores as
        'missing'. generate may raise; recorded per-endpoint.
    usage() -> optional callable returning {"prompt_tokens", "completion_tokens",
        "total_tokens"} accumulated by the framework, used by the judge's efficiency
        discriminator. Best-effort; absent/zero when the framework does not expose it.
    """
    t0 = time.monotonic()
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
        observed = versioning_spec.evaluate(case_obs, cfg["schema_diff_field"], TODAY)

        scenarios = []
        for label in versioning_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = versioning_spec.correct(label, tok)
            scenarios.append({"endpoint": cfg["endpoint"], "scenario": label,
                              "ideal": versioning_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"endpoint": cfg["endpoint"], "list_field": cfg["list_field"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * correct / total, 2) if total else 0.0
    elapsed = round(time.monotonic() - t0, 3)
    tok = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if callable(usage):
        try:
            u = usage() or {}
            for k in tok:
                tok[k] = int(u.get(k, 0) or 0)
        except Exception:  # noqa
            pass
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL, "today": TODAY,
           "version_routing_accuracy_pct": rate,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "elapsed_seconds": elapsed, "tokens": tok,
           "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "version_routing_accuracy_pct": rate, "scenarios_total": total,
        "elapsed_seconds": elapsed, "tokens_total": tok["total_tokens"]})

    everos_note(agent, f"versioning-behavior run: accuracy={rate}% "
                       f"over {len(cfgs)} endpoints ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the
    headline Version Routing Accuracy; the judge later overwrites it with
    fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "validate-api-versioning-behavior" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("headline_metric", "version_routing_accuracy_pct"),
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
