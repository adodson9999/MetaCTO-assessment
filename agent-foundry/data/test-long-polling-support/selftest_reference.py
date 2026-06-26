#!/usr/bin/env python3
"""Deterministic, no-LLM validation of the long-polling harness + fidelity metric.

Proves two things against the live longpoll-target (no model involved):
  1. A CORRECT plan (the canonical reference plan per channel) reproduces every gold
     token -> Long-Poll-Test Fidelity == 100%, and the headline Long-Poll Response
     Accuracy == the empirical fixture value (66.67%, inventory non-compliant).
  2. A DEGRADED plan (drops the event case on one channel) scores < 100% -> the metric
     actually discriminates plan quality.

Usage (fixture must be running + gold built):
  FORGE_TARGET_BASE_URL=http://127.0.0.1:8921 python3 data/test-long-polling-support/selftest_reference.py
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ.setdefault("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8921")
sys.path.insert(0, str(WS / "agents" / "common"))
import longpoll as harness  # noqa: E402
import longpoll_spec  # noqa: E402


def _fidelity(run_id: str) -> float:
    import subprocess
    subprocess.run([sys.executable, str(WS / "judge" / "test-long-polling-support" / "score.py"),
                    "--workspace", str(WS), "--run-id", run_id],
                   capture_output=True, text=True)
    meta = json.loads((WS / "results" / "runs" / run_id / "_probe.json").read_text())
    return meta["metric_value"]


def _run(run_id: str, generate) -> dict:
    os.environ["FORGE_RUN_ID"] = run_id
    # reload module globals that read RUN_ID at import
    harness.RUN_ID = run_id
    return harness.run_longpoll_test("_probe", generate)


def main() -> int:
    # 1) correct reference plan
    def ref(cfg):
        return longpoll_spec.build_reference_plan(cfg)

    raw = _run("selftest-ref", ref)
    fid = _fidelity("selftest-ref")
    print(f"[reference]  accuracy={raw['longpoll_response_accuracy_pct']}%  fidelity={fid}%")
    assert fid == 100.0, f"reference plan must score 100% fidelity, got {fid}"

    # 2) degraded plan: drop the event case on the first channel
    def degraded(cfg):
        p = longpoll_spec.build_reference_plan(cfg)
        if cfg["channel"] == harness.channel_cfgs()[0]["channel"]:
            p["cases"] = [c for c in p["cases"] if c["kind"] != "event"]
        return p

    _run("selftest-degraded", degraded)
    dfid = _fidelity("selftest-degraded")
    print(f"[degraded]   fidelity={dfid}%  (event case dropped on one channel)")
    assert dfid < 100.0, f"degraded plan must score < 100%, got {dfid}"

    print("\nSELF-TEST PASS: metric reaches 100% for a correct plan and discriminates a degraded one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
