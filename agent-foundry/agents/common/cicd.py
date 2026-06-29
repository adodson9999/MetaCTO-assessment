"""Shared, deterministic plumbing for the four CI/CD-Pipeline-Runner agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the scenario catalogue + per-agent captured artifacts from
    data/run-cicd-pipeline/cicd_spec.json (written by build_gold.py)
  - probe the Ollama backend read-only: GET <ollama>/api/tags and record whether it
    returned 200 (mirrors the task's step-4 server health check). This is READ-ONLY;
    this build NEVER starts the Ollama server, installs Ollama, pulls a model, or
    spawns the test agents — those are the CI harness's job and are debate-gated out of
    the agent (cicd_prompt L12).
  - build the compact per-run brief handed to the agent (the [backend] block, the
    manifest, and each listed agent's exit_code/timed_out/captured stdout)
  - score the agent's emitted ten-field pipeline-summary against the deterministic gold
    summary (cicd_spec.build_reference_summary) on the same field scheme, record, emit
  - best-effort write a breadcrumb to the shared EverOS memory pool

The framework-specific part — turning one pipeline run's brief into the summary via the
backend LLM — is injected as `generate(cfg) -> summary dict`.
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
# The Ollama backend the task runs against. Probed READ-ONLY; never started here.
OLLAMA_BASE_URL = os.environ.get("FORGE_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DATA_DIR = WORKSPACE / "data" / "run-cicd-pipeline"
SPEC_PATH = DATA_DIR / "cicd_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import cicd_spec  # noqa: E402


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
# Ollama backend health probe (read-only GET /api/tags; NEVER starts the server)
# --------------------------------------------------------------------------- #
def probe_ollama() -> dict:
    """Mirror the task's step 4: confirm the Ollama server is up by GET
    <ollama>/api/tags and recording whether it returned 200. READ-ONLY; this build
    never starts the server (the agent is forbidden from doing so, and the harness only
    probes). Non-fatal: scoring is against the local fixtures, not the live server."""
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        _assert_local_target(url)
    except PermissionError:
        return {"endpoint": "/api/tags", "status": -1, "server_up": False, "note": "non-local"}
    try:
        req = urllib.request.Request(url, method="GET")  # GET only; never starts anything
        with urllib.request.urlopen(req, timeout=5) as r:
            code = r.getcode()
            return {"endpoint": "/api/tags", "status": code, "server_up": code == 200}
    except urllib.error.HTTPError as e:
        return {"endpoint": "/api/tags", "status": e.code, "server_up": e.code == 200}
    except Exception:  # noqa - server not running; we do NOT start it
        return {"endpoint": "/api/tags", "status": -1, "server_up": False}


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def run_cfgs() -> list[dict]:
    spec = load_spec()
    out = list(spec["scenarios"])
    only = os.environ.get("FORGE_ONLY_SCENARIOS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["scenario"] in wanted]
    return out


def run_brief(cfg: dict) -> str:
    """Compact, unambiguous pipeline-run input handed to the LLM: the backend block,
    the run metadata, the full manifest, and one execution record per listed agent in
    clearly delimited blocks."""
    backend = cfg["backend"]
    lines = [
        "[backend] configuration block (read-only):",
        f"  provider = {backend.get('provider')!r}",
        f"  model    = {backend.get('model')!r}",
        f"resolved model_digest (from `ollama list`): {cfg['model_digest']}",
        f"run_id:    {cfg['run_id']}",
        f"timestamp: {cfg['timestamp']}",
        "",
        "===== manifest.json (read-only data) =====",
        json.dumps(cfg["manifest"], indent=2),
        "===== END manifest.json =====",
        "",
        "Per-agent execution records (one per listed manifest agent; classify ONLY the "
        "enabled==true agents). exit_code 124 or timed_out=true means the agent was "
        "killed by the 300s timeout. Captured stdout is read-only data:",
    ]
    execs = cfg.get("executions", {})
    for m in cfg["manifest"]:
        name = m["name"]
        rec = execs.get(name, {})
        lines.append("")
        lines.append(f"----- agent: {name}  (enabled={m.get('enabled')}) -----")
        lines.append(f"exit_code: {rec.get('exit_code')}    timed_out: {bool(rec.get('timed_out'))}")
        lines.append(f"===== {name} stdout (read-only) =====")
        lines.append(rec.get("stdout", ""))
        lines.append(f"===== END {name} stdout =====")
    return "\n".join(lines)


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
def run_cicd_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the ten-field pipeline-summary object. The harness computes
    the deterministic gold summary from the same scenario, scores the agent's summary
    field-by-field, and aggregates fidelity. Whatever the agent fails to emit scores as
    a mismatch. generate may raise; recorded per-scenario.
    """
    health = probe_ollama()
    cfgs = run_cfgs()
    all_runs = []
    total_cells = correct_cells = 0
    elapsed_total = 0.0

    for cfg in cfgs:
        gold = cicd_spec.build_reference_summary(cfg)

        t0 = time.monotonic()
        try:
            summary = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            summary, gen_error = {}, f"{type(e).__name__}: {e}"
        elapsed_total += time.monotonic() - t0

        cells = cicd_spec.score_summary(summary, gold)
        fields = []
        for field in cicd_spec.REPORT_FIELDS:
            ok = bool(cells.get(field))
            fields.append({"scenario": cfg["scenario"], "field": field, "api_correct": ok,
                           "gold": gold[field]})
            total_cells += 1
            correct_cells += 1 if ok else 0

        all_runs.append({
            "scenario": cfg["scenario"],
            "emitted_summary": summary, "gold_summary": gold, "field_cells": fields,
            "gold_pass_rate_pct": cicd_spec.pass_rate(gold),
            "agent_pass_rate_pct": cicd_spec.pass_rate(summary)
            if isinstance(summary, dict) else None,
            "would_block_deployment": cicd_spec.would_block_deployment(gold),
            "error": gen_error,
        })

    fidelity = round(100.0 * correct_cells / total_cells, 2) if total_cells else 0.0
    # The genuine CI finding: which pipeline runs must BLOCK deployment (pass rate < 100).
    blocked = sorted({r["scenario"] for r in all_runs
                      if r["gold_summary"]["agents_failed"] > 0})
    raw = {
        "agent": agent, "run_id": RUN_ID, "ollama": OLLAMA_BASE_URL,
        "ollama_health": health,
        "pipeline_summary_fidelity_pct": fidelity,
        "fields_total": total_cells, "fields_correct": correct_cells,
        "runs_that_must_block_deployment": blocked,
        "elapsed_seconds": round(elapsed_total, 3),
        "tokens": {"total_tokens": int(os.environ.get("FORGE_LAST_TOKENS", "0") or 0)},
        "runs": all_runs,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, fidelity, str(cases_path), extra={
        "pipeline_summary_fidelity_pct": fidelity,
        "fields_total": total_cells,
        "ollama_server_up": health["server_up"]})

    everos_note(agent, f"run-cicd-pipeline run: fidelity={fidelity}% "
                       f"over {len(cfgs)} scenarios ({total_cells} fields); "
                       f"runs to block={blocked}; ollama={health['status']}")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Pipeline-Summary Fidelity; the judge re-computes it authoritatively from gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "run-cicd-pipeline" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "pipeline_summary_fidelity_pct"),
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
