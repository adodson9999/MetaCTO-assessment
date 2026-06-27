"""Shared, deterministic plumbing for the four soft-delete-behavior agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing. In particular, the *soft-delete lifecycle execution itself* lives
here (POST -> record T_DELETE -> DELETE -> GET-by-id -> collection scan -> direct
SQLite query -> include_deleted), so all four agents exercise the contract the exact
same way; what differs is only the PLAN each agent emitted.

Responsibilities (all deterministic, no LLM):
  - load the run config from data/test-soft-delete-behavior/softdelete_spec.json
  - build the compact brief handed to the agent
  - execute whatever plan the agent emitted across `case_count` resource lifecycles:
      * POST a known, per-(run,agent,case)-namespaced body
      * confirm the new id is in GET /resources
      * record T_DELETE (wall clock) immediately before DELETE
      * DELETE /resources/<id>
      * GET /resources/<id>  (expect 404, body must not leak the posted field values)
      * GET /resources        (the deleted id must be absent)
      * query the SQLite DB FILE directly (the task's psql/mysql step) for the surviving
        row, deleted_at, is_deleted, and the |deleted_at - T_DELETE| <= tolerance check
      * GET /resources?include_deleted=true (the deleted id must reappear w/ deleted_at)
  - evaluate every scenario (shared softdelete_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is NOT touched and NOT used: every request goes to the local, purpose-built
soft-delete target (tools/softdelete_target/app.py), which is the only endpoint that
can satisfy the DB-row / deleted_at / collection-exclusion assertions.

The framework-specific part — turning the brief into the soft-delete test plan via the
backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
SPEC_PATH = WORKSPACE / "data" / "test-soft-delete-behavior" / "softdelete_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import softdelete_spec  # noqa: E402


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
    spec = json.loads(SPEC_PATH.read_text())
    spec["base_url"] = os.environ.get("FORGE_BASE_URL", spec["base_url"]).rstrip("/")
    # held-out VARIANT overrides (used only by the SkillOpt evolution gate) so a
    # candidate skill is validated on a config it was NOT tuned on, without editing the
    # spec file. Absent in normal runs.
    ho_cc = os.environ.get("FORGE_HELDOUT_CASE_COUNT")
    if ho_cc:
        spec["case_count"] = int(ho_cc)
    ho_ep = os.environ.get("FORGE_HELDOUT_RESOURCE_ENDPOINT")
    if ho_ep:
        spec["resource_endpoint"] = ho_ep
    ho_tol = os.environ.get("FORGE_HELDOUT_TOLERANCE_S")
    if ho_tol:
        spec["deleted_at_tolerance_s"] = int(ho_tol)
    return spec


def run_cfg() -> dict:
    return load_spec()


def brief(cfg: dict) -> str:
    """Compact, unambiguous soft-delete contract handed to the LLM."""
    de = cfg.get("delete_expected_status", [200, 204])
    return "\n".join([
        f"resource_endpoint: {cfg['resource_endpoint']}   # collection path; POST here to create, GET here to list",
        f"create_fields: {json.dumps(cfg.get('create_fields', {}))}   # known field name/value pairs to POST in each create body",
        f"id_field: {cfg.get('id_field', 'id')}   # JSON field carrying the created resource id in the POST response",
        f"delete_expected_status: {json.dumps(de)}   # the DELETE call must return one of these codes",
        f"get_deleted_expected_status: {cfg.get('get_deleted_expected_status', 404)}   # GET of the deleted resource by id must return exactly this",
        f"include_deleted_param: {cfg.get('include_deleted_param', 'include_deleted=true')}   # query string that re-includes soft-deleted rows in the listing",
        f"db_table: {cfg['db_table']}",
        f"db_id_column: {cfg.get('db_id_column', 'id')}",
        f"db_deleted_at_column: {cfg.get('db_deleted_at_column', 'deleted_at')}",
        f"db_is_deleted_column: {cfg.get('db_is_deleted_column', 'is_deleted')}",
        f"deleted_at_tolerance_s: {cfg.get('deleted_at_tolerance_s', softdelete_spec.DELETED_AT_TOLERANCE_S)}   # max seconds between the DELETE call and the stored deleted_at",
        f"case_count: {cfg.get('case_count', softdelete_spec.CASE_COUNT)}   # number of independent create->delete->verify lifecycles to run",
    ])


# --------------------------------------------------------------------------- #
# HTTP primitives (stdlib; local-only) — deterministic
# --------------------------------------------------------------------------- #
def _request(method: str, url: str, body: dict | None = None, timeout: float = 30.0):
    """Return (status:int, parsed_json|None, raw_text:str). status -1 on transport error."""
    _assert_local_target(url)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:  # 4xx/5xx are real answers, not failures
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        status = e.code
    except Exception:  # noqa  -- transport failure
        return -1, None, ""
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:  # noqa
        parsed = None
    return status, parsed, raw


# --------------------------------------------------------------------------- #
# Direct DB query (the task's psql/mysql step) — read the SQLite file directly
# --------------------------------------------------------------------------- #
def _db_path(cfg: dict) -> Path:
    raw = os.environ.get("SOFTDELETE_DB_PATH") or str(WORKSPACE / cfg["db_path"])
    return Path(raw).resolve()


def _db_row(cfg: dict, dbq: dict, rid: str) -> dict:
    """SELECT id, deleted_at, is_deleted FROM <table> WHERE <id_col> = ?.
    Returns {row_count, deleted_at, is_deleted_raw}."""
    p = _db_path(cfg)
    table = dbq.get("table", cfg["db_table"])
    id_col = dbq.get("id_column", cfg.get("db_id_column", "id"))
    del_col = dbq.get("deleted_at_column", cfg.get("db_deleted_at_column", "deleted_at"))
    flag_col = dbq.get("is_deleted_column", cfg.get("db_is_deleted_column", "is_deleted"))
    out = {"row_count": 0, "deleted_at": None, "is_deleted_raw": None}
    if not p.exists():
        return out
    conn = sqlite3.connect(str(p), timeout=10.0)
    try:
        conn.execute("PRAGMA busy_timeout=10000;")
        cur = conn.execute(
            f"SELECT {id_col}, {del_col}, {flag_col} FROM {table} WHERE {id_col} = ?",
            (rid,))
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return out
    finally:
        conn.close()
    out["row_count"] = len(rows)
    if rows:
        out["deleted_at"] = rows[0][1]
        out["is_deleted_raw"] = rows[0][2]
    return out


def _within_tolerance(deleted_at: str | None, t_delete: float, tol_s: float) -> bool:
    if not deleted_at:
        return False
    try:
        dt = datetime.fromisoformat(deleted_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return abs(dt.timestamp() - t_delete) <= tol_s
    except Exception:  # noqa
        return False


def _is_deleted_true(raw) -> bool:
    """Interpret the DB is_deleted column as a boolean true (1 / "1" / true / "true")."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return int(raw) == 1
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "t")
    return False


# --------------------------------------------------------------------------- #
# Plan execution — run case_count lifecycles
# --------------------------------------------------------------------------- #
def _exec_plan(agent: str, cfg: dict, plan: dict) -> tuple[list, dict]:
    """Execute the AGENT's plan. Tolerant of missing/malformed keys — whatever the
    agent omits simply does not get exercised and scores as 'missing'.
    Returns (case_results, request_log)."""
    plan = plan if isinstance(plan, dict) else {}
    base = cfg["base_url"]
    case_count = _to_int(plan.get("case_count")) or cfg.get("case_count", softdelete_spec.CASE_COUNT)
    tol_s = cfg.get("deleted_at_tolerance_s", softdelete_spec.DELETED_AT_TOLERANCE_S)

    create = plan.get("create") if isinstance(plan.get("create"), dict) else {}
    delete = plan.get("delete") if isinstance(plan.get("delete"), dict) else {}
    get_deleted = plan.get("get_deleted") if isinstance(plan.get("get_deleted"), dict) else {}
    collection = plan.get("collection") if isinstance(plan.get("collection"), dict) else {}
    dbq = plan.get("db_query") if isinstance(plan.get("db_query"), dict) else {}
    include = plan.get("include_deleted") if isinstance(plan.get("include_deleted"), dict) else {}
    if "deleted_at_within_seconds" in dbq:
        tol_s = _to_int(dbq.get("deleted_at_within_seconds")) or tol_s

    create_ep = create.get("endpoint")
    coll_ep = collection.get("endpoint")
    incl_ep = include.get("endpoint")
    incl_q = include.get("query", cfg.get("include_deleted_param", "include_deleted=true"))
    base_fields = create.get("fields") if isinstance(create.get("fields"), dict) else {}

    case_results: list = []
    log: list = []

    for i in range(case_count):
        case: dict = {}
        rlog: dict = {"case": i}

        # ---- CREATE ----
        rid = None
        posted_values: list = []
        if create_ep:
            # namespace field values per (run, agent, case) so they are unique + traceable
            ns = f"{RUN_ID}:{agent}:{i}"
            body = {}
            for k, v in base_fields.items():
                val = f"{v}-{ns}" if isinstance(v, str) else v
                body[k] = val
                if isinstance(val, str):
                    posted_values.append(val)
            st, parsed, _ = _request("POST", base + create_ep, body)
            case["create_status"] = st
            if isinstance(parsed, dict):
                rid = parsed.get(cfg.get("id_field", "id"))
            rlog["create"] = {"status": st, "id": rid}

        # ---- APPEARS BEFORE DELETE (collection scan) ----
        if coll_ep and rid is not None:
            ids = _collection_ids(base + coll_ep)
            case["appears_before"] = rid in ids

        # ---- T_DELETE + DELETE ----
        if delete and rid is not None:
            tmpl = delete.get("path_template", "")
            del_path = tmpl.replace("{RESOURCE_ID}", str(rid))
            t_delete = time.time()
            st, _, _ = _request("DELETE", base + del_path)
            case["delete_status"] = st
            rlog["delete"] = {"path": del_path, "status": st, "t_delete": t_delete}
        else:
            t_delete = time.time()

        # ---- GET BY ID (expect 404, no field-value leak) ----
        if get_deleted and rid is not None:
            tmpl = get_deleted.get("path_template", "")
            g_path = tmpl.replace("{RESOURCE_ID}", str(rid))
            st, _, raw = _request("GET", base + g_path)
            case["get_by_id_status"] = st
            case["get_by_id_no_leak"] = not any(v in raw for v in posted_values) if posted_values else (raw == "" or st == 404)
            rlog["get_by_id"] = {"path": g_path, "status": st}

        # ---- ABSENT FROM COLLECTION ----
        if coll_ep and rid is not None:
            ids = _collection_ids(base + coll_ep)
            case["absent_from_collection"] = rid not in ids

        # ---- DIRECT DB QUERY ----
        if dbq and rid is not None:
            row = _db_row(cfg, dbq, str(rid))
            case["db_row_count"] = row["row_count"]
            case["db_deleted_at"] = row["deleted_at"]
            case["db_within_10s"] = _within_tolerance(row["deleted_at"], t_delete, tol_s)
            case["db_is_deleted"] = _is_deleted_true(row["is_deleted_raw"])
            rlog["db"] = row

        # ---- INCLUDE DELETED ----
        if incl_ep and rid is not None:
            url = base + incl_ep + ("?" + incl_q if incl_q else "")
            st, parsed, _ = _request("GET", url)
            present = False
            if isinstance(parsed, dict):
                for item in parsed.get("resources", []):
                    if isinstance(item, dict) and item.get(cfg.get("id_field", "id")) == rid:
                        present = item.get("deleted_at") not in (None, "", "NULL")
                        break
            case["include_deleted_status"] = st
            case["include_deleted_present"] = present
            rlog["include_deleted"] = {"status": st, "present": present}

        case_results.append(case)
        log.append(rlog)

    return case_results, {"cases": log, "case_count": case_count, "tolerance_s": tol_s}


def _collection_ids(url: str) -> set:
    st, parsed, _ = _request("GET", url)
    ids = set()
    if isinstance(parsed, dict):
        for item in parsed.get("resources", []):
            if isinstance(item, dict) and "id" in item:
                ids.add(item["id"])
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and "id" in item:
                ids.add(item["id"])
    return ids


def _to_int(v):
    try:
        return int(v)
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
def run_softdelete_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the soft-delete plan object (see softdelete_spec): a dict
        with case_count + the create/delete/get_deleted/collection/db_query/
        include_deleted descriptors. The harness executes the AGENT's plan over
        case_count lifecycles, queries the DB directly, and evaluates every scenario.
        Whatever the agent fails to emit scores as 'missing'. generate may raise;
        recorded.
    """
    cfg = run_cfg()
    try:
        plan = generate(cfg) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    case_count = _to_int(plan.get("case_count")) or cfg.get("case_count", softdelete_spec.CASE_COUNT)
    case_results, reqlog = _exec_plan(agent, cfg, plan)
    observed = softdelete_spec.evaluate(case_results, case_count)
    ideal = softdelete_spec.ideal_for(case_count)

    scenarios = []
    total = correct = 0
    for label in softdelete_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = softdelete_spec.correct(label, tok, ideal)
        scenarios.append({"scenario": label, "ideal": ideal[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    # G1 staging write — write per-item findings for G1b orchestration
    _write_staging_findings(
        agent=agent,
        item_id=str(cfg.get("resource_endpoint", "softdelete")).strip("/").replace("/", "-") or "softdelete",
        item_label=f"soft-delete {cfg.get('resource_endpoint', '')} (case_count={case_count})",
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

    headline = softdelete_spec.success_rate(case_results, case_count)
    rate = headline["rate_pct"]

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "target": cfg["base_url"], "case_count": case_count,
        "soft_delete_correctness_rate_pct": rate,
        "correct_cases": headline["correct_cases"], "total_cases": headline["total_cases"],
        "scenarios_total": total, "scenarios_api_correct": correct,
        "emitted_plan": plan, "request_log": reqlog,
        "case_results": case_results,
        "scenarios": scenarios, "error": gen_error,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "soft_delete_correctness_rate_pct": rate,
        "scenarios_total": total,
        "correct_cases": headline["correct_cases"]})

    everos_note(agent, f"soft-delete-behavior run: correctness_rate={rate}% "
                       f"(correct_cases={headline['correct_cases']}/{headline['total_cases']}, "
                       f"scenarios_ok={correct}/{total})")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline Soft
    Delete Correctness Rate; the judge later overwrites metric_value with
    fidelity-to-gold for ranking."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-soft-delete-behavior" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "soft_delete_correctness_rate_pct"),
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
