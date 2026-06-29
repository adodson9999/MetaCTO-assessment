#!/usr/bin/env python3
# Used by: orchestrator — full framework sweep across ALL agents.
"""Full-from-scratch, all-4-framework, full-pipeline runner — loops until 3 SUCCESSFUL runs.

Per run (timestamped FWRUN-<ts>):
  1. orchestrate_full FWRUN-<ts>  -> subagent executors + per-agent producer (G11) + the full
     pipeline (guardrails -> adjudicate -> bug-reporter), under results/runs/FWRUN-<ts>/.
  2. For every api-tester, run crewai + langgraph + claude_sdk over ALL 22 endpoints, snapshot
     each framework's REAL output file (subagent -> api-tester-<a>.cases.json; the others ->
     <framework>.cases.json) into  results/FWRUN-<ts>/<agent>/<framework>.json, retry-until-clean
     (rc==0 + non-empty parseable JSON), then write <agent>/combined.json (per-scenario, all 4).
  3. SUCCESS when all 40 agents have a folder with 5 valid non-empty files
     {crewai,langgraph,claude_sdk,subagent,combined}.json AND no framework error.

Loops until 3 successful runs (or a hard safety cap). Resumable: a run resumes its own
agent/framework slices; clean framework files are not re-run.

Usage:  python full_framework_runs.py [--successes 3] [--max-runs 12]
Env:    FORGE_PROVIDER=ollama  FORGE_TARGET_BASE_URL=http://localhost:8899  (defaults)
        FORGE_FRAMEWORK_RETRY (per (agent,fw) clean retries, default 4)
        FWRUN_STAMP (REQUIRED per run: the timestamp string; main loop sets it per run)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
PY = str(WS / ".venv" / "bin" / "python")
TARGET = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
FW_RETRY = int(os.environ.get("FORGE_FRAMEWORK_RETRY", "4"))
EXTRA_FRAMEWORKS = ["crewai", "langgraph", "claude_sdk"]   # subagent comes from orchestrate_full
ALL_FRAMEWORKS = ["subagent", "crewai", "langgraph", "claude_sdk"]

import orchestrate_full as O  # API_TESTERS, run loop


def fw_src(run_dir: Path, agent: str, fw: str) -> Path:
    """The file a framework's run.py actually writes (discovered empirically)."""
    if fw == "subagent":
        return run_dir / f"api-tester-{agent}.cases.json"
    return run_dir / f"{fw}.cases.json"     # crewai/langgraph/claude_sdk are framework-named


def valid_json_nonempty(p: Path) -> bool:
    try:
        d = json.loads(p.read_text())
        return bool(d)
    except (OSError, json.JSONDecodeError):
        return False


def run_framework_clean(run_dir: Path, run_id: str, agent: str, fw: str, out_dir: Path) -> dict:
    """Run one framework for one agent over all endpoints; snapshot to <agent>/<fw>.json.
    Retry until clean (rc==0 + valid non-empty output). Returns {ok, attempts, error}."""
    dest = out_dir / f"{fw}.json"
    if dest.exists() and valid_json_nonempty(dest):
        return {"framework": fw, "ok": True, "attempts": 0, "cached": True}
    rp = WS / "agents" / "api-tester" / agent / fw / "run.py"
    if not rp.exists():
        return {"framework": fw, "ok": False, "attempts": 0, "error": "run.py missing"}
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_TARGET_BASE_URL=TARGET, FORGE_MAX_ENDPOINTS="0")
    src = fw_src(run_dir, agent, fw)
    last_err = None
    for attempt in range(1, FW_RETRY + 1):
        try:
            src.unlink()
        except OSError:
            pass
        try:
            proc = subprocess.run([PY, str(rp)], cwd=str(WS), env=env,
                                  capture_output=True, text=True, timeout=2400)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            last_err = "timeout"
            continue
        if rc == 0 and src.exists() and valid_json_nonempty(src):
            shutil.copyfile(src, dest)
            return {"framework": fw, "ok": True, "attempts": attempt}
        last_err = f"rc={rc} src_exists={src.exists()}"
    return {"framework": fw, "ok": False, "attempts": FW_RETRY, "error": last_err}


def _iter_scenarios(obj):
    if isinstance(obj, dict):
        for s in obj.get("scenarios", []) if isinstance(obj.get("scenarios"), list) else []:
            if isinstance(s, dict):
                yield s
        for v in obj.values():
            yield from _iter_scenarios(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_scenarios(v)


def build_combined(out_dir: Path, agent: str) -> None:
    present = {}
    for fw in ALL_FRAMEWORKS:
        p = out_dir / f"{fw}.json"
        if p.exists():
            try:
                present[fw] = json.loads(p.read_text())
            except json.JSONDecodeError:
                pass
    scen = {}
    for fw, data in present.items():
        for s in _iter_scenarios(data):
            k = f"{s.get('endpoint') or s.get('collection') or ''}::{s.get('scenario','')}"
            row = scen.setdefault(k, {"scenario": s.get("scenario"),
                                      "endpoint": s.get("endpoint") or s.get("collection"),
                                      "ideal": s.get("ideal"), "observed_by": {}, "api_correct_by": {}})
            row["observed_by"][fw] = s.get("observed_token")
            row["api_correct_by"][fw] = s.get("api_correct")
    for row in scen.values():
        obs = list(row["observed_by"].values())
        row["frameworks_agree"] = len(set(map(str, obs))) <= 1 if obs else None
    (out_dir / "combined.json").write_text(json.dumps(
        {"agent": agent, "frameworks_present": sorted(present.keys()),
         "scenario_count": len(scen), "scenarios": list(scen.values())}, indent=2))


def agent_complete(out_dir: Path) -> bool:
    need = [f"{fw}.json" for fw in ALL_FRAMEWORKS] + ["combined.json"]
    return all((out_dir / n).exists() and valid_json_nonempty(out_dir / n) for n in need)


def do_one_run(stamp: str) -> dict:
    run_id = f"FWRUN-{stamp}"
    run_dir = WS / "results" / "runs" / run_id          # pipeline artifacts
    agents_root = WS / "results" / run_id               # results/FWRUN-<ts>/<agent>/  (the 5-file folders)
    agents_root.mkdir(parents=True, exist_ok=True)
    print(f"\n========== RUN {run_id} ==========", flush=True)

    # 1. full pipeline + subagent + per-agent producer
    print(f"[{run_id}] orchestrate_full (subagent + producer + guardrails/adjudicate/bug-reporter)...", flush=True)
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_PROVIDER=os.environ.get("FORGE_PROVIDER", "ollama"),
               FORGE_TARGET_BASE_URL=TARGET)
    subprocess.run([PY, str(WS / "scripts" / "orchestrate_full.py"), run_id],
                   cwd=str(WS), env=env)

    # 2. all 4 frameworks per agent -> the 5-file folder, retry-until-clean
    errors = []
    for i, agent in enumerate(O.API_TESTERS, 1):
        out_dir = agents_root / agent
        out_dir.mkdir(parents=True, exist_ok=True)
        # subagent output already produced by orchestrate_full -> snapshot it
        sub_src = fw_src(run_dir, agent, "subagent")
        if sub_src.exists() and valid_json_nonempty(sub_src) and not (out_dir / "subagent.json").exists():
            shutil.copyfile(sub_src, out_dir / "subagent.json")
        for fw in EXTRA_FRAMEWORKS:
            rec = run_framework_clean(run_dir, run_id, agent, fw, out_dir)
            if not rec["ok"]:
                errors.append({"agent": agent, **rec})
        # subagent fallback: run it directly if orchestrate_full's copy is missing
        if not (out_dir / "subagent.json").exists():
            rec = run_framework_clean(run_dir, run_id, agent, "subagent", out_dir)
            if not rec["ok"]:
                errors.append({"agent": agent, **rec})
        build_combined(out_dir, agent)
        print(f"[{run_id}] [{i}/40] {agent}: complete={agent_complete(out_dir)}", flush=True)

    # 3. success check
    complete = [a for a in O.API_TESTERS if agent_complete(agents_root / a)]
    ok = (len(complete) == len(O.API_TESTERS)) and not errors
    result = {"run_id": run_id, "agents_complete": len(complete), "total": len(O.API_TESTERS),
              "framework_errors": errors, "success": ok}
    (agents_root / "_RUN-RESULT.json").write_text(json.dumps(result, indent=2))
    print(f"[{run_id}] agents_complete={len(complete)}/40 errors={len(errors)} SUCCESS={ok}", flush=True)
    return result


def main() -> None:
    successes_needed = 3
    max_runs = 12
    if "--successes" in sys.argv:
        successes_needed = int(sys.argv[sys.argv.index("--successes") + 1])
    if "--max-runs" in sys.argv:
        max_runs = int(sys.argv[sys.argv.index("--max-runs") + 1])

    stamps = [s.strip() for s in os.environ.get("FWRUN_STAMPS", "").split(",") if s.strip()]
    successes, attempts, log = 0, 0, []
    while successes < successes_needed and attempts < max_runs:
        attempts += 1
        stamp = stamps[attempts - 1] if attempts - 1 < len(stamps) else f"r{attempts:02d}"
        res = do_one_run(stamp)
        log.append({"attempt": attempts, "stamp": stamp,
                    "success": res["success"], "agents_complete": res["agents_complete"],
                    "errors": len(res["framework_errors"])})
        if res["success"]:
            successes += 1
        print(f"\n>>> PROGRESS: {successes}/{successes_needed} successful runs "
              f"({attempts} attempts) <<<", flush=True)
        (WS / "results" / "FWRUN-progress.json").write_text(json.dumps(
            {"successes": successes, "needed": successes_needed, "attempts": attempts, "log": log}, indent=2))

    print(f"\n=== FINISHED: {successes}/{successes_needed} successful runs in {attempts} attempts ===", flush=True)
    sys.exit(0 if successes >= successes_needed else 1)


if __name__ == "__main__":
    main()
