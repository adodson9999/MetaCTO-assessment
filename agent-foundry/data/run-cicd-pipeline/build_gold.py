#!/usr/bin/env python3
"""Gold-set builder for the API "CI/CD Pipeline Runner" task (general position).

This is NOT one of the four agents. It is the deterministic *reference*: it materialises
the agents' briefing input (cicd_spec.json + the per-scenario fixture files) from the
scenario catalogue, then derives the canonical CORRECT ten-field pipeline-summary for
every scenario by classifying the same execution records the agents receive.

Why fixtures: the task's real inputs (a manifest + captured agent stdout/stderr from a
live CI run) are local, air-gapped fixtures under
data/run-cicd-pipeline/scenarios/<scenario>/. DummyJSON exposes no CI surface and is
never modified. Backend = Ollama, local; the Ollama server is NEVER started by this
build — the only (optional) call is a read-only GET <ollama>/api/tags to mirror the
task's server health step.

Outputs (all under data/run-cicd-pipeline/):
  - cicd_spec.json              the scenario catalogue the agents are briefed from (INPUT)
  - scenarios/<scenario>/manifest.json + stdout/<agent>.stdout.txt + exec.json (fixtures)
  - gold/<scenario>.json        per-scenario gold summary
  - gold.json                   consolidated gold summaries + pass-rate summary

Usage:
  [OLLAMA_BASE_URL=http://127.0.0.1:11434] python3 build_gold.py
Stdlib only. Air-gapped (no network beyond the optional read-only /api/tags GET; the
Ollama server is never started).
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
SCEN_DIR = HERE / "scenarios"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

# Shared classification structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import cicd_spec  # noqa: E402


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from: the scenario catalogue with the
    [backend] block, run metadata, manifest, and per-agent execution records — WITHOUT
    the answer summary."""
    return {
        "title": "CI/CD Pipeline Runner — scenario catalogue (general)",
        "description": "Each entry is one full pipeline run's captured artifacts: the [backend] "
                       "config block (provider=ollama, model), the model digest, the run id and "
                       "timestamp, the manifest.json agent array, and one execution record "
                       "(exit_code, timed_out, captured stdout) per listed agent. Agents classify "
                       "exactly the enabled==true agents and emit the ten-field pipeline-summary; "
                       "ground truth is the deterministic classification in cicd_spec. The Ollama "
                       "server is probed read-only and NEVER started; DummyJSON is untouched.",
        "ollama_base_url": OLLAMA_BASE_URL,
        "scenarios_subdir": "scenarios",
        "scenarios": cicd_spec.SCENARIOS,
    }


def materialise_fixtures() -> None:
    """Write each scenario's manifest.json + per-agent stdout files + exec.json to disk,
    mirroring the run-regression-suite builds/<pair>/ fixture layout. These are the
    on-disk artifacts a real CI runner would have captured."""
    for s in cicd_spec.SCENARIOS:
        d = SCEN_DIR / s["scenario"]
        (d / "stdout").mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps(s["manifest"], indent=2))
        exec_meta = {}
        for name, rec in s["executions"].items():
            (d / "stdout" / f"{name}.stdout.txt").write_text(rec.get("stdout", ""))
            exec_meta[name] = {"exit_code": rec.get("exit_code"),
                               "timed_out": bool(rec.get("timed_out")),
                               "stdout_file": f"stdout/{name}.stdout.txt"}
        (d / "exec.json").write_text(json.dumps({
            "scenario": s["scenario"],
            "backend": s["backend"],
            "model_digest": s["model_digest"],
            "run_id": s["run_id"],
            "timestamp": s["timestamp"],
            "executions": exec_meta,
        }, indent=2))


def optional_health() -> dict:
    """Read-only GET <ollama>/api/tags (mirrors the task's server health step). Non-fatal
    and NON-STARTING: the gold summaries are computed from the fixtures, not the server."""
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=5) as r:
            return {"endpoint": "/api/tags", "status": r.getcode(), "server_up": r.getcode() == 200}
    except urllib.error.HTTPError as e:
        return {"endpoint": "/api/tags", "status": e.code, "server_up": e.code == 200}
    except Exception as e:  # noqa
        return {"endpoint": "/api/tags", "status": -1, "server_up": False, "note": str(e)}


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    materialise_fixtures()
    (HERE / "cicd_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    rate_summary = []
    for s in cicd_spec.SCENARIOS:
        gold = cicd_spec.build_reference_summary(s)
        rate = cicd_spec.pass_rate(gold)
        rec = {
            "scenario": s["scenario"], "note": s.get("note", ""),
            "gold_summary": gold,
            "pass_rate_pct": rate,
            "would_block_deployment": cicd_spec.would_block_deployment(gold),
        }
        (GOLD_DIR / f"{s['scenario']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)
        rate_summary.append({"scenario": s["scenario"], "run_id": s["run_id"],
                             "pass_rate_pct": rate,
                             "would_block_deployment": rec["would_block_deployment"]})

    blocked = sorted({r["scenario"] for r in rate_summary if r["would_block_deployment"]})
    summary = {
        "ollama_base_url": OLLAMA_BASE_URL,
        "ollama_health": optional_health(),
        "scenarios": len(cicd_spec.SCENARIOS),
        "fields_per_scenario": len(cicd_spec.REPORT_FIELDS),
        "total_gold_fields": len(cicd_spec.SCENARIOS) * len(cicd_spec.REPORT_FIELDS),
        "pass_rates": rate_summary,
        "runs_that_must_block_deployment": blocked,
        "note": "Ground truth = the deterministic ten-field pipeline-summary per scenario "
                "(TIMED_OUT > MALFORMED > FAILED > PASSED precedence over the enabled agents). "
                "Pipeline Agent Pass Rate is fixture-determined; the genuine finding is which "
                "pipeline runs must be BLOCKED for having any non-passing agent (pass = exactly "
                "100%, no tolerance). Framework ranking is Pipeline-Summary Fidelity (agent "
                "summary vs gold), which is backend-independent. The Ollama server is never "
                "started by this build.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "scenarios": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
