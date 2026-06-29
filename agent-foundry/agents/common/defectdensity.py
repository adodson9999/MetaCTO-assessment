"""Shared, deterministic plumbing for the four defect-density-reporting agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the sprint fixtures from data/track-defect-density/defectdensity_spec.json
  - build the compact per-sprint brief handed to the agent
  - run whatever report the agent emitted through the shared field comparator vs the
    deterministic gold reference (agents/common/defectdensity_spec.build_reference_record)
  - record per (sprint, field) correctness, compute Report Accuracy, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

Fully air-gapped: no Jira, no Git, no network target. DummyJSON is irrelevant to this
task and is never contacted or modified.

The framework-specific part — turning one sprint's brief into the report via the
backend LLM — is injected as `generate(cfg) -> report dict`.
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
SPEC_PATH = WORKSPACE / "data" / "track-defect-density" / "defectdensity_spec.json"
GOLD_PATH = WORKSPACE / "data" / "track-defect-density" / "gold.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import defectdensity_spec as ddspec  # noqa: E402


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
# Fixture loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def sprint_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for s in spec["sprints"]:
        out.append({
            "sprint_name": s["sprint_name"],
            "jira_issues": s["jira_issues"],
            "diff_numstat": s["diff_numstat"],
            "prev_density_1": s["prev_density_1"],
            "prev_density_2": s["prev_density_2"],
            "prev_density_3": s["prev_density_3"],
        })
    only = os.environ.get("FORGE_ONLY_SPRINTS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [c for c in out if c["sprint_name"] in wanted]
    return out


def sprint_brief(cfg: dict) -> str:
    """Compact, unambiguous defect + code-change brief handed to the LLM."""
    issues = json.dumps(cfg["jira_issues"], separators=(",", ":"))
    return "\n".join([
        f"sprint_name: {cfg['sprint_name']}",
        f"jira_issues: {issues}",
        "diff_numstat: |",
        *[f"  {line}" for line in cfg["diff_numstat"].splitlines()],
        f"prev_density_1: {cfg['prev_density_1']}   # most recent preceding sprint",
        f"prev_density_2: {cfg['prev_density_2']}",
        f"prev_density_3: {cfg['prev_density_3']}",
    ])


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
def run_defectdensity_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the dashboard report object: a dict with the ten keys
        sprint_name, defect_density, rolling_avg_3_sprint, deviation_pct, alert_flag,
        p1_count..p4_count, trend. The harness computes the gold record itself and
        scores the emitted report field-by-field. Whatever the agent fails to emit
        scores as a field mismatch. generate may raise; recorded per-sprint.
    """
    cfgs = sprint_cfgs()
    all_cases = []
    total = correct = 0

    for cfg in cfgs:
        try:
            emitted = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            emitted, gen_error = {}, f"{type(e).__name__}: {e}"

        gold = ddspec.build_reference_record(cfg)
        checks = ddspec.evaluate(emitted, gold)

        fields = []
        for field in ddspec.FIELDS:
            ok = checks[field]
            fields.append({"sprint": cfg["sprint_name"], "field": field,
                           "gold": gold[field],
                           "emitted": emitted.get(field) if isinstance(emitted, dict) else None,
                           "correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"sprint": cfg["sprint_name"], "emitted_report": emitted,
                          "gold_record": gold, "fields": fields, "error": gen_error})

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(cfg["sprint_name"]).strip().replace("/", "-").replace(" ", "-") or "sprint",
            item_label=str(cfg["sprint_name"]),
            step_results=[
                {
                    "assertion_result": "PASS" if f.get("correct") else "FAIL",
                    "assertion_detail": (
                        f"field={f.get('field')} gold={f.get('gold')} "
                        f"emitted={f.get('emitted')}"
                    ),
                    **f,
                }
                for f in fields
            ],
        )

    rate = round(100.0 * correct / total, 2) if total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID,
           "defect_density_report_accuracy_pct": rate,
           "fields_total": total, "fields_correct": correct,
           "sprints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "defect_density_report_accuracy_pct": rate,
        "fields_total": total})

    everos_note(agent, f"track-defect-density run: report_accuracy={rate}% "
                       f"over {len(cfgs)} sprints ({total} fields)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    report-accuracy; the judge later overwrites it with accuracy-vs-gold (same number,
    judge-authoritative)."""
    metric = {}
    mp = WORKSPACE / "judge" / "track-defect-density" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "defect_density_report_accuracy_pct"),
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
