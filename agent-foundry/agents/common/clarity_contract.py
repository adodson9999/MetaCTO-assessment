"""Shared, deterministic plumbing for the four error-message-clarity agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the operation list (+ documented error codes + per-code trigger + metadata)
    from data/clarity/openapi.json
  - perform one login to obtain a real bearer token (for auth:"valid")
  - send a real HTTP request to the LOCAL target only (sandbox + host guard),
    capturing both the status code AND the raw response body
  - run the deterministic clarity assertions (clarity_spec.clarity_verdict) on the
    body — identical for every agent
  - drive the per-operation loop, record every case, emit the result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The framework-specific part — turning one operation brief into the per-code request
descriptors via the backend LLM — is injected as `generate(op) -> dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
LOGIN_USER = os.environ.get("FORGE_LOGIN_USER", "emilys")
LOGIN_PASS = os.environ.get("FORGE_LOGIN_PASS", "emilyspass")
MAX_RETRIES = int(os.environ.get("FORGE_SEND_RETRIES", "2"))

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import clarity_spec  # noqa: E402

# reuse the validate-workflow's robust JSON extractor (same workspace module)
from contract import extract_json  # noqa: E402


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


# --------------------------------------------------------------------------- #
# Spec loading
# --------------------------------------------------------------------------- #
def load_operations() -> list[dict]:
    spec = json.loads((WORKSPACE / "data" / "clarity" / "openapi.json").read_text())
    out = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            triggers_raw = op.get("x-error-triggers", {})
            triggers = {int(c): t for c, t in triggers_raw.items()}
            codes = sorted(triggers)
            media = (op.get("requestBody", {}).get("content", {})
                     .get("application/json", {}))
            schema = media.get("schema", {})
            out.append({
                "slug": op.get("operationId", f"{method}_{path}"),
                "method": method.upper(),
                "path": path,
                "auth_required": bool(op.get("security")),
                "required": schema.get("required", []),
                "properties": schema.get("properties", {}),
                "example": media.get("example"),
                "is_hook": path.startswith("/http/"),
                "bad_query": op.get("x-bad-query"),
                "triggers": triggers,
                "codes": codes,
            })
    only = os.environ.get("FORGE_ONLY_SLUGS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [o for o in out if o["slug"] in wanted]
    return out


def operation_brief(op: dict) -> str:
    """Compact, unambiguous operation description handed to the LLM. Each
    documented error code is paired with exactly one trigger name."""
    pairs = [f"{c}:{op['triggers'][c]}" for c in op["codes"]]
    lines = [f"operationId: {op['slug']}",
             f"method: {op['method']}",
             f"path: {op['path']}",
             f"auth_required: {str(op['auth_required']).lower()}",
             f"is_http_status_hook: {str(op['is_hook']).lower()}",
             f"required_body_fields: {op['required']}",
             f"bad_query_suffix: {json.dumps(op.get('bad_query'))}",
             f"documented_error_codes_with_triggers: [{', '.join(pairs)}]"]
    if op.get("example") is not None:
        lines.append(f"valid_example_body: {json.dumps(op['example'])}")
    else:
        lines.append("valid_example_body: null")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Auth + HTTP
# --------------------------------------------------------------------------- #
def login_token() -> str | None:
    body = json.dumps({"username": LOGIN_USER, "password": LOGIN_PASS}).encode()
    req = urllib.request.Request(TARGET_BASE_URL + "/auth/login", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("accessToken")
    except Exception:  # noqa
        return None


def _headers(auth: str, token: str | None) -> dict:
    h = {"Content-Type": "application/json"}
    if auth == "valid" and token:
        h["Authorization"] = f"Bearer {token}"
    elif auth == "malformed":
        # 3-segment JWT-shaped but undecodable token: triggers DummyJSON's
        # parse-level 500 with a plain-English body (verified live).
        h["Authorization"] = "Bearer xx.yy.zz"
    return h


def send(desc: dict, token: str | None):
    """Send one descriptor; return (status_code, raw_body_text). Bounded retry on
    transport faults (status -1) so a transient flake is not scored as a miss."""
    method = (desc.get("method") or "GET").upper()
    path = desc.get("path") or "/"
    url = TARGET_BASE_URL + (path if path.startswith("/") else "/" + path)
    _assert_local_target(url)
    body = desc.get("body")
    data = json.dumps(body).encode() if body is not None else None
    last = (-1, "")
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=_headers(desc.get("auth", "none"), token))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                b = e.read().decode("utf-8", "replace")
            except Exception:  # noqa
                b = ""
            return e.code, b  # a real HTTP error response is a valid observation
        except Exception:  # noqa
            last = (-1, "")
            if attempt < MAX_RETRIES:
                time.sleep(0.4 * (attempt + 1))
                continue
    return last


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
def run_clarity_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(op: dict) -> {"requests": [descriptor, ...]} mapping each documented
    error code to a request descriptor that triggers it. The harness sends each
    descriptor, captures the real body, and runs the identical clarity assertions.
    A documented code the agent omitted is recorded covered=False (counts against
    the pass rate and scores 0 for fidelity). generate may raise; recorded as a
    per-op generation error.
    """
    ops = load_operations()
    token = login_token()
    cases = []
    total = passed = msg_yes = code_yes = leaks = p1 = 0

    for op in ops:
        _op_case_start = len(cases)
        try:
            out = generate(op) or {}
            gen_error = None
        except Exception as e:  # noqa
            out, gen_error = {}, f"{type(e).__name__}: {e}"
        by_code: dict[int, dict] = {}
        for d in clarity_spec.iter_agent_requests(out):
            by_code.setdefault(d["code"], d)  # first descriptor per code wins

        for code in op["codes"]:
            total += 1
            desc = by_code.get(code)
            if desc is None:
                cases.append({"slug": op["slug"], "method": op["method"], "path": op["path"],
                              "documented_code": code, "trigger": op["triggers"][code],
                              "covered": False, "sent": None, "actual_code": None,
                              "body": None, "verdict": None, "passed": False, "error": gen_error})
                continue
            actual, body = send(desc, token)
            verdict = clarity_spec.clarity_verdict(body)
            passed += int(verdict["passed"])
            msg_yes += int(verdict["message_present"])
            code_yes += int(verdict["code_present"])
            if verdict["sensitive_found"]:
                leaks += 1
                p1 += 1
            cases.append({"slug": op["slug"], "method": op["method"], "path": op["path"],
                          "documented_code": code, "trigger": op["triggers"][code],
                          "covered": True, "sent": desc, "actual_code": actual,
                          "body": body, "verdict": verdict, "passed": verdict["passed"],
                          "error": None})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=op["slug"],
            item_label=f"{op['method']} {op['path']}",
            step_results=[
                {
                    "assertion_result": "PASS" if c.get("passed") else "FAIL",
                    "assertion_detail": (
                        f"documented_code={c.get('documented_code')} "
                        f"trigger={c.get('trigger')} covered={c.get('covered')} "
                        f"actual_code={c.get('actual_code')}"
                    ),
                    **c,
                }
                for c in cases[_op_case_start:]
            ],
        )

    pass_rate = round(100.0 * passed / total, 2) if total else 0.0
    covered = sum(1 for c in cases if c["covered"])

    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "error_clarity_pass_rate_pct": pass_rate,
           "documented_error_cases": total, "passed_cases": passed,
           "message_field_present": msg_yes, "code_field_present": code_yes,
           "responses_with_internal_leaks": leaks, "p1_security_defects": p1,
           "covered_cases": covered, "cases": cases}
    run_dir = WORKSPACE / "results" / "clarity" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, pass_rate, str(cases_path),
         extra={"error_clarity_pass_rate_pct": pass_rate,
                "documented_error_cases": total, "passed_cases": passed,
                "message_field_present": msg_yes, "code_field_present": code_yes,
                "p1_security_defects": p1, "covered_cases": covered})
    everos_note(agent, f"error-clarity run: pass_rate={pass_rate}% passed={passed}/{total} "
                       f"msg={msg_yes} code={code_yes} p1_leaks={p1} covered={covered} "
                       f"over {len(ops)} operations")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/clarity/runs/<run>/<agent>.json. metric_value here is the
    headline Error Clarity Pass Rate; the judge later overwrites metric_value with
    Error-Clarity Test Fidelity."""
    metric = {}
    mp = WORKSPACE / "judge" / "clarity" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "clarity" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("headline_metric", "error_clarity_pass_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))
