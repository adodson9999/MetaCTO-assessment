"""Shared, deterministic plumbing for the four OAuth-integration-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the OAuth flow catalogue from
    data/verify-third-party-oauth-integration/oauth_spec.json
  - build the compact per-flow brief handed to the agent
  - execute whatever 5-stage plan the agent emitted against the LOCAL target only
    (sandbox + host guards): drive the documented OAuth2 authorization-code flow —
    Stage 1 authorize redirect, Stage 2 follow to the callback for code+state, Stage 3
    token exchange, Stage 4 access-token use, Stage 5 refresh + re-use — recording the
    REAL observed outcome at each stage
  - evaluate every assertion (shared oauth_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified, per the Phase-2 owner decision. The
flow's auth requests (the authorize GET, the token/refresh POSTs, the /me GET) are
DummyJSON's own auth surface; DummyJSON's writes are non-persistent, so issuing them
does not change the target. It ships no OAuth2 authorization-code flow, so every stage
fails the idealized contract — a genuine QA finding (OAuth Flow Completion Rate = 0%).

The framework-specific part — turning one flow's brief into the 5-stage OAuth test
plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
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
SPEC_PATH = WORKSPACE / "data" / "verify-third-party-oauth-integration" / "oauth_spec.json"

# Bound the redirect chase so a misbehaving target can never loop us forever.
MAX_REDIRECT_HOPS = 5

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import oauth_spec  # noqa: E402


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


def flow_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for f in spec["flows"]:
        out.append({
            "provider": f["provider"],
            "authorize_endpoint": f.get("authorize_endpoint", spec["authorize_endpoint"]),
            "callback_endpoint": f.get("callback_endpoint", spec["callback_endpoint"]),
            "token_endpoint": f.get("token_endpoint", spec["token_endpoint"]),
            "userinfo_endpoint": f.get("userinfo_endpoint", spec["userinfo_endpoint"]),
            "refresh_endpoint": f.get("refresh_endpoint", spec["refresh_endpoint"]),
            "client_id": f["client_id"],
            "redirect_uri": f["redirect_uri"],
            "scope": f["scope"],
            "state_min_length": spec.get("state_min_length", oauth_spec.MIN_STATE_LENGTH),
        })
    only = os.environ.get("FORGE_ONLY_FLOWS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["provider"] in wanted]
    return out


def flow_brief(cfg: dict) -> str:
    """Compact, unambiguous OAuth2 authorization-code contract handed to the LLM."""
    return "\n".join([
        f"provider: {cfg['provider']}",
        f"authorize_endpoint: {cfg['authorize_endpoint']}   # GET; documented to 302-redirect to the provider",
        f"callback_endpoint: {cfg['callback_endpoint']}     # where the provider returns ?code=&state=",
        f"token_endpoint: {cfg['token_endpoint']}           # POST; exchanges the code for tokens",
        f"userinfo_endpoint: {cfg['userinfo_endpoint']}     # GET; returns the user profile for a Bearer token",
        f"refresh_endpoint: {cfg['refresh_endpoint']}       # POST; exchanges a refresh_token for a new access_token",
        f"client_id: {cfg['client_id']}",
        f"redirect_uri: {cfg['redirect_uri']}",
        f"scope: {cfg['scope']}",
        f"state_min_length: {cfg['state_min_length']}",
        "contract: a correct integration runs the authorization-code flow in five stages — "
        "(1) the authorize endpoint 302-redirects to an HTTPS URL carrying client_id, redirect_uri, "
        "scope, and a state of at least state_min_length chars; (2) approving redirects to the "
        "callback with a non-empty code and the same state (CSRF); (3) the token endpoint returns "
        "200 with access_token, token_type \"Bearer\", refresh_token, and a positive expires_in; "
        "(4) the userinfo endpoint returns 200 with a non-empty profile field for the access token; "
        "(5) the refresh endpoint returns 200 with a new access_token different from the first, and "
        "userinfo with the new token returns 200.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (no-redirect-follow opener so we can inspect 302 Location ourselves)
# --------------------------------------------------------------------------- #
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa
        return None  # never auto-follow; the harness inspects Location itself


_OPENER = urllib.request.build_opener(_NoRedirect)


def _request(method: str, path: str, headers: dict | None = None,
             body: bytes | None = None, _retries: int = 4):
    """One HTTP request that does NOT auto-follow redirects. Returns
    (status_code, headers_dict, body_text). A 3xx/4xx/5xx is a real response and is
    returned as-is; only transient connection failures (status -1) retry briefly —
    retries are generous because the single-threaded local target can reset a
    connection under concurrent agents, which must not be mistaken for a real outcome."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    last = (-1, {}, "")
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, method=method, data=body)
        for k, v in (headers or {}).items():
            if k and v is not None:
                req.add_header(k, str(v))
        try:
            with _OPENER.open(req, timeout=20) as r:
                return r.getcode(), dict(r.headers.items()), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            hdrs = dict(e.headers.items()) if e.headers else {}
            try:
                text = e.read().decode("utf-8", "replace")
            except Exception:  # noqa
                text = ""
            return e.code, hdrs, text
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            last = (-1, {}, "")
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return last


def _json_or_none(text: str):
    try:
        return json.loads(text)
    except Exception:  # noqa
        return None


def _query_of(location: str) -> dict:
    """Parse the query string of a (possibly absolute) URL into a flat dict."""
    if not location:
        return {}
    parsed = urllib.parse.urlparse(location)
    return {k: (v[0] if v else "") for k, v in urllib.parse.parse_qs(parsed.query).items()}


def _path_of(location: str) -> str:
    return urllib.parse.urlparse(location).path or ""


# --------------------------------------------------------------------------- #
# Flow execution
# --------------------------------------------------------------------------- #
def _planned_stage_names(plan: dict) -> set[str]:
    """Which stage names the agent actually included (so an omitted stage scores
    'missing' for all its assertions)."""
    names: set[str] = set()
    if not isinstance(plan, dict):
        return names
    for st in plan.get("stages", []) if isinstance(plan.get("stages"), list) else []:
        if isinstance(st, dict) and st.get("name") in oauth_spec.STAGE_NAMES:
            names.add(st["name"])
    return names


def _exec_flow(cfg: dict, plan: dict) -> tuple[dict, list]:
    """Execute the AGENT's 5-stage plan against the LOCAL target and record raw
    observations. Tolerant of missing/malformed keys — a stage the agent omitted is
    not run and its assertions score 'missing'."""
    reqlog: list = []
    planned = _planned_stage_names(plan)
    raw: dict = {"stages_run": {n: False for n in oauth_spec.STAGE_NAMES}}

    # ---- Stage 1: authorize redirect ----
    state1 = None
    location = None
    if "redirect" in planned:
        raw["stages_run"]["redirect"] = True
        status, hdrs, _ = _request("GET", cfg["authorize_endpoint"])
        location = hdrs.get("Location") or hdrs.get("location")
        q = _query_of(location or "")
        state1 = q.get("state")
        raw.update({
            "s1_status": status, "s1_location": location,
            "s1_client_id_match": q.get("client_id") == cfg["client_id"],
            "s1_redirect_uri_match": q.get("redirect_uri") == cfg["redirect_uri"],
            "s1_scope_match": q.get("scope") == cfg["scope"],
            "s1_state": state1, "s1_state_for_csrf": state1,
        })
        reqlog.append({"stage": 1, "name": "redirect", "method": "GET",
                       "path": cfg["authorize_endpoint"], "status": status,
                       "location": location})

    # ---- Stage 2: code receipt (auto-approve: follow the redirect chain to the callback) ----
    code = None
    state2 = None
    if "code_receipt" in planned:
        raw["stages_run"]["code_receipt"] = True
        code, state2 = _follow_to_callback(location, cfg["callback_endpoint"], reqlog)
        raw.update({"s2_code": code, "s2_state": state2})
        # carry stage-1 state forward for the CSRF comparison regardless of stage-1 result
        raw.setdefault("s1_state_for_csrf", state1)

    # ---- Stage 3: token exchange ----
    access_token = None
    refresh_token = None
    if "token_exchange" in planned:
        raw["stages_run"]["token_exchange"] = True
        payload = json.dumps({
            "grant_type": "authorization_code", "code": code or "",
            "redirect_uri": cfg["redirect_uri"], "client_id": cfg["client_id"],
        }).encode()
        status, _, text = _request("POST", cfg["token_endpoint"],
                                   headers={"Content-Type": "application/json"}, body=payload)
        doc = _json_or_none(text) or {}
        access_token = doc.get("access_token") if isinstance(doc, dict) else None
        refresh_token = doc.get("refresh_token") if isinstance(doc, dict) else None
        raw.update({
            "s3_status": status,
            "s3_access_token": access_token,
            "s3_token_type": doc.get("token_type") if isinstance(doc, dict) else None,
            "s3_refresh_token": refresh_token,
            "s3_expires_in": doc.get("expires_in") if isinstance(doc, dict) else None,
        })
        reqlog.append({"stage": 3, "name": "token_exchange", "method": "POST",
                       "path": cfg["token_endpoint"], "status": status})

    # ---- Stage 4: access-token use ----
    if "access_token_use" in planned:
        raw["stages_run"]["access_token_use"] = True
        status, _, text = _request("GET", cfg["userinfo_endpoint"],
                                   headers={"Authorization": f"Bearer {access_token or ''}"})
        doc = _json_or_none(text) or {}
        profile_value = None
        if isinstance(doc, dict):
            for k in ("email", "username", "firstName", "name", "id"):
                v = doc.get(k)
                if isinstance(v, str) and v:
                    profile_value = v
                    break
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    profile_value = str(v)
                    break
        raw.update({"s4_status": status, "s4_profile_value": profile_value})
        reqlog.append({"stage": 4, "name": "access_token_use", "method": "GET",
                       "path": cfg["userinfo_endpoint"], "status": status})

    # ---- Stage 5: token refresh + re-use ----
    if "token_refresh" in planned:
        raw["stages_run"]["token_refresh"] = True
        payload = json.dumps({"refresh_token": refresh_token or ""}).encode()
        status, _, text = _request("POST", cfg["refresh_endpoint"],
                                   headers={"Content-Type": "application/json"}, body=payload)
        doc = _json_or_none(text) or {}
        new_access = doc.get("access_token") if isinstance(doc, dict) else None
        me_status, _, _ = _request("GET", cfg["userinfo_endpoint"],
                                   headers={"Authorization": f"Bearer {new_access or ''}"})
        raw.update({
            "s5_status": status, "s5_new_access_token": new_access,
            "s5_old_access_token": access_token, "s5_me_status": me_status,
        })
        reqlog.append({"stage": 5, "name": "token_refresh", "method": "POST",
                       "path": cfg["refresh_endpoint"], "status": status,
                       "me_status": me_status})

    return raw, reqlog


def _follow_to_callback(location: str | None, callback_path: str, reqlog: list):
    """Auto-approve = follow the local redirect chain (bounded) until we reach the
    callback path carrying ?code=&state=, or run out of hops. Returns (code, state).
    Against a target with no authorize redirect (DummyJSON), location is None and this
    yields (None, None) immediately — the honest 'no code issued' outcome."""
    hops = 0
    current = location
    while current and hops < MAX_REDIRECT_HOPS:
        hops += 1
        q = _query_of(current)
        if _path_of(current).rstrip("/") == callback_path.rstrip("/") and q.get("code"):
            return q.get("code"), q.get("state")
        # follow one more local hop if the URL is on our target
        path = _path_of(current)
        query = urllib.parse.urlparse(current).query
        if not path:
            break
        status, hdrs, _ = _request("GET", f"{path}{('?' + query) if query else ''}")
        reqlog.append({"stage": 2, "name": "code_receipt", "method": "GET",
                       "path": path, "status": status})
        nxt = hdrs.get("Location") or hdrs.get("location")
        if not nxt:
            # terminal response; if it itself is the callback with a code, capture it
            q = _query_of(current)
            return (q.get("code"), q.get("state")) if q.get("code") else (None, None)
        current = nxt
    return None, None


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
def run_oauth_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the 5-stage OAuth flow plan object (see oauth_spec): a dict
        with the copied context fields and a `stages` array of five stage objects. The
        harness executes the documented flow stage by stage against the local target and
        evaluates every assertion. Whatever the agent fails to plan scores as 'missing'.
        generate may raise; recorded per-flow.
    """
    cfgs = flow_cfgs()
    all_cases = []
    total = correct = 0
    flows_complete = 0
    stage_pass_counts = {s["name"]: 0 for s in oauth_spec.STAGE_DEFS}

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        raw, reqlog = _exec_flow(cfg, plan)
        observed = oauth_spec.evaluate(raw)

        assertions = []
        for label in oauth_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = oauth_spec.correct(label, tok)
            assertions.append({"provider": cfg["provider"], "scenario": label,
                               "ideal": oauth_spec.ideal_for(label),
                               "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0

        stages_doc = []
        for s in oauth_spec.STAGE_DEFS:
            sc = oauth_spec.stage_correct(s["stage"], observed)
            if sc:
                stage_pass_counts[s["name"]] += 1
            stages_doc.append({"stage": s["stage"], "name": s["name"], "stage_correct": sc})

        complete = oauth_spec.flow_complete(observed)
        if complete:
            flows_complete += 1

        all_cases.append({"provider": cfg["provider"], "client_id": cfg["client_id"],
                          "redirect_uri": cfg["redirect_uri"], "scope": cfg["scope"],
                          "flow_complete": complete, "stages": stages_doc,
                          "emitted_plan": plan, "request_log": reqlog,
                          "assertions": assertions, "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(cfg["provider"]).strip().replace("/", "-").replace(" ", "-") or "provider",
            item_label=f"OAuth flow provider={cfg['provider']} (flow_complete={complete})",
            step_results=[
                {
                    "assertion_result": "PASS" if a.get("api_correct") else "FAIL",
                    "assertion_detail": (
                        f"scenario={a.get('scenario')} ideal={a.get('ideal')} "
                        f"observed={a.get('observed_token')}"
                    ),
                    **a,
                }
                for a in assertions
            ],
        )

    n_flows = len(cfgs)
    completion_rate = round(100.0 * flows_complete / n_flows, 2) if n_flows else 0.0
    fidelity_headline = round(100.0 * correct / total, 2) if total else 0.0
    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
               "oauth_flow_completion_rate_pct": completion_rate,
               "flows_complete": flows_complete, "flows_total": n_flows,
               "assertion_correctness_rate_pct": fidelity_headline,
               "stage_pass_counts": stage_pass_counts,
               "assertions_total": total, "assertions_api_correct": correct,
               "flows": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, completion_rate, str(cases_path), extra={
        "oauth_flow_completion_rate_pct": completion_rate,
        "flows_complete": flows_complete, "flows_total": n_flows,
        "stage_pass_counts": stage_pass_counts,
        "assertions_total": total})

    everos_note(agent, f"oauth-integration-test run: completion_rate={completion_rate}% "
                       f"({flows_complete}/{n_flows} flows) over {total} assertions")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline OAuth
    Flow Completion Rate; the judge later overwrites metric_value with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "verify-third-party-oauth-integration" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "oauth_flow_completion_rate_pct"),
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
