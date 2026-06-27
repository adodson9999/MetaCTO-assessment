"""Shared, deterministic plumbing for the four Measure-API-Consumer-Satisfaction agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is the
identical substrate every framework sits on, so leaderboard differences are attributable
to the framework + its gated prompt + its evolved skill — never to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the documented NPS-survey-measurement contract + the active dataset's gold
    tokens from data/measure-api-consumer-satisfaction/nps_spec.json
  - build the compact contract brief handed to the agent (carries NO seeded answers)
  - execute whatever plan the agent emitted: query the LOCAL seeded usage fixture
    (tools/satisfaction-fixture) for the 90-day-active recipients, select the collected
    responses inside the plan's window, and compute the dashboard (band counts, integer
    round-half-up NPS, validity gate, TF-IDF + k-means themes) deterministically
  - evaluate every scenario (shared nps_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The fixture is a read-only seeded SQLite usage DB + collected survey responses; the
harness only SELECTs from it and never mutates it. DummyJSON is never contacted or
modified by this task.

The framework-specific part — turning the documented contract into the JSON measurement
plan via the backend LLM — is injected as `generate(brief) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
DATASET = os.environ.get("FORGE_NPS_DATASET", "current")
SPEC_PATH = WORKSPACE / "data" / "measure-api-consumer-satisfaction" / "nps_spec.json"
GOLD_PATH = WORKSPACE / "data" / "measure-api-consumer-satisfaction" / "gold.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
sys.path.insert(0, str(WORKSPACE / "tools" / "satisfaction-fixture"))
import nps_spec  # noqa: E402
import seed as fixture  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox guard
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


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


def contract_brief(spec: dict) -> str:
    """Compact, unambiguous documented contract handed to the LLM. Carries the contract
    the agent must render as a plan — NO seeded recipients, responses, counts, or answers."""
    c = spec["contract"]
    qs = "\n".join(
        f'    - id={q["id"]} type={q["type"]} text="{q["text"]}"' for q in c["survey_questions"])
    return (
        "recipient_window_days: the distinct users with >=1 API call in the last N days; N = "
        f"{c['recipient_window_days']}\n"
        f"collection_window_days: responses collected for N days after Day-1 send (close Day {c['collection_window_days'] + 1}); N = {c['collection_window_days']}\n"
        "survey_questions (exactly these four, in order, verbatim):\n"
        f"{qs}\n"
        f"score_bands: promoter={c['score_bands']['promoter']} passive={c['score_bands']['passive']} detractor={c['score_bands']['detractor']} (inclusive score ranges)\n"
        f"nps_formula: {c['nps_formula']} (integer, round half up)\n"
        f"validity_min_response_rate_pct: results valid only if response rate >= {c['validity_min_response_rate_pct']}%\n"
        f"clustering: {json.dumps(c['clustering'])} (k-means over TF-IDF of combined open-text; top-3 clusters; <=5-word labels)\n"
        f"dashboard_fields (exactly these, in order): {c['dashboard_fields']}"
    )


# --------------------------------------------------------------------------- #
# Local seeded usage fixture (read-only) — recipients + collected responses
# --------------------------------------------------------------------------- #
def _fixture_inputs(plan: dict):
    """Query the seeded usage DB for the 90-day-active recipients using the PLAN's
    recipient_window_days, and return (recipients, all_responses, survey_period).

    Faithful to the spec's `SELECT DISTINCT user_id FROM api_request_logs WHERE
    timestamp >= NOW() - INTERVAL '<window>' days` — expressed against the deterministic
    day_offset column. Read-only; never mutates the fixture."""
    import sqlite3
    # Strict: an unpinned/invalid recipient window selects NO recipients, so an empty
    # plan diverges from gold rather than inheriting the canonical 90-day default.
    window = plan.get("recipient_window_days")
    window = window if isinstance(window, int) and window > 0 else -1

    db_path = WORKSPACE / "tools" / "satisfaction-fixture" / f"usage_{DATASET}.db"
    _assert_sandbox(db_path)
    fixture.build_db(db_path, DATASET)   # idempotent rebuild of the read-only fixture

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.execute(
            "SELECT DISTINCT user_id FROM api_request_logs "
            "WHERE day_offset >= 0 AND day_offset <= ? ORDER BY user_id", (window,))
        recipients = [row[0] for row in cur.fetchall()]
        cur = con.execute(
            "SELECT user_id, score, submit_day, painpoint, improvement, other "
            "FROM survey_responses")
        responses = [{"user_id": r[0], "score": r[1], "submit_day": r[2],
                      "painpoint": r[3], "improvement": r[4], "other": r[5]}
                     for r in cur.fetchall()]
    finally:
        con.close()
    period = fixture.survey_period(DATASET, window)
    return recipients, responses, period


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
# Gold tokens (for the per-scenario api_correct flag in the recorded cases)
# --------------------------------------------------------------------------- #
def _gold_tokens() -> dict:
    try:
        gold = json.loads(GOLD_PATH.read_text())
    except Exception:  # noqa
        return {}
    for ds in gold.get("datasets", []):
        if ds.get("dataset") == DATASET:
            return {s["scenario"]: s["observed_token"] for s in ds["scenarios"]}
    return {}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_nps_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(brief: str) -> the measurement plan object (see nps_spec.build_reference_plan):
        a dict with the eight plan keys. The harness executes the AGENT's plan against the
        local seeded fixture (read-only) and evaluates every scenario. Whatever the agent
        fails to emit scores as 'missing'. generate may raise; recorded.
    """
    spec = load_spec()
    brief = contract_brief(spec)
    try:
        plan = generate(brief) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    recipients, responses, period = _fixture_inputs(plan if isinstance(plan, dict) else {})
    dashboard = nps_spec.compute_dashboard(plan if isinstance(plan, dict) else {},
                                           recipients, responses, period)
    observed = nps_spec.evaluate(plan if isinstance(plan, dict) else {}, dashboard)
    gold_tokens = _gold_tokens()

    scenarios = []
    total = correct = 0
    for label in nps_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = nps_spec.correct(label, tok, gold_tokens)
        scenarios.append({"scenario": label,
                          "ideal": nps_spec.ideal_for(label, gold_tokens),
                          "observed_token": tok, "plan_correct": ok})
        total += 1
        correct += 1 if ok else 0

    # G1 staging write — write per-item findings for G1b orchestration
    _write_staging_findings(
        agent=agent,
        item_id=str(DATASET).strip().replace("/", "-").replace(" ", "-") or "dataset",
        item_label=f"NPS dataset={DATASET}",
        step_results=[
            {
                "assertion_result": "PASS" if s.get("plan_correct") else "FAIL",
                "assertion_detail": (
                    f"scenario={s.get('scenario')} ideal={s.get('ideal')} "
                    f"observed={s.get('observed_token')}"
                ),
                **s,
            }
            for s in scenarios
        ],
    )

    plan_accuracy = round(100.0 * correct / total, 2) if total else 0.0
    nps_score = dashboard.get("nps_score")
    raw = {"agent": agent, "run_id": RUN_ID, "dataset": DATASET,
           "nps_score": nps_score, "plan_accuracy_pct": plan_accuracy,
           "scenarios_total": total, "scenarios_correct": correct,
           "emitted_plan": plan, "dashboard": dashboard, "gen_error": gen_error,
           "scenarios": scenarios}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    # Headline emit = the business KPI (NPS score). The judge later overwrites
    # metric_value with NPS-Measurement Plan Fidelity-to-gold.
    emit(agent, nps_score if isinstance(nps_score, (int, float)) else 0, str(cases_path),
         extra={"nps_score": nps_score, "plan_accuracy_pct": plan_accuracy,
                "statistical_validity": dashboard.get("statistical_validity"),
                "response_rate_pct": dashboard.get("response_rate_pct")})

    everos_note(agent, f"nps run [{DATASET}]: nps={nps_score} "
                       f"validity={dashboard.get('statistical_validity')} "
                       f"plan_accuracy={plan_accuracy}% ({correct}/{total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline NPS
    score; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "measure-api-consumer-satisfaction" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "nps_score"),
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
