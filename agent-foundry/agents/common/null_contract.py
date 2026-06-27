"""Shared, deterministic plumbing for the four null-and-empty-fields testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint list (+ required/optional split + example) from data/openapi.json
  - build the compact per-endpoint brief handed to the agent
  - send a real HTTP request to the LOCAL target only (sandbox + host guard, bounded retry)
  - classify status codes; compute the idealized contract token (null_spec.ideal_token)
  - iterate whatever the agent emitted, record every case, emit the result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is started air-gapped (MONGODB_URI empty) so add/update routes simulate a
response and do NOT persist — sending POST/PUT/PATCH does not mutate stored data.

The framework-specific part — turning one endpoint's schema into the six-key matrix
via the backend LLM — is injected as `generate(endpoint) -> dict`.
"""
from __future__ import annotations

import json
import os
import re
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
MAX_ENDPOINTS = int(os.environ.get("FORGE_MAX_ENDPOINTS", "0"))  # 0 => all
EXISTING_ID = "1"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import null_spec  # noqa: E402


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
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_endpoints() -> list[dict]:
    spec = json.loads((WORKSPACE / "data" / "openapi.json").read_text())
    out = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            media = op["requestBody"]["content"]["application/json"]
            schema = media["schema"]
            props = schema.get("properties", {})
            required = schema.get("required", [])
            out.append({
                "slug": op["operationId"],
                "method": method.upper(),
                "path": path,
                "properties": props,
                "required": required,
                "optional": null_spec.optional_fields(props, required),
                "example": media.get("example", {}),
            })
    only = os.environ.get("FORGE_ONLY_SLUGS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [ep for ep in out if ep["slug"] in wanted]
    if MAX_ENDPOINTS > 0:
        out = out[:MAX_ENDPOINTS]
    return out


def endpoint_brief(ep: dict) -> str:
    """Compact, unambiguous schema description handed to the LLM."""
    lines = [f"method: {ep['method']}", f"path: {ep['path']}", "fields:"]
    for k, v in ep["properties"].items():
        req = "required" if k in ep["required"] else "optional"
        lines.append(f"  - {k} (type={v.get('type', 'any')}, {req})")
    lines.append(f"required (spec order): {ep['required']}")
    lines.append(f"optional (spec order): {ep['optional']}")
    lines.append(f"known_valid_example: {json.dumps(ep['example'])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTTP + classification (bounded retry on transient connection failure)
# --------------------------------------------------------------------------- #
def send(method: str, path: str, body, _retries: int = 2) -> int:
    url = TARGET_BASE_URL + path.replace("{id}", EXISTING_ID)
    _assert_local_target(url)
    data = json.dumps(body).encode()
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.getcode()
        except urllib.error.HTTPError as e:
            return e.code  # a real response from the API, not a transient failure
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1


def classify(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "2xx"
    if code == 400:
        return "400"
    return f"other_{code}"


# --------------------------------------------------------------------------- #
# LLM-output JSON extraction (deterministic, no model)
# --------------------------------------------------------------------------- #
def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
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
def run_null_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(endpoint: dict) -> the six-key output object (see null_spec). The harness
    iterates every labeled body the agent emitted, sends each to the local target, and
    records the real response and the idealized contract token. Whatever the agent fails
    to emit simply does not appear — the judge scores coverage against the gold case set.
    generate may raise; recorded as a per-endpoint generation error, not a crash.
    """
    endpoints = load_endpoints()
    cases = []
    total = correct = 0
    req_invalid = req_invalid_400 = 0
    opt_null = opt_null_match = 0

    for ep in endpoints:
        _ep_case_start = len(cases)
        props = ep["properties"]
        try:
            out = generate(ep) or {}
            gen_error = None
        except Exception as e:  # noqa
            out, gen_error = {}, f"{type(e).__name__}: {e}"

        produced = False
        for category, label, field, state, body in null_spec.iter_cases(out):
            produced = True
            if not isinstance(body, (dict, list)):
                code, ac = None, "none"
            else:
                code = send(ep["method"], ep["path"], body)
                ac = classify(code)
            ideal = null_spec.ideal_token(category, field, state, props)
            ok = ac == ideal
            cases.append({"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
                          "category": category, "label": label, "field": field, "state": state,
                          "ideal_token": ideal, "actual_code": code, "actual_class": ac,
                          "api_correct": ok, "sent_body": body, "error": None})
            total += 1
            correct += 1 if ok else 0
            if category in null_spec.REQUIRED_INVALID_CATEGORIES:
                req_invalid += 1
                if ac == "400":
                    req_invalid_400 += 1
            if category == "optional_state" and state == "json_null":
                opt_null += 1
                if ok:
                    opt_null_match += 1
        if not produced:
            cases.append({"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
                          "category": "_none_", "label": "", "field": None, "state": None,
                          "ideal_token": None, "actual_code": None, "actual_class": "none",
                          "api_correct": False, "sent_body": None,
                          "error": gen_error or "no payloads produced"})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=ep["slug"],
            item_label=f"{ep['method']} {ep['path']}",
            step_results=[
                {
                    "assertion_result": "PASS" if c.get("api_correct") else "FAIL",
                    "assertion_detail": (
                        f"category={c.get('category')} field={c.get('field')} "
                        f"state={c.get('state')} ideal={c.get('ideal_token')} "
                        f"actual_class={c.get('actual_class')}"
                    ),
                    **c,
                }
                for c in cases[_ep_case_start:]
            ],
        )

    def pct(n, d):
        return round(100.0 * n / d, 2) if d else None

    accuracy = pct(correct, total) or 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "null_empty_validation_accuracy_pct": accuracy,
           "required_invalid_state_rejection_rate_pct": pct(req_invalid_400, req_invalid),
           "optional_field_nullable_compliance_rate_pct": pct(opt_null_match, opt_null),
           "total_cases": total,
           "coverage": {"produced_cases": sum(1 for c in cases if c["category"] != "_none_")},
           "cases": cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, accuracy, str(cases_path), extra={
        "null_empty_validation_accuracy_pct": accuracy,
        "required_invalid_state_rejection_rate_pct": raw["required_invalid_state_rejection_rate_pct"],
        "optional_field_nullable_compliance_rate_pct": raw["optional_field_nullable_compliance_rate_pct"],
        "produced_cases": raw["coverage"]["produced_cases"]})

    everos_note(agent, f"null-empty test run: accuracy={accuracy}% over {len(endpoints)} endpoints "
                       f"({total} cases); required-rejection="
                       f"{raw['required_invalid_state_rejection_rate_pct']}%")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Null & Empty Validation Accuracy; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "validate-null-empty-fields" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "null_empty_validation_accuracy_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))
