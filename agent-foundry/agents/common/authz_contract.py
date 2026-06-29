"""Shared, deterministic plumbing for the four authorization-rules agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so that leaderboard
differences are attributable to the framework + its gated prompt + its evolved
skill — never to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the access-surface spec (data/authz/authz_spec.json)
  - provision tokens by logging the designated users into the LOCAL target only
  - bind each agent-emitted case (role + endpoint template) to a concrete token
    and the real owned-resource id, send a real HTTP request, record the response
  - decide, per case: data_exposed, leak_safe, pass — by fixed rules
  - drive the per-case loop, emit the result JSON + headline metric
  - best-effort breadcrumb into the shared EverOS memory pool

The framework-specific part — turning the access surface into the authorization
matrix + leakage assertions via the backend LLM — is injected as
`generate(spec) -> {"cases": [...]}`.
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
from urllib.parse import urlparse

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import authz_spec  # noqa: E402

MALFORMED_TOKEN = "Bearer garbage.malformed.token"


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
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
# Spec loading + the access-surface brief handed to the LLM
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads((WORKSPACE / "data" / "authz" / "authz_spec.json").read_text())


def surface_brief(spec: dict) -> str:
    """Compact, unambiguous description of the access surface for the LLM."""
    lines = [
        "roles:",
        "  - viewer  (a low-privilege user; owns none of owner B's resources)",
        "  - owner   (User B; owns the resource under test)",
        "  - admin   (an administrator)",
        f"resource_under_test_id: {spec['resource_id']}  (owned by: owner)",
        f"resource_path_template: {spec['resource_path']}   (use {{id}} for the resource id)",
        f"collection_path: {spec['collection_path']}   (lists resources)",
        f"admin_listing_path: {spec['admin_listing_path']}   (admin-only listing of all users)",
        "resource_field_names (must NOT leak in any forbidden body): "
        + json.dumps(spec["resource_field_names"]),
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTTP — token-aware, local target only
# --------------------------------------------------------------------------- #
def _bearer(token: str) -> str:
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def provision_tokens(spec: dict) -> dict:
    """Log the three designated users into the live target. Returns role->Bearer.
    Deterministic; identical for gold and every agent."""
    tokens = {}
    for role, creds in spec["users"].items():
        url = TARGET_BASE_URL + spec["login_path"]
        _assert_local_target(url)
        data = json.dumps({"username": creds["username"],
                           "password": creds["password"]}).encode()
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.loads(r.read()).get("accessToken", "")
        tokens[role] = _bearer(tok)
    return tokens


def send(method: str, path: str, auth_header) -> tuple:
    """Send one request. auth_header is a Bearer string, MALFORMED_TOKEN, or None.
    Returns (code, body_text, body_json_or_None)."""
    url = TARGET_BASE_URL + path
    _assert_local_target(url)
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    body = json.dumps({"title": "authz-probe"}).encode() if method in ("PUT", "PATCH", "POST") else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
            return r.getcode(), text, _safe_json(text)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace") if e.fp else ""
        return e.code, text, _safe_json(text)
    except Exception:  # noqa
        return -1, "", None


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:  # noqa
        return None


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


# --------------------------------------------------------------------------- #
# Per-case evaluation — fixed rules, no LLM
# --------------------------------------------------------------------------- #
def _auth_for(case: dict, tokens: dict):
    role = case.get("requesting_role")
    if role == "none":
        return None
    if role == "malformed":
        return MALFORMED_TOKEN
    return tokens.get(role)


def _data_exposed(case: dict, body_text: str, body_json, owner_snapshot: dict) -> bool:
    """True when the body reveals owner-resource data it must not.

    For the collection case: True if the owner resource id appears among the
    listed resources. For the unauthorized single-resource cases: True if any of
    the owner resource's actual field values surfaces in the body."""
    excl = case.get("list_must_exclude")
    if excl is not None:
        if isinstance(body_json, dict):
            for v in body_json.values():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and str(item.get("id")) == str(excl):
                            return True
        return str(excl) in body_text and '"id"' in body_text
    for fname in case.get("leakage", {}).get("forbidden_fields", []):
        val = owner_snapshot.get(fname)
        if val in (None, "", []):
            continue
        token = str(val).strip()
        if len(token) >= 4 and token in body_text:
            return True
    return False


def _leak_safe(case: dict, code, body_text: str, body_json) -> bool:
    """For a non-2xx body: must carry a non-empty error/message string AND none of
    the forbidden substrings. For a 2xx body the guard is not applicable (True)."""
    if code is not None and 200 <= code < 300:
        return True
    has_msg = isinstance(body_json, dict) and any(
        isinstance(body_json.get(k), str) and body_json.get(k).strip()
        for k in ("error", "message"))
    if not has_msg:
        return False
    subs = case.get("leakage", {}).get("forbidden_substrings", []) or []
    return not any(s and s in body_text for s in subs)


def evaluate(case: dict, code, body_text: str, body_json, owner_snapshot: dict) -> dict:
    expected = case.get("expected_code")
    ac = authz_spec.classify(code)
    code_ok = (code == expected)
    exposed = _data_exposed(case, body_text, body_json, owner_snapshot)
    safe = _leak_safe(case, code, body_text, body_json)

    if case.get("expect_resource_data"):           # ADMIN_GET: data SHOULD be present
        data_present = bool(owner_snapshot) and any(
            (str(owner_snapshot.get(f)).strip() in body_text)
            for f in case.get("leakage", {}).get("forbidden_fields", [])
            if owner_snapshot.get(f) not in (None, "", []))
        passed = code_ok and data_present
        return {"actual_code": code, "actual_class": ac, "data_exposed": False,
                "data_present": data_present, "leak_safe": True, "pass": passed}

    if expected is not None and 200 <= expected < 300:   # VIEWER_LIST: 200 w/o owner res
        passed = code_ok and not exposed
    else:                                                # 401/403 cases
        passed = code_ok and not exposed and safe
    return {"actual_code": code, "actual_class": ac, "data_exposed": exposed,
            "data_present": None, "leak_safe": safe, "pass": passed}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
CORE = {"VIEWER_GET", "VIEWER_PUT", "VIEWER_DELETE", "ADMIN_GET",
        "VIEWER_ADMIN_ENDPOINT", "VIEWER_LIST"}


def run_authz_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(spec: dict) -> {"cases": [ case, ... ]} where each case has
        sub_test, requesting_role, method, endpoint (with {id}), resource_owner,
        expected_code, leakage{forbidden_fields, forbidden_substrings},
        expect_resource_data, list_must_exclude. The harness binds the role to a
        token and {id} to the real resource id, sends each case to the local
        target, and records the real response. Missing sub_tests simply do not
        appear; the judge scores coverage against the gold case set. May raise;
        recorded as a generation error, not a crash.
    """
    spec = load_spec()
    owner_snapshot = spec.get("owner_resource_snapshot", {})
    tokens = provision_tokens(spec)

    try:
        out = generate(spec) or {}
        gen_error = None
    except Exception as e:  # noqa
        out = {}
        gen_error = f"{type(e).__name__}: {e}"

    cases = []
    core_total = core_pass = 0
    for case in authz_spec.iter_cases(out):
        endpoint = str(case["endpoint"]).replace("{id}", str(spec["resource_id"]))
        auth = _auth_for(case, tokens)
        code, text, bj = send(str(case["method"]).upper(), endpoint, auth)
        ev = evaluate(case, code, text, bj, owner_snapshot)
        row = {"sub_test": case.get("sub_test"),
               "requesting_role": case.get("requesting_role"),
               "method": str(case.get("method")).upper(), "endpoint": endpoint,
               "resource_owner": case.get("resource_owner"),
               "expected_code": case.get("expected_code"),
               "body_snippet": text[:200], **ev, "error": None}
        cases.append(row)
        if case.get("sub_test") in CORE:
            core_total += 1
            core_pass += 1 if ev["pass"] else 0

    if not cases:
        cases.append({"sub_test": "_none_", "error": gen_error or "no cases produced",
                      "actual_code": None, "actual_class": "none", "pass": False})

    # G1 staging write — write per-item findings for G1b orchestration
    _write_staging_findings(
        agent=agent,
        item_id="authz-access-surface",
        item_label=str(spec.get("resource_path", "access-surface")),
        step_results=[
            {
                "assertion_result": "PASS" if c.get("pass") else "FAIL",
                "assertion_detail": (
                    f"sub_test={c.get('sub_test')} role={c.get('requesting_role')} "
                    f"{c.get('method')} {c.get('endpoint')} "
                    f"expected={c.get('expected_code')} actual={c.get('actual_code')} "
                    f"(class={c.get('actual_class')})"
                ),
                **c,
            }
            for c in cases
        ],
    )

    accuracy = round(100.0 * core_pass / core_total, 2) if core_total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "access_control_accuracy_rate_pct": accuracy,
           "core_sub_tests": core_total, "core_passed": core_pass,
           "cases": cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, accuracy, str(cases_path),
         extra={"access_control_accuracy_rate_pct": accuracy,
                "produced_cases": sum(1 for c in cases if c["sub_test"] != "_none_")})
    everos_note(agent, f"authz run: access_control_accuracy={accuracy}% "
                       f"core {core_pass}/{core_total}")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value is the headline
    accuracy; the judge later overwrites metric_value with Authorization Fidelity."""
    metric = {}
    mp = WORKSPACE / "judge" / "metric_authz.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "access_control_accuracy_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
    payload = {"session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
               "project_id": cfg.get("project_id", "agent-foundry"),
               "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                             "content": text, "timestamp": int(time.time())}]}
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
