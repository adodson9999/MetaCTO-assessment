"""Shared, deterministic execution harness for the four auth-flow agents.

This module carries NO debate-gated instruction. It is the identical substrate
every framework sits on: it reads the auth test PLAN the agent generated,
constructs each credential deterministically (login / mint-expired / truncate /
logout-then-reuse — all in auth_spec), sends each to the LOCAL protected
endpoint, records the real response, and computes the task findings:

  - Auth Flow Pass Rate  = correct-code cases / executed cases x 100  (task rule)
  - False Acceptance Rate = invalid scenarios returning 2xx           (critical)
  - False Rejection Rate  = valid scenarios returning non-2xx

The agent is purely generative: it emits the plan (recipes + task-rule expected
codes + the not_applicable enumeration). It never sends a request. The framework
-specific part — eliciting that plan from the backend LLM — is injected as
`generate() -> dict`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
SECRET = os.environ.get("JWT_SECRET", "forge_test_secret")

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import auth_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox guard
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


# --------------------------------------------------------------------------- #
# Spec loading + the brief handed to the model
# --------------------------------------------------------------------------- #
def load_security() -> dict:
    return json.loads((WORKSPACE / "data" / "auth_openapi.json").read_text())


def scheme_brief() -> str:
    """Compact, unambiguous description of the documented security section +
    the protected endpoint + which schemes are absent. Handed to the LLM."""
    spec = load_security()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    lines = ["protected_endpoint: GET /auth/me",
             "login_endpoint: POST /auth/login (creds: emilys / emilyspass)",
             "revoke_equivalent: POST /auth/logout (no dedicated /auth/revoke exists)",
             "documented_security_schemes:"]
    for name, defn in schemes.items():
        lines.append(f"  - {name}: type={defn.get('type')} scheme={defn.get('scheme')} "
                     f"format={defn.get('bearerFormat')} (sent in Authorization header as 'Bearer <jwt>')")
    lines.append(f"schemes_NOT_documented_in_this_API: {spec.get('x-not-implemented', [])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# LLM-output JSON extraction (deterministic, no model)
# --------------------------------------------------------------------------- #
def extract_json(text: str):
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
def run_auth_test(agent: str, generate) -> dict:
    """Execute one agent's auth test plan against the live target.

    generate() -> the agent's plan object:
        {protected_endpoint, schemes:[{scheme, subtests:[{label, credential, expected_class}]}],
         not_applicable:[{item, status}]}
    The harness iterates each implemented sub-test, builds its credential, sends
    it to the protected endpoint, and records the real response. The agent never
    sends anything. Whatever the agent fails to emit simply does not appear — the
    judge scores coverage + correct outcome against the gold.
    """
    auth_spec._assert_local(TARGET_BASE_URL)
    ep = auth_spec.PROTECTED_ENDPOINT
    try:
        plan = generate() or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    cases = []
    executed = correct = false_accept = false_reject = 0
    for sname, label, recipe, expected in auth_spec.iter_subtests(plan):
        headers, note = auth_spec.build_credential(recipe, TARGET_BASE_URL, SECRET)
        code, text = auth_spec._request(TARGET_BASE_URL, ep["method"], ep["path"], headers=headers)
        actual_class = auth_spec.classify(code)
        msg = _message_of(text)
        passed = (actual_class == expected)
        cases.append({"scheme": sname, "label": label, "recipe": recipe,
                      "construction_note": note, "expected_class": expected,
                      "actual_code": code, "actual_class": actual_class,
                      "message": msg, "task_rule_pass": passed, "error": None})
        executed += 1
        if passed:
            correct += 1
        if label == "valid" and actual_class != "2xx":
            false_reject += 1
        if label != "valid" and actual_class == "2xx":
            false_accept += 1

    na_items = [{"item": item, "status": status}
                for item, status in auth_spec.iter_not_applicable(plan)]

    if executed == 0:
        cases.append({"scheme": None, "label": "_none_", "recipe": None,
                      "construction_note": gen_error or "no plan produced",
                      "expected_class": None, "actual_code": None,
                      "actual_class": "none", "message": "", "task_rule_pass": False,
                      "error": gen_error or "no executable sub-tests produced"})

    pass_rate = round(100.0 * correct / executed, 2) if executed else 0.0
    far = round(100.0 * false_accept / executed, 2) if executed else 0.0
    frr = round(100.0 * false_reject / executed, 2) if executed else 0.0

    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "auth_flow_pass_rate_pct": pass_rate,
           "false_acceptance_rate_pct": far, "false_rejection_rate_pct": frr,
           "false_acceptance_count": false_accept, "false_rejection_count": false_reject,
           "executed_cases": executed,
           "not_applicable_enumerated": na_items,
           "cases": cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, pass_rate, str(cases_path), extra={
        "auth_flow_pass_rate_pct": pass_rate,
        "false_acceptance_rate_pct": far, "false_rejection_rate_pct": frr,
        "executed_cases": executed})

    crit = " CRITICAL:false-acceptance" if false_accept else ""
    everos_note(agent, f"auth-flow run: pass_rate={pass_rate}% executed={executed} "
                       f"FAR={far}% FRR={frr}%{crit}")
    return raw


def _message_of(text: str) -> str:
    try:
        return json.loads(text).get("message", "")
    except Exception:  # noqa
        return ""


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Auth Flow Pass Rate; the judge later overwrites metric_value with Auth-Flow
    Fidelity for ranking."""
    metric = {}
    mp = WORKSPACE / "judge" / "auth_metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("headline_metric", "auth_flow_pass_rate_pct"),
               "metric_value": metric_value,
               "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))
