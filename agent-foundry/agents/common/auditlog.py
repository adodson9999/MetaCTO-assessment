"""Shared, deterministic plumbing for the four audit-log-verification agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the collection catalogue from
    data/verify-audit-log-generation/auditlog_spec.json
  - build the compact per-collection brief handed to the agent
  - authenticate as the test user (DummyJSON login; the contract's test_user_id is
    mapped onto real DummyJSON creds via FORGE_TEST_USER / FORGE_TEST_PASS)
  - execute whatever plan the agent emitted: run the create/update/delete operations
    in order, substituting the create-returned id for the literal "{resource_id}"
    token in the update/delete paths, capturing each operation's status and wall-clock
    time
  - query the audit substrate: read the target's own captured log (FORGE_AUDIT_LOG,
    the winston "HTTP Request" stdout the request-logger emits when LOG_ENABLED=true),
    parse it, and check each candidate entry for the audit_query's required fields,
    timestamp tolerance, and user scope
  - evaluate every scenario (shared auditlog_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is NEVER modified: writes are non-persistent (deepFrozen), all HTTP is to
the LOCAL target only (host guard), LOG_ENABLED is a runtime env flag (not a source
change), and every file write stays within the sandbox.

The framework-specific part — turning one collection's brief into the audit-
verification plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
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
SPEC_PATH = WORKSPACE / "data" / "verify-audit-log-generation" / "auditlog_spec.json"
AUDIT_LOG_PATH = os.environ.get("FORGE_AUDIT_LOG", "")  # the captured winston stdout
TEST_USER = os.environ.get("FORGE_TEST_USER", "emilys")
TEST_PASS = os.environ.get("FORGE_TEST_PASS", "emilyspass")

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import auditlog_spec  # noqa: E402


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


def collection_cfgs() -> list[dict]:
    spec = load_spec()
    uid = spec.get("test_user_id", "user-test-001")
    out = []
    for c in spec["collections"]:
        out.append({
            "collection": c["collection"],
            "id_field": spec.get("id_field", "id"),
            "test_user_id": uid,
        })
    only = os.environ.get("FORGE_ONLY_COLLECTIONS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["collection"] in wanted]
    return out


def collection_brief(cfg: dict) -> str:
    """Compact, unambiguous audit-logging contract handed to the LLM."""
    return "\n".join([
        f"collection_path: {cfg['collection']}",
        f"id_field: {cfg['id_field']}        # each item's unique id is under this key",
        f"test_user_id: {cfg['test_user_id']}   # perform the operations as this user",
        "note: the plan performs one create, one update, and one delete on this "
        "collection's record as the test user; the executor runs them in order, then "
        "queries the audit log for the 3 entries those operations should produce.",
    ])


# --------------------------------------------------------------------------- #
# Auth + operation execution
# --------------------------------------------------------------------------- #
def _send(method: str, path: str, body, token: str | None, _retries: int = 2):
    """Send one request to the LOCAL target. Returns (status_code, raw_body_str)."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:  # a real response from the API
            try:
                return e.code, e.read().decode("utf-8", "replace")
            except Exception:  # noqa
                return e.code, None
        except Exception:  # noqa  -- connection refused/reset/timeout: retry briefly
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, None


def authenticate() -> str | None:
    """Log in as the test user (DummyJSON). Returns the access token, or None.
    The contract's test_user_id is a logical handle; DummyJSON has no such user, so it
    is mapped onto real creds (FORGE_TEST_USER / FORGE_TEST_PASS)."""
    code, raw = _send("POST", "/auth/login", {"username": TEST_USER, "password": TEST_PASS}, None)
    if code == 200 and raw:
        try:
            d = json.loads(raw)
            return d.get("accessToken") or d.get("token")
        except Exception:  # noqa
            return None
    return None


def _resolve_path(path: str, resource_id) -> str:
    if resource_id is None:
        return path
    return path.replace(auditlog_spec.RESOURCE_PLACEHOLDER, str(resource_id))


def _id_from_body(raw: str | None, id_field: str):
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return d.get(id_field, d.get("id"))
    except Exception:  # noqa
        return None


def _exec_ops(cfg: dict, plan: dict, token: str | None):
    """Execute the AGENT's create/update/delete in order. Tolerant of missing/malformed
    keys — whatever the agent omits is simply not run and scores as 'missing'.
    Returns (op_obs, op_log, t_start, t_end, resource_id)."""
    op_obs, op_log = {}, []
    ops = plan.get("operations") if isinstance(plan, dict) else None
    ops = ops if isinstance(ops, list) else []
    by_label = {o.get("label"): o for o in ops if isinstance(o, dict) and o.get("label")}

    t_start = time.time()
    resource_id = None

    for label in ("create", "update", "delete"):
        o = by_label.get(label)
        if not o or not o.get("method") or not o.get("path"):
            continue
        path = _resolve_path(o["path"], resource_id if label != "create" else None)
        wall = time.time()
        code, raw = _send(o["method"], path, o.get("body"), token)
        if label == "create":
            resource_id = _id_from_body(raw, cfg.get("id_field", "id"))
        op_obs[label] = {"status": code, "expect_status": o.get("expect_status")}
        op_log.append({"label": label, "action_type": o.get("action_type"),
                       "method": o["method"], "path": path, "status": code,
                       "wall_ts": wall, "resource_id": resource_id})
        time.sleep(0.01)  # keep ops on distinct ms ticks so log timestamps separate

    t_end = time.time()
    return op_obs, op_log, t_start, t_end, resource_id


# --------------------------------------------------------------------------- #
# Audit substrate query (the captured winston request-log)
# --------------------------------------------------------------------------- #
def _parse_log_entries() -> list[dict]:
    """Read + parse the captured target log (FORGE_AUDIT_LOG). Each winston line is a
    JSON object; lines that don't parse are skipped. Returns a list of raw entries.
    If no log is available, returns [] (no audit store => 0 valid entries)."""
    if not AUDIT_LOG_PATH:
        return []
    p = Path(AUDIT_LOG_PATH)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or "HTTP Request" not in line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:  # noqa
            continue
    return entries


def _log_epoch(entry: dict) -> float | None:
    ts = entry.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:  # noqa
        return None


def _audit_field(entry: dict, field: str):
    """Extract a documented audit field from a raw log entry by its audit name.
    Generous synonym mapping for fields the log genuinely carries (timestamp,
    ip_address<-meta.ip); user_id / action_type / resource_id have NO source in the
    winston request-log, so they resolve to None (the honest finding)."""
    meta = entry.get("meta", {}) if isinstance(entry.get("meta"), dict) else {}
    if field == "timestamp":
        return entry.get("timestamp")
    if field == "ip_address":
        v = entry.get("ip_address", meta.get("ip"))
        return v if v not in (None, "") else None
    # user_id / action_type / resource_id: only count if literally present under that name
    v = entry.get(field, meta.get(field))
    return v if v not in (None, "") else None


def _query_audit(plan: dict, op_log: list, t_start: float, t_end: float) -> dict:
    """Apply the agent's audit_query to the captured log. An entry is a VALID audit
    entry for an operation iff it (a) falls in the time window, (b) corresponds to that
    operation (matched by method+path), and (c) has every required field non-null with
    user_id == filter_user_id and timestamp within the tolerance of the op's wall time.

    Because the winston request-log lacks user_id/action_type/resource_id, no entry is
    ever valid against DummyJSON => count_valid = 0 (the honest finding). The raw
    candidate count is recorded for the report.
    """
    aq = plan.get("audit_query") if isinstance(plan, dict) else None
    queried = isinstance(aq, dict) and bool(aq)
    if not queried:
        return {"queried": False, "by_op": {}, "count_valid": 0,
                "all_fields_nonnull": False, "user_scoped": False,
                "candidate_lines": 0, "detail": []}

    required = aq.get("required_fields") or auditlog_spec.REQUIRED_FIELDS
    filter_uid = aq.get("filter_user_id")
    before = float(aq.get("window_before_seconds", auditlog_spec.WINDOW_BEFORE_S))
    after = float(aq.get("window_after_seconds", auditlog_spec.WINDOW_AFTER_S))
    tol = float(aq.get("timestamp_tolerance_seconds", auditlog_spec.TIMESTAMP_TOLERANCE_S))

    lo, hi = t_start - before, t_end + after
    entries = _parse_log_entries()

    by_op = {}
    valid_entries = []
    candidate_lines = 0
    detail = []

    for op in op_log:
        method = (op.get("method") or "").upper()
        path = op.get("path") or ""
        wall = op.get("wall_ts")
        # candidate log lines: same method+url within the window
        cands = []
        for e in entries:
            ep = _log_epoch(e)
            if ep is None or not (lo <= ep <= hi):
                continue
            meta = e.get("meta", {}) if isinstance(e.get("meta"), dict) else {}
            if (e.get("method") or "").upper() == method and meta.get("url") == path:
                cands.append((e, ep))
        candidate_lines += len(cands)

        present = len(cands) > 0
        fields_complete = False
        ts_within = False
        user_match = False
        chosen = None
        for e, ep in cands:
            field_vals = {f: _audit_field(e, f) for f in required}
            complete = all(field_vals.get(f) is not None for f in required)
            within = (wall is not None and abs(ep - wall) <= tol)
            umatch = (field_vals.get("user_id") == filter_uid) if "user_id" in required else True
            if complete and within and umatch:
                chosen = field_vals
                fields_complete = within = user_match = True
                valid_entries.append({"op": op["label"], **field_vals})
                break
            # record best-effort signal even when invalid (for the report)
            fields_complete = fields_complete or complete
            ts_within = ts_within or within
            user_match = user_match or umatch

        by_op[op["label"]] = {"present": present, "fields_complete": fields_complete,
                              "ts_within": ts_within, "user_match": user_match,
                              "candidate_lines": len(cands)}
        detail.append({"op": op["label"], "method": method, "path": path,
                       "candidate_lines": len(cands),
                       "valid_audit_entry": chosen is not None,
                       "missing_fields": [f for f in required
                                          if (cands and _audit_field(cands[0][0], f) is None)]
                                         if cands else list(required)})

    count_valid = len(valid_entries)
    all_nonnull = (count_valid == auditlog_spec.EXPECTED_ENTRY_COUNT)
    user_scoped = (count_valid >= 1 and all(v.get("user_id") == filter_uid for v in valid_entries))

    return {"queried": True, "by_op": by_op, "count_valid": count_valid,
            "all_fields_nonnull": all_nonnull, "user_scoped": user_scoped,
            "candidate_lines": candidate_lines, "detail": detail,
            "expected_entry_count": aq.get("expected_entry_count")}


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
def run_auditlog_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the audit-verification plan object (see auditlog_spec): a
        dict with `operations` (create/update/delete) and `audit_query`. The harness
        authenticates, executes the AGENT's planned operations in order, captures the
        target's log, queries it per audit_query, and evaluates every scenario.
        Whatever the agent fails to emit scores as 'missing'. generate may raise;
        recorded per-collection.
    """
    token = authenticate()
    cfgs = collection_cfgs()
    all_cases = []
    observed_by_collection = {}
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        op_obs, op_log, t_start, t_end, rid = _exec_ops(cfg, plan, token)
        audit_obs = _query_audit(plan, op_log, t_start, t_end)
        observed = auditlog_spec.evaluate(op_obs, audit_obs)
        observed_by_collection[cfg["collection"]] = observed

        scenarios = []
        for label in auditlog_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = auditlog_spec.correct(label, tok)
            scenarios.append({"collection": cfg["collection"], "scenario": label,
                              "ideal": auditlog_spec.IDEAL[label], "observed_token": tok,
                              "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"collection": cfg["collection"], "test_user_id": cfg["test_user_id"],
                          "emitted_plan": plan, "resource_id": rid, "op_log": op_log,
                          "audit_query_result": audit_obs, "scenarios": scenarios,
                          "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=cfg["collection"].strip("/").replace("/", "-") or "root",
            item_label=cfg["collection"],
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

    cov = auditlog_spec.coverage(observed_by_collection)
    correctness_rate = round(100.0 * correct / total, 2) if total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "authenticated": token is not None,
           "audit_log_coverage_rate_pct": cov["rate_pct"],
           "audit_correctness_rate_pct": correctness_rate,
           "coverage_cases": cov,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "collections": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, cov["rate_pct"], str(cases_path), extra={
        "audit_log_coverage_rate_pct": cov["rate_pct"],
        "audit_correctness_rate_pct": correctness_rate,
        "scenarios_total": total})

    everos_note(agent, f"audit-log-verification run: coverage_rate={cov['rate_pct']}% "
                       f"({cov['covered']}/{cov['total']} auditable ops) over "
                       f"{len(cfgs)} collections ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline Audit
    Log Coverage Rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "verify-audit-log-generation" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "audit_log_coverage_rate_pct"),
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
