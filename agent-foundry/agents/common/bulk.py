"""Shared, deterministic plumbing for the four test-bulk-operation-endpoints agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing. In particular, the batch CONSTRUCTION + SENDING + DB-query logic
lives here, so all four agents exercise the bulk endpoint the exact same way; what
differs is only the PLAN each agent emitted.

Responsibilities (all deterministic, no LLM):
  - load the run config from data/test-bulk-operation-endpoints/bulk_spec.json
  - build the compact brief handed to the agent
  - execute whatever plan the agent emitted:
      * mixed batch : valid_count valid items + 1 missing-required + 1 wrong-type,
        POSTed as one JSON array to the bulk endpoint
      * all-invalid : ten independently-invalid items
      * oversize    : oversize_count valid items (> max batch size)
  - query the SQLite DB FILE directly (the task's "psql/mysql CLI" step) for the
    before/after counts within this run/agent's scope
  - evaluate every scenario (shared bulk_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is never touched: it exposes no bulk endpoints, so the entire bulk test
runs against the separate, purpose-built local SQLite target. The harness sends an
X-Bulk-Scope header so the four agents can run in parallel against one DB without
their row counts colliding.

The framework-specific part — turning the brief into the bulk test plan via the
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
SPEC_PATH = WORKSPACE / "data" / "test-bulk-operation-endpoints" / "bulk_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import bulk_spec  # noqa: E402


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
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    spec["base_url"] = os.environ.get("FORGE_BULK_BASE_URL", spec["base_url"]).rstrip("/")
    # held-out VARIANT overrides (used only by the SkillOpt evolution gate) so a
    # candidate skill is validated on a config it was NOT tuned on, without editing
    # the spec file. Absent in normal runs.
    ho_ep = os.environ.get("FORGE_HELDOUT_ENDPOINT")
    if ho_ep:
        spec["endpoint"] = ho_ep
    ho_mf = os.environ.get("FORGE_HELDOUT_MISSING_FIELD")
    if ho_mf:
        spec["missing_field"] = ho_mf
    ho_vc = os.environ.get("FORGE_HELDOUT_VALID_COUNT")
    if ho_vc:
        spec["valid_count"] = int(ho_vc)
        spec["expected_db_delta"] = int(ho_vc)
    return spec


def run_cfg() -> dict:
    return load_spec()


def brief(cfg: dict) -> str:
    """Compact, unambiguous bulk contract handed to the LLM."""
    req = ", ".join(f"{f['name']}:{f['type']}" for f in cfg["required_fields"])
    return "\n".join([
        f"endpoint: {cfg['endpoint']}   # the documented bulk POST path",
        f"max_batch_size: {cfg['max_batch_size']}   # items beyond this are rejected",
        f"required_fields: {req}   # every item must carry these with these JSON types",
        f"valid_item_template: {json.dumps(cfg['valid_item_template'])}   # '[N]' is replaced by the item number",
        f"valid_count: {cfg['valid_count']}   # number of fully-valid items in the mixed batch",
        f"missing_field: {cfg['missing_field']}   # required field the missing-required item omits",
        f"wrongtype_field: {cfg['wrongtype_field']}   # required string field the wrong-type item corrupts",
        f"wrongtype_value: {json.dumps(cfg['wrongtype_value'])}   # the integer placed in wrongtype_field",
        f"oversize_count: {cfg['oversize_count']}   # item count for the over-the-limit batch",
        f"expected_batch_status: {cfg['expected_batch_status']}",
        f"expected_valid_item_status: {cfg['expected_valid_item_status']}",
        f"expected_invalid_item_status: {cfg['expected_invalid_item_status']}",
        f"expected_oversize_status: {cfg['expected_oversize_status']}",
        f"expected_db_delta: {cfg['expected_db_delta']}",
    ])


# --------------------------------------------------------------------------- #
# HTTP (deterministic) — one POST of a JSON array, returns (status, parsed_body)
# --------------------------------------------------------------------------- #
def _post_array(url: str, items: list, scope: str, timeout: float = 60.0):
    _assert_local_target(url)
    body = json.dumps(items).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "X-Bulk-Scope": scope})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:  # 4xx/5xx still carry a body
        raw = e.read()
        status = e.code
    except Exception:  # noqa  -- connection error/timeout
        return -1, None
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:  # noqa
        parsed = None
    return status, parsed


def _db_count(cfg: dict, scope: str) -> int:
    p = _db_path(cfg)
    if not p.exists():
        return 0
    conn = sqlite3.connect(str(p), timeout=10.0)
    try:
        conn.execute("PRAGMA busy_timeout=10000;")
        cur = conn.execute(
            f"SELECT COUNT(*) FROM {cfg['db_table']} WHERE scope = ?", (scope,))
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _db_reset_scope(cfg: dict, scope: str) -> None:
    p = _db_path(cfg)
    if not p.exists():
        return
    conn = sqlite3.connect(str(p), timeout=10.0)
    try:
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute(f"DELETE FROM {cfg['db_table']} WHERE scope = ?", (scope,))
        conn.commit()
    finally:
        conn.close()


def _db_path(cfg: dict) -> Path:
    raw = os.environ.get("BULK_DB_PATH") or str(WORKSPACE / cfg["db_path"])
    return Path(raw).resolve()


# --------------------------------------------------------------------------- #
# Plan execution
# --------------------------------------------------------------------------- #
def _send_batch(cfg: dict, scope: str, items: list) -> dict:
    """POST one batch, bracketing it with direct DB counts. Returns the observation
    dict bulk_spec.evaluate expects."""
    url = f"{cfg['base_url']}{cfg['endpoint']}"
    before = _db_count(cfg, scope)
    status, parsed = _post_array(url, items, scope)
    after = _db_count(cfg, scope)
    return {"batch_status": status,
            "results": parsed if isinstance(parsed, list) else [],
            "db_before": before, "db_after": after, "url": url}


def _exec_plan(agent: str, cfg: dict, plan: dict) -> tuple[dict, dict, dict, dict]:
    """Execute the AGENT's plan. Tolerant of missing/malformed keys — a plan that
    omits a key falls back to nothing, and the corresponding scenarios score
    'missing'. The endpoint is always taken from the trusted spec (never from agent
    text) to keep the harness pinned to the one local target."""
    plan = plan if isinstance(plan, dict) else {}
    # endpoint/max_batch_size are enforced from the spec, not agent-controlled, so a
    # bad plan can never redirect traffic off the local target.
    eff = dict(plan)
    eff["endpoint"] = cfg["endpoint"]
    eff.setdefault("valid_item_template", cfg["valid_item_template"])
    eff.setdefault("valid_count", cfg["valid_count"])
    eff.setdefault("missing_field", cfg["missing_field"])
    eff.setdefault("wrongtype_field", cfg["wrongtype_field"])
    eff.setdefault("wrongtype_value", cfg["wrongtype_value"])
    eff.setdefault("oversize_count", cfg["oversize_count"])

    base_scope = f"{RUN_ID}:{agent}"

    mixed_obs = allinvalid_obs = oversize_obs = {}
    reqlog: dict = {}

    # --- mixed batch ---
    try:
        items = bulk_spec.build_mixed_batch(eff)
        scope = base_scope + ":mixed"
        _db_reset_scope(cfg, scope)
        mixed_obs = _send_batch(cfg, scope, items)
        reqlog["mixed"] = {"items_sent": len(items),
                           "batch_status": mixed_obs["batch_status"],
                           "db_before": mixed_obs["db_before"],
                           "db_after": mixed_obs["db_after"]}
    except Exception as e:  # noqa
        reqlog["mixed_error"] = f"{type(e).__name__}: {e}"

    # --- all-invalid batch ---
    try:
        items = bulk_spec.build_all_invalid_batch(eff)
        scope = base_scope + ":allinvalid"
        _db_reset_scope(cfg, scope)
        allinvalid_obs = _send_batch(cfg, scope, items)
        reqlog["all_invalid"] = {"items_sent": len(items),
                                 "batch_status": allinvalid_obs["batch_status"],
                                 "db_delta": allinvalid_obs["db_after"] - allinvalid_obs["db_before"]}
    except Exception as e:  # noqa
        reqlog["all_invalid_error"] = f"{type(e).__name__}: {e}"

    # --- oversize batch ---
    try:
        items = bulk_spec.build_oversize_batch(eff)
        scope = base_scope + ":oversize"
        _db_reset_scope(cfg, scope)
        oversize_obs = _send_batch(cfg, scope, items)
        reqlog["oversize"] = {"items_sent": len(items),
                              "batch_status": oversize_obs["batch_status"],
                              "db_delta": oversize_obs["db_after"] - oversize_obs["db_before"]}
    except Exception as e:  # noqa
        reqlog["oversize_error"] = f"{type(e).__name__}: {e}"

    return mixed_obs, allinvalid_obs, oversize_obs, reqlog


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
def run_bulk_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the bulk plan object (see bulk_spec). The harness
    constructs the three batches from the plan, POSTs each to the local bulk
    endpoint, queries the DB directly, and evaluates every scenario. Whatever the
    agent fails to emit scores as 'missing'. generate may raise; recorded.
    """
    cfg = run_cfg()
    try:
        plan = generate(cfg) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    mixed_obs, allinvalid_obs, oversize_obs, reqlog = _exec_plan(agent, cfg, plan)
    # the effective plan values used for evaluation (spec fallbacks applied)
    eff = {**{k: cfg[k] for k in ("valid_count", "missing_field", "wrongtype_field")},
           **{k: v for k, v in plan.items() if k in ("valid_count", "missing_field", "wrongtype_field")}}
    observed = bulk_spec.evaluate(mixed_obs, allinvalid_obs, oversize_obs, eff)

    scenarios = []
    total = correct = 0
    for label in bulk_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = bulk_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": bulk_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    headline = bulk_spec.bulk_operation_accuracy(mixed_obs, allinvalid_obs, oversize_obs, eff)
    rate = headline["accuracy_pct"]

    raw = {
        "agent": agent, "run_id": RUN_ID, "target": cfg["base_url"],
        "endpoint": cfg["endpoint"],
        "bulk_operation_accuracy_pct": rate,
        "cases_passed": headline["cases_passed"], "cases_total": headline["cases_total"],
        "per_case": headline["per_case"],
        "mixed_db_delta": (mixed_obs.get("db_after", 0) - mixed_obs.get("db_before", 0))
        if mixed_obs else None,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "emitted_plan": plan, "request_log": reqlog,
        "scenarios": scenarios, "error": gen_error,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "bulk_operation_accuracy_pct": rate,
        "scenarios_total": total,
        "mixed_db_delta": raw["mixed_db_delta"]})

    everos_note(agent, f"bulk-operation-endpoints run: accuracy={rate}% "
                       f"(cases_passed={headline['cases_passed']}/{headline['cases_total']}, "
                       f"mixed_db_delta={raw['mixed_db_delta']})")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Bulk Operation Accuracy; the judge later overwrites metric_value with
    fidelity-to-gold for ranking."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-bulk-operation-endpoints" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "bulk_operation_accuracy_pct"),
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
