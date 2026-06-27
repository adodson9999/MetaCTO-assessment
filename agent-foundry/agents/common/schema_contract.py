"""Shared, deterministic plumbing for the four response-schema-validation agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint list (+ documented response keys, schema-presence) from
    data/openapi.json (the shared, untouched spec)
  - perform one login to obtain a real bearer token (for auth:"valid")
  - send ONE valid request per endpoint to the LOCAL target only (sandbox guard)
  - deterministically look up the documented response schema for the real status
  - run the real ajv v8 validator (tools/ajv/ajv_validate.mjs) when a schema exists
  - record every response, compute the headline conformance rate, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The framework-specific part — turning one endpoint brief into the valid request
descriptor + documented-schema map via the backend LLM — is injected as
`generate(op) -> dict`.
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
LOGIN_USER = os.environ.get("FORGE_LOGIN_USER", "emilys")
LOGIN_PASS = os.environ.get("FORGE_LOGIN_PASS", "emilyspass")
MAX_ENDPOINTS = int(os.environ.get("FORGE_MAX_ENDPOINTS", "0"))  # 0 = all
AJV = WORKSPACE / "tools" / "ajv" / "ajv_validate.mjs"
EXISTING_ID = "1"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import schema_spec  # noqa: E402
from contract import extract_json  # noqa: E402  -- reuse the robust JSON extractor


# --------------------------------------------------------------------------- #
# Sandbox + host guards
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


def _stage_schema_op(agent: str, op: dict, op_cases: list[dict]) -> None:
    """Stage the single case this op produced (covered or not) for G1b orchestration."""
    _write_staging_findings(
        agent=agent,
        item_id=op["slug"],
        item_label=f"{op['method']} {op['path']}",
        step_results=[
            {
                "assertion_result": (
                    "PASS" if c.get("covered") and c.get("schema_claim_correct")
                    and c.get("conformance") != "fail" else "FAIL"
                ),
                "assertion_detail": (
                    f"covered={c.get('covered')} actual_code={c.get('actual_code')} "
                    f"matched_key={c.get('matched_response_key')} "
                    f"documented_schema={c.get('documented_schema')} "
                    f"conformance={c.get('conformance')}"
                ),
                **c,
            }
            for c in op_cases
        ],
    )


# --------------------------------------------------------------------------- #
# Spec loading
# --------------------------------------------------------------------------- #
def _classify(code: int) -> str:
    if 200 <= code < 300:
        return "2xx"
    if 400 <= code < 500:
        return "4xx"
    if 500 <= code < 600:
        return "5xx"
    return f"other_{code}"


def load_operations() -> list[dict]:
    spec = json.loads((WORKSPACE / "data" / "openapi.json").read_text())
    out = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            responses = op.get("responses", {})
            codes = list(responses.keys())  # documented response keys, as strings
            schema_by_code = {
                c: bool(responses[c].get("content", {})
                        .get("application/json", {}).get("schema"))
                for c in codes
            }
            media = (op.get("requestBody", {}).get("content", {})
                     .get("application/json", {}))
            schema = media.get("schema", {})
            out.append({
                "slug": op.get("operationId", f"{method}_{path}"),
                "method": method.upper(),
                "path": path,
                "auth_required": bool(op.get("security")),
                "required": schema.get("required", []),
                "example": media.get("example"),
                "codes": codes,
                "schema_by_code": schema_by_code,
            })
    only = os.environ.get("FORGE_ONLY_SLUGS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [o for o in out if o["slug"] in wanted]
    if MAX_ENDPOINTS > 0:
        out = out[:MAX_ENDPOINTS]
    return out, spec


def endpoint_brief(op: dict) -> str:
    """Compact, unambiguous endpoint description handed to the LLM."""
    schema_lines = ", ".join(f'{c}: has_json_schema={str(op["schema_by_code"][c]).lower()}'
                             for c in op["codes"])
    lines = [f"operationId: {op['slug']}",
             f"method: {op['method']}",
             f"path: {op['path']}",
             f"auth_required: {str(op['auth_required']).lower()}",
             f"required_body_fields: {op['required']}",
             f"documented_response_status_keys: {op['codes']}",
             f"response_schema_documented_per_key: {{{schema_lines}}}"]
    if op.get("example") is not None:
        lines.append(f"valid_example_body: {json.dumps(op['example'])}")
    else:
        lines.append("valid_example_body: null")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Auth + HTTP + validation
# --------------------------------------------------------------------------- #
def login_token() -> str | None:
    body = json.dumps({"username": LOGIN_USER, "password": LOGIN_PASS}).encode()
    req = urllib.request.Request(TARGET_BASE_URL + "/auth/login", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("accessToken")
    except Exception:  # noqa: BLE001
        return None


def _headers(auth: str, token: str | None) -> dict:
    h = {"Content-Type": "application/json"}
    if auth == "valid" and token:
        h["Authorization"] = f"Bearer {token}"
    return h


def send(desc: dict, token: str | None):
    method = (desc.get("method") or "GET").upper()
    path = desc.get("path") or "/"
    url = TARGET_BASE_URL + (path if path.startswith("/") else "/" + path)
    _assert_local_target(url)
    body = desc.get("body")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=_headers(desc.get("auth", "none"), token))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode(), _parse_body(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, _parse_body(e.read().decode("utf-8", "replace") if e.fp else "")
    except Exception as e:  # noqa: BLE001
        return -1, {"_transport_error": str(e)}


def _parse_body(raw: str):
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return raw[:500] if raw else None


def lookup_response_schema(spec: dict, path: str, method: str, status_code: int):
    op = spec.get("paths", {}).get(path, {}).get(method.lower(), {})
    responses = op.get("responses", {})
    range_key = {"2xx": "2xx", "4xx": "400", "5xx": "5xx"}.get(_classify(status_code))
    for key in (str(status_code), range_key, "default"):
        if key and key in responses:
            schema = (responses[key].get("content", {})
                      .get("application/json", {}).get("schema"))
            return schema, key
    return None, None


def ajv_validate(schema, data):
    """Run the real ajv v8 validator. Returns (valid, error_count, errors, fields)."""
    payload = json.dumps({"schema": schema, "data": data, "draft": "draft-07"}).encode()
    proc = subprocess.run(["node", str(AJV)], input=payload, capture_output=True, timeout=30)
    out = json.loads(proc.stdout.decode() or "{}")
    return out.get("valid"), out.get("error_count", 0), out.get("errors", []), out.get("fields_validated", 0)


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
    except Exception:  # noqa: BLE001  -- EverOS optional; never block a run
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_schema_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(op: dict) -> {"request": {...}, "documented_response_schemas": [...]}.
    The harness sends the agent's ONE valid request to the local target, records the
    real status + body, deterministically looks up the documented response schema for
    that status, runs ajv v8 when a schema exists, and records the real conformance.
    An endpoint the agent failed to produce a usable request for is recorded
    covered=False (scores 0 for fidelity). generate may raise; recorded per-endpoint.
    """
    ops, spec = load_operations()
    token = login_token()
    cases = []
    validated = conformant = 0

    for op in ops:
        _op_case_start = len(cases)
        try:
            out = generate(op) or {}
            gen_error = None
        except Exception as e:  # noqa: BLE001
            out, gen_error = {}, f"{type(e).__name__}: {e}"

        req = schema_spec.normalize_request(out)
        claim_map = {e["code"]: e["has_json_schema"]
                     for e in schema_spec.normalize_schema_map(out)}
        covered = bool(req.get("method") and req.get("path"))

        if not covered:
            cases.append({"slug": op["slug"], "method": op["method"], "path": op["path"],
                          "covered": False, "sent": req, "actual_code": None,
                          "actual_class": None, "matched_response_key": None,
                          "documented_schema": False, "agent_claimed_has_schema": None,
                          "schema_claim_correct": False, "fields_validated": 0,
                          "validation_error_count": 0, "conformance": None,
                          "error": gen_error})
            _stage_schema_op(agent, op, cases[_op_case_start:])
            continue

        actual_code, body = send(req, token)
        schema, matched_key = lookup_response_schema(spec, op["path"], op["method"], actual_code)
        documented = schema is not None

        if documented:
            _valid, err_count, errors, fields = ajv_validate(schema, body)
            validated += 1
            conformance = "pass" if err_count == 0 else "fail"
            conformant += 1 if err_count == 0 else 0
        else:
            err_count, errors, fields = 0, [], 0
            conformance = "n/a"

        # did the agent correctly report whether a schema is documented for the
        # response key that actually matched? (gold truth = `documented`)
        agent_claim = claim_map.get(matched_key) if matched_key is not None else None
        claim_correct = (bool(agent_claim) == documented) if agent_claim is not None else (not documented and matched_key is None)

        cases.append({
            "slug": op["slug"], "method": op["method"], "path": op["path"],
            "covered": True, "sent": req, "actual_code": actual_code,
            "actual_class": _classify(actual_code) if actual_code != -1 else None,
            "matched_response_key": matched_key, "documented_schema": documented,
            "agent_claimed_has_schema": agent_claim, "schema_claim_correct": claim_correct,
            "fields_validated": fields, "validation_error_count": err_count,
            "validation_errors": errors, "conformance": conformance, "error": None,
        })

        # G1 staging write — write per-item findings for G1b orchestration
        _stage_schema_op(agent, op, cases[_op_case_start:])

    rate = round(100.0 * conformant / validated, 2) if validated else None
    covered_n = sum(1 for c in cases if c["covered"])

    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "schema_conformance_rate_pct": rate,
           "responses_validated": validated, "responses_conformant": conformant,
           "endpoints_total": len(ops), "endpoints_covered": covered_n,
           "endpoints_without_documented_response_schema":
               sum(1 for c in cases if c["covered"] and not c["documented_schema"]),
           "cases": cases}
    run_dir = WORKSPACE / "results" / "schema" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "schema_conformance_rate_pct": rate, "responses_validated": validated,
        "responses_conformant": conformant, "endpoints_covered": covered_n,
        "endpoints_total": len(ops)})
    rate_str = "N/A" if rate is None else f"{rate}%"
    everos_note(agent, f"schema-validation run: conformance_rate={rate_str} "
                       f"validated={validated} covered={covered_n}/{len(ops)} endpoints")
    return raw


def emit(agent: str, metric_value, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/schema/runs/<run>/<agent>.json. metric_value here is the
    headline conformance rate (None/N/A under the current spec); the judge later
    overwrites metric_value with Response-Validation Fidelity."""
    metric = {}
    mp = WORKSPACE / "judge" / "schema" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "schema" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("headline_metric", "schema_conformance_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))
