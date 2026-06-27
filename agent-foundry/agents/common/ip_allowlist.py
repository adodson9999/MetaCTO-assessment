"""Shared, deterministic plumbing for the four IP-allowlist-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the restricted-endpoint catalogue from
    data/test-ip-allowlist-enforcement/ip_allowlist_spec.json
  - build the compact per-endpoint brief handed to the agent
  - execute whatever plan the agent emitted against the LOCAL ip-allowlist-gateway only
    (sandbox + host guards): reset the endpoint's IP set to {allow_ip}, then for each
    case perform its allowlist management action and send one resource request with the
    edge-verified source IP and optional X-Forwarded-For exactly as the case specifies
  - record each case's real status code + whether the protected resource data leaked,
    evaluate every scenario (shared ip_allowlist_spec.evaluate), emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is never touched: the target is the local gateway. Each agent runs in its own
WAF scope (namespaced by agent name) so parallel agents never corrupt each other's
allowlist state.

The framework-specific part — turning one endpoint's brief into the IP-allowlist test
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
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8913").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-ip-allowlist-enforcement" / "ip_allowlist_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import ip_allowlist_spec  # noqa: E402

SCOPE_HEADER = "X-Waf-Scope"


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
        out.append({
            "endpoint": e["endpoint"],
            "method": spec.get("method", "GET"),
            "success_code": spec.get("success_code", ip_allowlist_spec.DEFAULT_SUCCESS_CODE),
            "forbidden_code": spec.get("forbidden_code", ip_allowlist_spec.DEFAULT_FORBIDDEN_CODE),
            "allow_ip": e.get("allow_ip", spec.get("allow_ip")),
            "block_ip": e.get("block_ip", spec.get("block_ip")),
            "edge_ip_header": spec.get("edge_ip_header", ip_allowlist_spec.EDGE_IP_HEADER),
            "xff_header": spec.get("xff_header", ip_allowlist_spec.XFF_HEADER),
            "mgmt_allowlist_path": spec.get("mgmt_allowlist_path", ip_allowlist_spec.MGMT_ALLOWLIST_PATH),
            "waf_scope": e.get("waf_scope", "ipset-" + e["endpoint"].strip("/").replace("/", "-")),
        })
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["endpoint"] in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous IP-allowlist contract handed to the LLM."""
    return "\n".join([
        f"endpoint_path: {cfg['endpoint']}",
        f"method: {cfg['method']}",
        f"success_code: {cfg['success_code']}   # status an allowed request returns",
        f"forbidden_code: {cfg['forbidden_code']}   # status a blocked request returns",
        f"allow_ip: {cfg['allow_ip']}        # currently ON the allowlist",
        f"block_ip: {cfg['block_ip']}        # currently NOT on the allowlist",
        f"edge_ip_header: {cfg['edge_ip_header']}   # carries the edge-verified source IP",
        f"xff_header: {cfg['xff_header']}   # client-supplied forwarded-for value (untrusted)",
        f"mgmt_allowlist_path: {cfg['mgmt_allowlist_path']}   # allowlist management API mount",
        f"waf_scope: {cfg['waf_scope']}   # IP set to evaluate against",
        "contract: an allowed (allowlisted source IP) request returns success_code with the "
        "resource data; a blocked (non-allowlisted source IP) request returns forbidden_code "
        "with no resource data; the allowlist decision must NOT honor the xff_header; the "
        "management API can add/remove an IP from the set.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (local gateway only): resource GET + allowlist management
# --------------------------------------------------------------------------- #
def _request(method: str, path: str, headers: dict | None = None,
             body: dict | None = None, _retries: int = 2):
    """One request to the LOCAL gateway. Returns (status_code, body_dict). Transient
    connection failures (status -1) retry briefly; real HTTP codes are returned as-is."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            if k and v is not None:
                req.add_header(k, str(v))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                try:
                    return r.getcode(), json.loads(raw or b"{}")
                except Exception:  # noqa
                    return r.getcode(), {}
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:  # noqa
                return e.code, {}
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, {}


def _data_exposed(code: int | None, body: dict) -> bool:
    """The protected payload leaked iff the body carries resource records/secrets.
    A correct 403 body is just {"message": "Forbidden"} and exposes nothing."""
    if not isinstance(body, dict):
        return False
    if "records" in body or "secret" in json.dumps(body):
        return True
    return False


def _reset_scope(cfg: dict, scope: str) -> None:
    _request("POST", "/__waf/reset", body={"scope": scope, "ips": [cfg["allow_ip"]]})


def _apply_mgmt(cfg: dict, scope: str, action: str) -> None:
    path = cfg["mgmt_allowlist_path"]
    if action == "add_block_ip":
        _request("PUT", path, body={"scope": scope, "ip": cfg["block_ip"]})
    elif action == "remove_block_ip":
        _request("DELETE", path, body={"scope": scope, "ip": cfg["block_ip"]})
    # "none" -> no management call


def _resolve_ip(cfg: dict, token) -> str | None:
    if token == "allow_ip":
        return cfg["allow_ip"]
    if token == "block_ip":
        return cfg["block_ip"]
    return None


def _exec_plan(cfg: dict, plan: dict, scope: str) -> tuple[dict, list]:
    """Execute the AGENT's plan against the local gateway. Tolerant of missing/malformed
    keys — a case the agent omits is not run and scores 'missing'. Returns (obs, log)."""
    obs: dict[str, dict] = {label: {"ran": False, "code": None, "data_exposed": None}
                            for label in ip_allowlist_spec.CASE_LABELS}
    reqlog: list = []
    if not isinstance(plan, dict):
        return obs, reqlog

    edge_header = plan.get("edge_ip_header") or cfg["edge_ip_header"]
    xff_header = plan.get("xff_header") or cfg["xff_header"]
    cases = plan.get("cases")
    if not isinstance(cases, list):
        return obs, reqlog

    # Each endpoint starts from a known baseline: only allow_ip on the set.
    _reset_scope(cfg, scope)

    for case in cases:
        if not isinstance(case, dict):
            continue
        label = case.get("label")
        if label not in obs:
            continue  # ignore unknown/extra cases; the five fixed labels are the denominator

        # 1. apply the allowlist management action (harness performs it, never the agent)
        _apply_mgmt(cfg, scope, case.get("mgmt_action", "none"))

        # 2. build the request headers: edge-verified source IP + scope, optional XFF
        src_ip = _resolve_ip(cfg, case.get("source_ip"))
        headers = {SCOPE_HEADER: scope}
        if src_ip is not None:
            headers[edge_header] = src_ip
        xff_token = case.get("send_xff")
        xff_val = _resolve_ip(cfg, xff_token) if xff_token else None
        if xff_val is not None:
            headers[xff_header] = xff_val

        # 3. send one resource request and record the real outcome
        code, body = _request(cfg["method"], cfg["endpoint"], headers=headers)
        exposed = _data_exposed(code, body)
        obs[label] = {"ran": True, "code": code, "data_exposed": exposed}
        reqlog.append({"label": label, "source_ip": case.get("source_ip"),
                       "sent_xff": xff_val, "mgmt_action": case.get("mgmt_action", "none"),
                       "status": code, "data_exposed": exposed})

    return obs, reqlog


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
def run_ip_allowlist_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the IP-allowlist plan object (see ip_allowlist_spec): a dict
        with the ten copied context keys and `cases` (the five fixed enforcement cases).
        The harness executes the AGENT's planned requests + management actions and
        evaluates every case. Whatever the agent fails to emit scores as 'missing'.
        generate may raise; recorded per-endpoint.
    """
    cfgs = endpoint_cfgs()
    all_cases = []
    total = correct = 0
    any_leak = False
    any_bypass = False  # a non-allowlisted IP (or XFF spoof) that received 200

    for cfg in cfgs:
        scope = f"{agent}:{cfg['waf_scope']}"  # per-agent isolation on the shared gateway
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        obs, reqlog = _exec_plan(cfg, plan, scope)
        observed = ip_allowlist_spec.evaluate(obs)

        scenarios = []
        for label in ip_allowlist_spec.CASE_LABELS:
            tok = observed.get(label, "missing")
            ok = ip_allowlist_spec.correct(label, tok)
            scenarios.append({"endpoint": cfg["endpoint"], "scenario": label,
                              "ideal": ip_allowlist_spec.ideal_for(label),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
            # critical-finding flags (the headline)
            if label in ("nonallowlisted_baseline", "xff_spoof_rejected", "allowlist_remove_blocks"):
                if tok.startswith("200"):
                    any_bypass = True
            if tok.endswith(":data") and label in ("nonallowlisted_baseline", "xff_spoof_rejected",
                                                    "allowlist_remove_blocks"):
                any_leak = True

        all_cases.append({"endpoint": cfg["endpoint"], "waf_scope": cfg["waf_scope"],
                          "allow_ip": cfg["allow_ip"], "block_ip": cfg["block_ip"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(cfg["endpoint"]).strip("/").replace("/", "-") or "endpoint",
            item_label=f"{cfg['method']} {cfg['endpoint']}",
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
    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
               "ip_allowlist_enforcement_rate_pct": rate,
               "enforcement_pass": (correct == total and total > 0),
               "any_nonallowlisted_200_bypass": any_bypass,
               "any_resource_data_leak_on_block": any_leak,
               "cases_total": total, "cases_correct": correct,
               "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "ip_allowlist_enforcement_rate_pct": rate,
        "enforcement_pass": (correct == total and total > 0),
        "any_nonallowlisted_200_bypass": any_bypass,
        "cases_total": total})

    everos_note(agent, f"ip-allowlist-test run: enforcement_rate={rate}% "
                       f"bypass_detected={any_bypass} over {len(cfgs)} endpoints ({total} cases)")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    enforcement rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-ip-allowlist-enforcement" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "ip_allowlist_enforcement_rate_pct"),
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
