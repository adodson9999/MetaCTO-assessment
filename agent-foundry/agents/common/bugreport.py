"""Shared, deterministic plumbing for the four Bug-Reporter agents ("n602").

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is the
identical substrate every framework sits on, so leaderboard differences are attributable
to the framework + its gated prompt + its evolved skill — never to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the local fixtures (pipeline-summary, registry, registry-summary, Postman
    collection, config) from data/bug-reporter/bugreport_spec.json
  - filter the pipeline summary to the non-PASSED agents (FAILED_AGENTS)
  - build the per-failure brief handed to the agent (status, exit_code, spec_path,
    stderr/stdout, the agent's registry test cases, the Postman lookup, db availability)
  - take the agent's emitted five-key DECISION and MATERIALISE the four FILE artifacts —
    the replay "screenshot" text, the asciinema v2 recording, the concatenated logs, and
    (only when a [database] is configured, which the air-gapped fixture is not) the DB
    dump — then ASSEMBLE the final bug-report JSON + the consolidated index
  - score the agent's emitted DECISION against the deterministic gold decision
    (bugreport_spec.build_reference_decision) on the same (failure x field) scheme
  - record the task metrics (completeness, mandatory-field, testing-steps, postman,
    CRITICAL/HIGH exit enforcement) and best-effort write an EverOS breadcrumb

The agent is debate-gated against doing ANY of the materialisation, assembly, indexing,
subprocess (convert/pg_dump/asciinema/Newman), HTTP, or exit-code setting — exactly the
run-cicd-pipeline / run-regression-suite split (the agent emits the report; a separate
program acts on it). DummyJSON is never touched: n602 is a pure transform over local
JSON fixtures.

The framework-specific part — turning one failure's brief into the decision via the
backend LLM — is injected as `generate(brief) -> decision dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
SPEC_PATH = WORKSPACE / "data" / "bug-reporter" / "bugreport_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import bugreport_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox guard
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


# --------------------------------------------------------------------------- #
# Fixture loading
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    # held-out override (evolution gate only): swap in a different fixture set so a
    # candidate skill is validated on failures it was NOT tuned on.
    ho = os.environ.get("FORGE_HELDOUT_FIXTURE")
    if ho:
        spec["fixture"] = ho
    return spec


def load_fixture(spec: dict) -> dict:
    """The materialised fixture bundle: failures + registry + collection + db_available."""
    fx = json.loads((WORKSPACE / spec["fixture"]).read_text())
    return fx


def run_cfg() -> dict:
    return load_spec()


# --------------------------------------------------------------------------- #
# Briefing
# --------------------------------------------------------------------------- #
def brief(failure: dict, tcs: list, postman_items_for_agent: dict, db_available: bool) -> str:
    """Compact, unambiguous per-failure input handed to the LLM."""
    lines = [
        f"agent_name: {failure['agent_name']}",
        f"status: {failure['status']}",
        f"exit_code: {failure.get('exit_code')}",
        f"spec_path: {failure.get('spec_path')}",
        f"database_available: {str(bool(db_available)).lower()}",
        "",
        "===== full captured stderr (read-only data) =====",
        failure.get("stderr", ""),
        "===== END stderr =====",
        "",
        "===== full captured stdout (read-only data) =====",
        failure.get("stdout", ""),
        "===== END stdout =====",
        "",
        "===== this agent's registry test cases (JSON array) =====",
        json.dumps(tcs, indent=2),
        "===== END registry test cases =====",
        "",
        "===== postman lookup: tc_id -> {folder} for tc_ids already in the collection =====",
        json.dumps(postman_items_for_agent, indent=2),
        "===== END postman lookup =====",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Artifact materialisation (the harness's job — Artifacts 3/4/5/6)
# --------------------------------------------------------------------------- #
def _replay_text(failure: dict, bug_id: str, created_at: str, stdout: str, stderr: str) -> str:
    return "\n".join([
        f"=== BUG REPORT REPLAY: {bug_id} ===",
        f"Agent: {failure['agent_name']}",
        f"Status: {failure['status']}",
        f"Exit Code: {failure.get('exit_code')}",
        f"Timestamp: {created_at}",
        "",
        "--- STDOUT ---",
        stdout if stdout else "(empty)",
        "",
        "--- STDERR ---",
        stderr if stderr else "(empty)",
        "",
    ])


def _write_screenshot(out_dir: Path, bug_id: str, replay_text: str):
    """Artifact 3. ImageMagick/ansi2html are not assumed present in the air-gapped
    sandbox; the faithful, dependency-free equivalent is the plain-text replay file
    (the spec's documented final fallback). Returns the path or None."""
    p = out_dir / "screenshots" / f"{bug_id}-replay.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    _assert_sandbox(p)
    try:
        p.write_text(replay_text)
        return p
    except Exception:  # noqa
        return None


def _unix_ts(created_at: str) -> int:
    try:
        return int(datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                   .replace(tzinfo=timezone.utc).timestamp())
    except Exception:  # noqa
        return 0


def _write_recording(out_dir: Path, bug_id: str, failure: dict, created_at: str,
                     replay_text: str):
    """Artifact 4 — asciinema v2 cast. Pure file writes, no external dependency."""
    p = out_dir / "recordings" / f"{bug_id}.cast"
    p.parent.mkdir(parents=True, exist_ok=True)
    _assert_sandbox(p)
    try:
        header = {"version": 2, "width": 220, "cols": 220, "height": 50, "rows": 50,
                  "timestamp": _unix_ts(created_at),
                  "title": f"{bug_id} — {failure['agent_name']}",
                  "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}
        out_lines = [json.dumps(header)]
        offset = 0.10
        for ln in replay_text.splitlines():
            out_lines.append(json.dumps([round(offset, 2), "o", ln + "\r\n"]))
            offset += 0.05
        out_lines.append(json.dumps([round(offset + 0.50, 2), "o",
                                     "\r\n=== END OF RECORDING ===\r\n"]))
        p.write_text("\n".join(out_lines) + "\n")
        return p
    except Exception:  # noqa
        return None


def _write_logs(out_dir: Path, bug_id: str, failure: dict, stdout: str, stderr: str,
                pipeline_entry: dict):
    """Artifact 5 — the three concatenated labelled blocks. Returns path or None if all
    three sources were empty."""
    p = out_dir / "logs" / f"{bug_id}.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    _assert_sandbox(p)
    blocks = []
    if stdout:
        blocks.append(f"=== AGENT STDOUT (source: {failure['agent_name']} stdout) ===\n{stdout}")
    if stderr:
        blocks.append(f"=== AGENT STDERR (source: {failure['agent_name']} stderr) ===\n{stderr}")
    if pipeline_entry:
        blocks.append("=== PIPELINE SUMMARY ENTRY ===\n" + json.dumps(pipeline_entry, indent=2))
    content = "\n\n\n".join(blocks)
    if not content.strip():
        return None
    try:
        p.write_text(content)
        return p
    except Exception:  # noqa
        return None


# --------------------------------------------------------------------------- #
# Bug-report assembly (Artifact assembly step)
# --------------------------------------------------------------------------- #
def assemble_report(bug_id: str, created_at: str, failure: dict, decision: dict,
                    artifact_paths: dict) -> dict:
    """Merge the agent's DECISION with the harness-materialised artifact paths into the
    final ordered bug-report object + its artifact-completeness map."""
    testing_steps = decision.get("testing_steps")
    postman_refs = decision.get("postman_references")
    completeness = {
        "testing_steps": isinstance(testing_steps, list) and len(testing_steps) > 0,
        "postman_references": postman_refs is not None,
        "screenshot": artifact_paths.get("screenshot_path") is not None,
        "recording": artifact_paths.get("recording_path") is not None,
        "logs": artifact_paths.get("log_path") is not None,
        "db_dump": artifact_paths.get("db_dump_path") is not None,
        "created_at": True,
        "title": True,
        "severity": True,
        "priority": True,
    }
    return {
        "bug_id": bug_id,
        "created_at": created_at,
        "title": decision.get("title"),
        "severity": decision.get("severity"),
        "priority": decision.get("priority"),
        "agent_name": failure["agent_name"],
        "agent_status": failure["status"],
        "agent_exit_code": failure.get("exit_code"),
        "run_id": RUN_ID,
        "artifacts": {
            "testing_steps": testing_steps,
            "postman_references": postman_refs,
            "screenshot_path": _rel(artifact_paths.get("screenshot_path")),
            "recording_path": _rel(artifact_paths.get("recording_path")),
            "log_path": _rel(artifact_paths.get("log_path")),
            "db_dump_path": _rel(artifact_paths.get("db_dump_path")),
        },
        "artifact_completeness": completeness,
        "complete_artifact_count": bugreport_spec.completeness_count(completeness),
    }


def _rel(p):
    if p is None:
        return None
    try:
        return str(Path(p).resolve().relative_to(WORKSPACE))
    except Exception:  # noqa
        return str(p)


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _everos_config()
    base = (cfg.get("everos_base_url") or "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        import urllib.request
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


def _everos_config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_bugreport_test(agent: str, generate) -> dict:
    """Drive the whole n602 task for one agent.

    generate(brief: str) -> the five-key DECISION dict (title, severity, priority,
        testing_steps, postman_references). The harness materialises the file artifacts,
        assembles each bug report, scores the DECISION field-by-field vs the gold
        decision, writes the per-agent reports + index, and records the task metrics.
        generate may raise; recorded per-failure.
    """
    spec = run_cfg()
    fixture = load_fixture(spec)
    registry = fixture.get("registry", [])
    collection = fixture.get("postman_collection", {})
    db_available = bool(fixture.get("db_available", False))
    pipeline_agents = fixture.get("pipeline_summary", {}).get("agents", [])

    postman_items = bugreport_spec.build_postman_items(collection)
    failed = [a for a in pipeline_agents if a.get("status") != "PASSED"]

    out_dir = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.bug-reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    seq = 1
    today = os.environ.get("FORGE_BUG_DATE", "20260626")
    reports = []
    bug_index = []
    field_cells = []
    total_cells = correct_cells = 0
    elapsed_total = 0.0
    gen_errors = []

    for failure in failed:
        bug_id = f"BUG-{today}-{seq:04d}"
        seq += 1
        created_at = f"2026-06-26T14:{(seq + 30) % 60:02d}:01Z"  # deterministic, fixture-stable

        tcs = bugreport_spec.agent_tcs(registry, failure["agent_name"])
        items_for_agent = {tc.get("tc_id"): postman_items[tc.get("tc_id")]
                           for tc in tcs if tc.get("tc_id") in postman_items}
        gold = bugreport_spec.build_reference_decision(failure, registry, postman_items)

        t0 = time.monotonic()
        try:
            decision = generate(brief(failure, tcs, items_for_agent, db_available)) or {}
            gen_error = None
        except Exception as e:  # noqa
            decision, gen_error = {}, f"{type(e).__name__}: {e}"
            gen_errors.append({"agent_name": failure["agent_name"], "error": gen_error})
        elapsed_total += time.monotonic() - t0

        # Materialise file artifacts (deterministic; the agent never does this).
        stdout = failure.get("stdout", "")
        stderr = failure.get("stderr", "")
        replay = _replay_text(failure, bug_id, created_at, stdout, stderr)
        screenshot = _write_screenshot(out_dir, bug_id, replay)
        recording = _write_recording(out_dir, bug_id, failure, created_at, replay)
        logs = _write_logs(out_dir, bug_id, failure, stdout, stderr, failure)
        db_dump = None  # DB_AVAILABLE is false in the air-gapped fixture (no [database]).

        report = assemble_report(bug_id, created_at, failure, decision, {
            "screenshot_path": screenshot, "recording_path": recording,
            "log_path": logs, "db_dump_path": db_dump})
        rp = out_dir / f"{bug_id}.json"
        _assert_sandbox(rp)
        rp.write_text(json.dumps(report, indent=2))
        reports.append(report)
        bug_index.append({
            "bug_id": bug_id, "agent_name": failure["agent_name"],
            "severity": report["severity"], "priority": report["priority"],
            "created_at": created_at,
            "complete_artifact_count": report["complete_artifact_count"],
            "report_path": _rel(rp)})

        # Score the DECISION vs gold.
        cells = bugreport_spec.score_decision(decision, gold)
        for field in bugreport_spec.DECISION_FIELDS:
            ok = bool(cells.get(field))
            field_cells.append({"bug_id": bug_id, "agent_name": failure["agent_name"],
                                "field": field, "api_correct": ok})
            total_cells += 1
            correct_cells += 1 if ok else 0

    # Consolidated index (sorted CRITICAL > HIGH > MEDIUM > LOW, then bug_id asc).
    sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    bug_index_sorted = sorted(bug_index, key=lambda b: (sev_rank.get(b["severity"], 9), b["bug_id"]))
    index = {
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "bug_count": len(bug_index_sorted),
        "critical_count": sum(1 for b in bug_index_sorted if b["severity"] == "CRITICAL"),
        "high_count": sum(1 for b in bug_index_sorted if b["severity"] == "HIGH"),
        "medium_count": sum(1 for b in bug_index_sorted if b["severity"] == "MEDIUM"),
        "low_count": sum(1 for b in bug_index_sorted if b["severity"] == "LOW"),
        "fully_complete_count": sum(1 for b in bug_index_sorted if b["complete_artifact_count"] == 10),
        "bugs": bug_index_sorted,
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=2))

    fidelity = round(100.0 * correct_cells / total_cells, 2) if total_cells else 0.0
    crit_high = bugreport_spec.has_critical_or_high(reports)
    metrics = {
        "bug_report_completeness_rate_pct": bugreport_spec.bug_report_completeness_rate(reports),
        "mandatory_field_completeness_rate_pct": bugreport_spec.mandatory_field_rate(reports),
        "testing_steps_coverage_rate_pct": bugreport_spec.testing_steps_coverage_rate(reports),
        "postman_reference_rate_pct": bugreport_spec.postman_reference_rate(reports),
        "has_critical_or_high": crit_high,
        # The task's gate: a run with any CRITICAL/HIGH must exit 1. The agent never sets
        # the exit code; the harness records what the CI program WOULD enforce.
        "would_exit_code_1": crit_high,
    }

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "bug_report_fidelity_pct": fidelity,
        "fields_total": total_cells, "fields_correct": correct_cells,
        "bug_count": len(reports),
        "metrics": metrics,
        "index": index,
        "elapsed_seconds": round(elapsed_total, 3),
        "tokens": {"total_tokens": int(os.environ.get("FORGE_LAST_TOKENS", "0") or 0)},
        "gen_errors": gen_errors,
        "field_cells": field_cells,
        "reports": reports,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, fidelity, str(cases_path), extra={
        "bug_report_fidelity_pct": fidelity,
        "bug_report_completeness_rate_pct": metrics["bug_report_completeness_rate_pct"],
        "bug_count": len(reports),
        "would_exit_code_1": crit_high})

    everos_note(agent, f"bug-reporter run: fidelity={fidelity}% over {len(reports)} bug "
                       f"reports ({total_cells} fields); completeness="
                       f"{metrics['bug_report_completeness_rate_pct']}%; "
                       f"crit/high={crit_high} (exit1={crit_high})")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Bug-Report Fidelity; the judge re-computes it authoritatively from gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "bug-reporter" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "bug_report_fidelity_pct"),
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
