"""Shared, deterministic plumbing for the four CRUD-integrity-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It
is the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill, never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the resource list (+ create/update fixtures) from data/crud/openapi.json
  - build a compact, unambiguous per-resource brief for the LLM
  - execute the agent's emitted 8-step plan against the LOCAL target only
    (sandbox + host guard): send each step, capture the created id, substitute the
    {RESOURCE_ID} placeholder, and perform the read-only direct DB reads
  - record every step's real HTTP code + body echo, and every DB checkpoint's state
  - compute the headline CRUD Integrity Rate (strict task expectations)
  - emit the result JSON for the judge
  - best-effort write a breadcrumb to the shared EverOS memory pool

The framework-specific part — turning one resource brief into the plan via the
backend LLM — is injected as `generate(resource) -> dict`.
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
TARGET_REPO = WORKSPACE.parent
DB_DIR = (TARGET_REPO / "database").resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
# DummyJSON enforces 100 requests / 10s per IP (src/middleware/rate-limiter.js, no env
# toggle). A naive CRUD sweep trips 429s, so we pace requests and retry on 429 to
# observe the TRUE CRUD behavior — exactly what a real suite (Newman/REST-Assured)
# would do. DummyJSON itself is never modified.
REQ_DELAY_S = float(os.environ.get("FORGE_REQ_DELAY_S", "0.15"))
RL_RETRIES = int(os.environ.get("FORGE_RL_RETRIES", "6"))
RL_BACKOFF_S = float(os.environ.get("FORGE_RL_BACKOFF_S", "10.5"))

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import crud_spec  # noqa: E402
from contract import extract_json  # noqa: E402  (reuse the robust JSON extractor)


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
def load_resources() -> list[dict]:
    spec = json.loads((WORKSPACE / "data" / "crud" / "openapi.json").read_text())
    by_slug: dict[str, dict] = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            slug = op.get("x-crud-resource")
            if not slug:
                continue
            by_slug[slug] = {
                "slug": slug,
                "table": op.get("x-crud-table", slug),
                "add_path": path,
                "base_path": "/" + slug,
                "auth_required": False,
                "create_body": op.get("x-crud-create-body", {}),
                "update_body": op.get("x-crud-update-body", {}),
            }
    out = [by_slug[s] for s in spec.get("x-crud-resources", []) if s in by_slug]
    only = os.environ.get("FORGE_ONLY_SLUGS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [o for o in out if o["slug"] in wanted]
    return out


def resource_brief(resource: dict) -> str:
    lines = [f"resource_name: {resource['slug']}",
             f"database_table: {resource['table']}",
             f"base_path: {resource['base_path']}",
             f"create_path: {resource['add_path']}",
             f"auth_required: {str(resource['auth_required']).lower()}",
             f"create_body: {json.dumps(resource['create_body'])}",
             f"update_body: {json.dumps(resource['update_body'])}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# HTTP + read-only direct DB read
# --------------------------------------------------------------------------- #
def _headers(auth: str, token: str | None) -> dict:
    h = {"Content-Type": "application/json"}
    if auth == "valid" and token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _send_once(url: str, data, method: str, auth: str, token) -> tuple[int, object]:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=_headers(auth, token))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            try:
                return r.getcode(), json.loads(raw)
            except Exception:  # noqa
                return r.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:  # noqa
            return e.code, None
    except Exception:  # noqa
        return -1, None


def send(method: str, path: str, body, auth: str = "none",
         token: str | None = None) -> tuple[int, object]:
    url = TARGET_BASE_URL + (path if path.startswith("/") else "/" + path)
    _assert_local_target(url)
    data = json.dumps(body).encode() if body is not None else None
    m = (method or "GET").upper()
    if REQ_DELAY_S > 0:
        time.sleep(REQ_DELAY_S)
    code, resp = _send_once(url, data, m, auth, token)
    # retry past the rate-limit window so 429 noise never lands in a recorded result
    attempts = 0
    while code == 429 and attempts < RL_RETRIES:
        time.sleep(RL_BACKOFF_S)
        attempts += 1
        code, resp = _send_once(url, data, m, auth, token)
    return code, resp


def db_read(table: str, resource_id) -> str:
    """Read-only direct query of database/<table>.json for one id. The deliberate,
    narrowly-scoped, READ-ONLY exception the task requires. Returns the db_state:
    "present" | "absent" | "no_store"."""
    if not isinstance(table, str) or not table:
        return "no_store"
    f = (DB_DIR / f"{table}.json").resolve()
    if DB_DIR not in f.parents or f.suffix != ".json" or not f.exists():
        return "no_store"
    try:
        rows = json.loads(f.read_text())
    except Exception:  # noqa
        return "no_store"
    if not isinstance(rows, list):
        return "no_store"
    if resource_id is None:
        return "absent"
    for row in rows:
        if isinstance(row, dict) and str(row.get("id")) == str(resource_id):
            return "present"
    return "absent"


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
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


# --------------------------------------------------------------------------- #
# Execute one resource's plan and compute integrity
# --------------------------------------------------------------------------- #
def _exec_resource(resource: dict, plan: dict) -> dict:
    norm = crud_spec.iter_agent_plan(plan)
    by_step = {s["step"]: s for s in norm["steps"]}
    table = norm["table"] if isinstance(norm["table"], str) and norm["table"] else resource["table"]
    create_body = resource["create_body"]
    post_update_state = crud_spec.expected_post_update(resource)

    resource_id = None
    step_records, db_records = [], []

    for name in crud_spec.STEP_ORDER:
        desc = by_step.get(name)
        if desc is None:
            step_records.append({"step": name, "covered": False, "method": None,
                                 "sent_path": None, "actual_code": None,
                                 "body_field_match": None, "captured_id": None})
        else:
            raw_path = desc.get("path") or ""
            path = raw_path.replace(crud_spec.ID_PLACEHOLDER,
                                    str(resource_id) if resource_id is not None
                                    else crud_spec.ID_PLACEHOLDER)
            code, resp = send(desc.get("method"), path, desc.get("body"),
                              desc.get("auth", "none"))
            if name == "CREATE" and isinstance(resp, dict):
                resource_id = resp.get("id")
            body_match = None
            if name == "CREATE":
                body_match = crud_spec.subset_matches(create_body, resp)
            elif name in ("UPDATE", "READ_AFTER_UPDATE"):
                body_match = crud_spec.subset_matches(post_update_state, resp)
            step_records.append({"step": name, "covered": True,
                                 "method": desc.get("method"), "sent_path": path,
                                 "actual_code": code, "body_field_match": body_match,
                                 "captured_id": resource_id if name == "CREATE" else None})

        if name in ("CREATE", "READ", "UPDATE"):
            chk = {"CREATE": "DB_AFTER_CREATE", "READ": "DB_AFTER_READ",
                   "UPDATE": "DB_AFTER_UPDATE"}[name]
            db_records.append({"checkpoint": chk, "resource_id": resource_id,
                               "db_state": db_read(table, resource_id)})

    db_records.append({"checkpoint": "DB_FINAL", "resource_id": resource_id,
                       "db_state": db_read(table, resource_id)})

    integrity = _integrity(step_records, db_records)
    return {"slug": resource["slug"], "table": table,
            "steps": step_records, "db_checkpoints": db_records,
            "integrity_pass": integrity}


def _integrity(steps: list, dbs: list) -> bool:
    by_step = {s["step"]: s for s in steps}
    by_db = {d["checkpoint"]: d for d in dbs}
    for name, exp in crud_spec.STRICT_EXPECT.items():
        if name == "DB_FINAL":
            continue
        s = by_step.get(name)
        if not s or not s.get("covered"):
            return False
        if s["actual_code"] not in exp["code"]:
            return False
        if s["body_field_match"] is False:
            return False
    for chk in ("DB_AFTER_CREATE", "DB_AFTER_READ", "DB_AFTER_UPDATE"):
        d = by_db.get(chk)
        if not d or d["db_state"] != "present":
            return False
    final = by_db.get("DB_FINAL")
    return bool(final and final["db_state"] == "absent")


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_crud_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(resource: dict) -> the agent's plan {"table":..,"steps":[...]}. The
    harness executes the agent's plan per resource, captures the created id, sends
    each step to the local target, performs the read-only DB reads, and records the
    real outcomes. A step the agent omitted is recorded covered=False (counts against
    fidelity). generate may raise; recorded as a per-resource generation error.
    """
    resources = load_resources()
    results = []
    passed = 0

    for resource in resources:
        try:
            plan = generate(resource) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"
        rec = _exec_resource(resource, plan)
        rec["gen_error"] = gen_error
        results.append(rec)
        passed += int(rec["integrity_pass"])

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=rec["slug"],
            item_label=f"CRUD {rec['slug']} (table={rec['table']}, integrity_pass={rec['integrity_pass']})",
            step_results=[
                {
                    "assertion_result": (
                        "PASS" if s.get("covered") and s.get("body_field_match") is not False
                        else "FAIL"
                    ),
                    "assertion_detail": (
                        f"step={s.get('step')} method={s.get('method')} "
                        f"path={s.get('sent_path')} code={s.get('actual_code')} "
                        f"covered={s.get('covered')} body_field_match={s.get('body_field_match')}"
                    ),
                    **s,
                }
                for s in rec["steps"]
            ],
        )

    total = len(resources)
    rate = round(100.0 * passed / total, 2) if total else 0.0
    covered_cells = sum(1 for r in results for s in r["steps"] if s["covered"])

    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "crud_integrity_rate_pct": rate,
           "resource_types": total, "resource_types_passing": passed,
           "covered_step_cells": covered_cells, "resources": results}
    run_dir = WORKSPACE / "results" / "crud" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path),
         extra={"crud_integrity_rate_pct": rate, "resource_types": total,
                "resource_types_passing": passed, "covered_step_cells": covered_cells})
    everos_note(agent, f"crud-integrity run: rate={rate}% passing={passed}/{total} "
                       f"covered_steps={covered_cells} over {total} resources")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str,
         extra: dict | None = None) -> None:
    """Write results/crud/runs/<run>/<agent>.json. metric_value here is the headline
    CRUD Integrity Rate; the judge later overwrites metric_value with CRUD-Test
    Fidelity."""
    metric = {}
    mp = WORKSPACE / "judge" / "crud" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "crud" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("headline_metric", "crud_integrity_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))
