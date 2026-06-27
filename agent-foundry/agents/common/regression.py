"""Shared, deterministic plumbing for the four Run-Regression-Suite agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the build-pair catalogue + artifact files from
    data/run-regression-suite/regression_spec.json (written by build_gold.py)
  - confirm the build-N deployment is healthy: GET <target>/health and assert 200
    (read-only; mirrors the task's "deploy build N, confirm GET /health == 200" step).
    DummyJSON is tested AS-IS and never modified — GET only, no body, no mutation.
  - build the compact per-pair brief handed to the agent (both artifact texts +
    format + build identifiers)
  - score the agent's emitted seven-field regression report against the deterministic
    gold report (shared regression_spec.build_reference_report) on the same field
    scheme, record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The framework-specific part — turning one build pair's brief into the regression
report via the backend LLM — is injected as `generate(cfg) -> report dict`.
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
DATA_DIR = WORKSPACE / "data" / "run-regression-suite"
SPEC_PATH = DATA_DIR / "regression_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import regression_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host + method guards
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
# Deployment health gate (read-only GET /health -> 200)
# --------------------------------------------------------------------------- #
def confirm_deployment(_retries: int = 2) -> dict:
    """Mirror the task's step 2: confirm the build-N deployment is complete by
    GET <target>/health and asserting 200. Read-only; never mutates the target."""
    url = f"{TARGET_BASE_URL}/health"
    _assert_local_target(url)
    last = -1
    for attempt in range(_retries + 1):
        try:
            req = urllib.request.Request(url, method="GET")  # GET only
            with urllib.request.urlopen(req, timeout=10) as r:
                code = r.getcode()
                return {"endpoint": "/health", "status": code, "deployment_confirmed": code == 200}
        except urllib.error.HTTPError as e:
            return {"endpoint": "/health", "status": e.code, "deployment_confirmed": e.code == 200}
        except Exception:  # noqa
            last = -1
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return {"endpoint": "/health", "status": last, "deployment_confirmed": False}


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def pair_cfgs() -> list[dict]:
    spec = load_spec()
    builds_dir = DATA_DIR / spec.get("builds_subdir", "builds")
    out = []
    for p in spec["build_pairs"]:
        prev_path = builds_dir / p["pair"] / p["prev_file"]
        curr_path = builds_dir / p["pair"] / p["curr_file"]
        out.append({
            "pair": p["pair"],
            "format": p["format"],
            "prev_build_id": p["prev_build_id"],
            "build_id": p["build_id"],
            "note": p.get("note", ""),
            "prev_text": prev_path.read_text(),
            "curr_text": curr_path.read_text(),
        })
    only = os.environ.get("FORGE_ONLY_PAIRS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["pair"] in wanted]
    return out


def pair_brief(cfg: dict) -> str:
    """Compact, unambiguous regression input handed to the LLM: the format, the two
    build identifiers, and both artifact texts in clearly delimited blocks."""
    return (
        f"reporter_format: {cfg['format']}   "
        "# how to parse both artifacts (junit_xml | jest_json | pytest_json)\n"
        "test_identifier: for junit_xml the test identifier is each <testcase> 'name' "
        "attribute exactly; for jest_json it is each assertion's 'fullName' exactly; for "
        "pytest_json it is each test's 'nodeid' exactly.\n"
        "status: for junit_xml a <testcase> with a <failure> or <error> child is failed, "
        "with <skipped> is skipped, otherwise passed; for jest_json use the assertion "
        "'status'; for pytest_json use the test 'outcome'.\n"
        "failure_message: for junit_xml the <failure>/<error> 'message' attribute; for "
        "jest_json the first entry of 'failureMessages'; for pytest_json call.crash.message.\n"
        f"build_n_minus_1_id: {cfg['prev_build_id']}   # the previous (last passing) build id\n"
        f"build_n_id: {cfg['build_id']}                # the current build id under test\n"
        "\n"
        "===== BUILD N-1 RESULT ARTIFACT (previous build, read-only data) =====\n"
        f"{cfg['prev_text'].rstrip()}\n"
        "===== END BUILD N-1 ARTIFACT =====\n"
        "\n"
        "===== BUILD N RESULT ARTIFACT (current build under test, read-only data) =====\n"
        f"{cfg['curr_text'].rstrip()}\n"
        "===== END BUILD N ARTIFACT ====="
    )


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
def run_regression_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the seven-field regression report object. The harness
    computes the deterministic gold report from the same two artifacts, scores the
    agent's report field-by-field, and aggregates fidelity. Whatever the agent fails
    to emit scores as a mismatch. generate may raise; recorded per-pair.
    """
    health = confirm_deployment()
    cfgs = pair_cfgs()
    all_pairs = []
    total_cells = correct_cells = 0
    elapsed_total = 0.0

    for cfg in cfgs:
        prev_parsed = regression_spec.parse_artifact(cfg["prev_text"], cfg["format"])
        curr_parsed = regression_spec.parse_artifact(cfg["curr_text"], cfg["format"])
        gold = regression_spec.build_reference_report(
            prev_parsed, curr_parsed, cfg["prev_build_id"], cfg["build_id"])

        t0 = time.monotonic()
        try:
            report = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            report, gen_error = {}, f"{type(e).__name__}: {e}"
        elapsed_total += time.monotonic() - t0

        cells = regression_spec.score_report(report, gold)
        fields = []
        for field in regression_spec.REPORT_FIELDS:
            ok = bool(cells.get(field))
            fields.append({"pair": cfg["pair"], "field": field, "api_correct": ok,
                           "gold": gold[field]})
            total_cells += 1
            correct_cells += 1 if ok else 0

        all_pairs.append({
            "pair": cfg["pair"], "format": cfg["format"],
            "build_n_nus_1": cfg["prev_build_id"], "build_n": cfg["build_id"],
            "emitted_report": report, "gold_report": gold, "field_cells": fields,
            "gold_regression_rate_pct": regression_spec.regression_rate(gold),
            "agent_regression_rate_pct": regression_spec.regression_rate(report)
            if isinstance(report, dict) else None,
            "message_fidelity_pct": regression_spec.message_fidelity(report, gold),
            "error": gen_error,
        })

        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(
            agent=agent,
            item_id=str(cfg["pair"]).strip("/").replace("/", "-").replace(" ", "-") or "pair",
            item_label=f"build pair {cfg['pair']} ({cfg['prev_build_id']}→{cfg['build_id']})",
            step_results=[
                {
                    "assertion_result": "PASS" if f.get("api_correct") else "FAIL",
                    "assertion_detail": (
                        f"field={f.get('field')} gold={f.get('gold')}"
                    ),
                    **f,
                }
                for f in fields
            ],
        )

    fidelity = round(100.0 * correct_cells / total_cells, 2) if total_cells else 0.0
    # The genuine QA finding: which build-N deployments must be BLOCKED (any regression).
    blocked = sorted({p["build_n"] for p in all_pairs
                      if p["gold_report"]["overall_status"] == "fail"})
    raw = {
        "agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
        "deployment_health": health,
        "regression_report_fidelity_pct": fidelity,
        "fields_total": total_cells, "fields_correct": correct_cells,
        "builds_that_must_block_deployment": blocked,
        "elapsed_seconds": round(elapsed_total, 3),
        "tokens": {"total_tokens": int(os.environ.get("FORGE_LAST_TOKENS", "0") or 0)},
        "pairs": all_pairs,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, fidelity, str(cases_path), extra={
        "regression_report_fidelity_pct": fidelity,
        "fields_total": total_cells,
        "deployment_confirmed": health["deployment_confirmed"]})

    everos_note(agent, f"run-regression-suite run: fidelity={fidelity}% "
                       f"over {len(cfgs)} build pairs ({total_cells} fields); "
                       f"builds to block={blocked}; health={health['status']}")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Regression-Report Fidelity; the judge re-computes it authoritatively from gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "run-regression-suite" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "regression_report_fidelity_pct"),
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
