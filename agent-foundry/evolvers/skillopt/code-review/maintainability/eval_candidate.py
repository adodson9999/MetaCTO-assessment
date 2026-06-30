#!/usr/bin/env python3
"""Evaluate one candidate prompt across all four frameworks; print mean band-accuracy.

Sets FORGE_SKILL_DOC=<candidate> (honoured first by every runner's load_system_prompt),
runs the four agents, scores against the held-out bands, and prints per-agent + mean
band-accuracy. Pure measurement — mutates no agent file. Usage:
    eval_candidate.py <candidate_prompt.txt> <run_id>
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

WS = Path(os.environ["FORGE_WORKSPACE"]).resolve()
sys.path.insert(0, str(WS / "agents" / "common"))
import maintainability_spec as spec  # noqa: E402

cand, run_id = sys.argv[1], sys.argv[2]
env = dict(os.environ, FORGE_SKILL_DOC=str(Path(cand).resolve()))
py = str(WS / ".venv" / "bin" / "python")
subprocess.run([py, "scripts/run_maintainability_agents__code-review-maintainability.py",
                "--workspace", str(WS), "--run-id", run_id, "--max-concurrency", "4"],
               cwd=str(WS), env=env, capture_output=True, text=True)

bands = {c["id"]: c["gold_band"] for c in spec.load_heldout(WS)}
denom = len(bands)
agents = ["crewai", "claude_sdk", "code-review-maintainability", "langgraph"]
per, total = {}, 0.0
for a in agents:
    doc = json.loads((WS / "results" / "runs" / run_id / f"{a}.cases.json").read_text())
    s = sum(spec.score_output(c.get("emitted") or {}, bands[c["case_id"]])["score"]
            for c in doc["cases"] if c["case_id"] in bands)
    per[a] = round(s / denom, 4); total += per[a]
mean = round(total / len(agents), 4)
print(json.dumps({"run_id": run_id, "per_agent": per, "mean_band_acc": mean}))
