"""Shared, deterministic plumbing for the four contract-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so that leaderboard
differences are attributable to the framework + its gated prompt + its evolved
skill — never to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint list from data/openapi.json
  - send a real HTTP request to the LOCAL target only (sandbox + host guard)
  - classify status codes
  - robustly extract a JSON object from an LLM's text output
  - drive the per-endpoint loop, record every case, emit the result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The framework-specific part — turning one endpoint's schema into the six
payloads via the backend LLM — is injected as `generate(endpoint) -> dict`.
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
import backend_config  # noqa: E402
import payload_spec  # noqa: E402

VARIANTS = payload_spec.CATEGORIES


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
    # Only the configured local target host is reachable. No other host, ever.
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
def load_endpoints() -> list[dict]:
    spec = json.loads((WORKSPACE / "data" / "openapi.json").read_text())
    out = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            media = op["requestBody"]["content"]["application/json"]
            schema = media["schema"]
            props = schema.get("properties", {})
            maxlen_field = next((k for k, v in props.items()
                                 if v.get("type") == "string" and "maxLength" in v), None)
            out.append({
                "slug": op["operationId"],
                "method": method.upper(),
                "path": path,
                "properties": props,
                "required": schema.get("required", []),
                "maxlen_field": maxlen_field,
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
        c = [f"type={v.get('type', 'any')}"]
        if "maxLength" in v:
            c.append(f"maxLength={v['maxLength']}")
        req = "required" if k in ep["required"] else "optional"
        lines.append(f"  - {k} ({req}, {', '.join(c)})")
    lines.append(f"required: {ep['required']}")
    mls = [k for k, v in ep["properties"].items()
           if v.get("type") == "string" and "maxLength" in v]
    lines.append(f"maxLength_string_fields: {mls}")  # ALL of them; [] if none
    lines.append(f"known_valid_example: {json.dumps(ep['example'])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTTP + classification
# --------------------------------------------------------------------------- #
def send(method: str, path: str, body) -> int:
    url = TARGET_BASE_URL + path.replace("{id}", EXISTING_ID)
    _assert_local_target(url)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa
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
        "session_id": RUN_ID,
        "app_id": cfg.get("app_id", "forge"),
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
    except Exception:  # noqa  -- EverOS optional; never block a run
        pass
    # guaranteed local breadcrumb inside the shared pool dir
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
def run_contract_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(endpoint: dict) -> the six-key output object (see payload_spec):
        "valid" + "inv_all_null" are single bodies; the other four are arrays of
        labeled payload objects. The harness iterates every labeled body the agent
        emitted, sends each to the local target, and records the real response.
        Whatever the agent fails to emit simply does not appear — the judge scores
        coverage against the gold case set. May raise; recorded as a per-endpoint
        generation error, not a crash.
    """
    endpoints = load_endpoints()
    cases = []
    invalid_sent = invalid_rejected = 0

    for ep in endpoints:
        _ep_case_start = len(cases)
        try:
            out = generate(ep) or {}
            gen_error = None
        except Exception as e:  # noqa
            out = {}
            gen_error = f"{type(e).__name__}: {e}"

        produced = False
        for category, label, field, expected, body in payload_spec.iter_cases(out):
            produced = True
            if not isinstance(body, (dict, list)):
                code, ac = None, "none"
            else:
                code = send(ep["method"], ep["path"], body)
                ac = classify(code)
            cases.append({"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
                          "category": category, "label": label, "field": field,
                          "expected_class": expected, "actual_code": code,
                          "actual_class": ac, "sent_body": body, "error": None})
            if category != "valid":
                invalid_sent += 1
                if ac == "400":
                    invalid_rejected += 1
        if not produced:
            cases.append({"slug": ep["slug"], "method": ep["method"], "path": ep["path"],
                          "category": "_none_", "label": "", "field": None,
                          "expected_class": None, "actual_code": None,
                          "actual_class": "none", "sent_body": None,
                          "error": gen_error or "no payloads produced"})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=ep["slug"],
            item_label=f"{ep['method']} {ep['path']}",
            step_results=[
                {
                    "assertion_result": "PASS" if c.get("actual_class") == c.get("expected_class") else "FAIL",
                    "assertion_detail": (
                        f"category={c['category']} label={c.get('label','')} "
                        f"sent HTTP {c['method']} {c['path']} → "
                        f"status {c['actual_code']} (class={c['actual_class']}, expected={c['expected_class']})"
                    ),
                    **c,
                }
                for c in cases[_ep_case_start:]
            ],
        )

    rejection_rate = round(100.0 * invalid_rejected / invalid_sent, 2) if invalid_sent else 0.0
    produced_cases = sum(1 for c in cases if c["category"] != "_none_")

    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "payload_rejection_rate_pct": rejection_rate,
           "invalid_sent": invalid_sent, "invalid_rejected_400": invalid_rejected,
           "coverage": {"produced_cases": produced_cases},
           "cases": cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rejection_rate, str(cases_path), extra={
        "payload_rejection_rate_pct": rejection_rate,
        "produced_cases": produced_cases})

    everos_note(agent, f"contract-test run: rejection_rate={rejection_rate}% "
                       f"produced {produced_cases} labeled cases over {len(endpoints)} endpoints")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    rejection rate; the judge later overwrites it with Contract-Test Fidelity."""
    metric = {}
    mp = WORKSPACE / "judge" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "payload_rejection_rate_pct"),
               "metric_value": metric_value,
               "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))
