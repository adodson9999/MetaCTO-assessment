#!/usr/bin/env python3
"""Gold-set builder for the API long-polling testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
agent-facing input spec (longpoll_spec.json — the documented contract, with the fixture's
compliance flags stripped), derives the canonical correct long-poll plan per channel,
drives that plan against a locally-running longpoll-target (open the no-event poll, then
the event poll with a background trigger), and records the REAL observed token per scenario.

The fixture is the air-gapped local stand-in for a real long-poll backend. One channel
(`inventory`) is deliberately non-compliant, so the gold records a real, catchable defect
(mirrors DummyJSON's lenient pagination behavior).

Outputs (all under data/test-long-polling-support/):
  - longpoll_spec.json       the channel catalogue the agents are briefed from (INPUT)
  - gold/<channel>.json      per-channel gold scenarios
  - gold.json                consolidated gold table + empirical accuracy summary

Usage:
  FORGE_TARGET_BASE_URL=http://127.0.0.1:8921 python3 build_gold.py
Stdlib only. No network beyond the local fixture. Air-gapped.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
GOLD_DIR = HERE / "gold"
BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8921").rstrip("/")

os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ["FORGE_TARGET_BASE_URL"] = BASE_URL
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "tools" / "longpoll-target"))

import fixture_config  # noqa: E402
import longpoll_spec  # noqa: E402
import longpoll as harness  # noqa: E402  (reuse the raw-socket long-poll probes)


def _cfg(c: dict) -> dict:
    return {"channel": c["channel"], "poll_path": c["poll_path"],
            "trigger_path": c["trigger_path"], "poll_timeout_s": c["poll_timeout_s"],
            "expected_event_type": c["expected_event_type"]}


def main() -> int:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        urllib.request.urlopen(BASE_URL + "/__health", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: longpoll-target not reachable at {BASE_URL} ({e})", file=sys.stderr)
        return 2

    (HERE / "longpoll_spec.json").write_text(
        json.dumps(fixture_config.agent_facing_spec(BASE_URL), indent=2))

    consolidated = []
    total = correct = 0
    cases_total = cases_passed = 0

    for raw in fixture_config.CHANNELS:
        c = _cfg(raw)
        plan = longpoll_spec.build_reference_plan(c)

        # Run the two cases with the canonical correct plan values.
        ne = harness.poll_no_event(plan["poll_path"], plan["poll_timeout_s"],
                                   plan["client_max_time_s"])
        ev = harness.poll_with_event(plan["poll_path"], plan["trigger_path"],
                                     plan["poll_timeout_s"], plan["client_max_time_s"])

        ne_tok = longpoll_spec.evaluate_no_event(ne, c["poll_timeout_s"])
        ev_tok = longpoll_spec.evaluate_event(ev, c["expected_event_type"])
        ch_tok = longpoll_spec.evaluate_channel(plan, c)

        scenarios = []
        for label in longpoll_spec.NO_EVENT_SCENARIO_LABELS:
            tok = ne_tok.get(label, "missing")
            ok = longpoll_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": longpoll_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        for label in longpoll_spec.EVENT_SCENARIO_LABELS:
            tok = ev_tok.get(label, "missing")
            ok = longpoll_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": longpoll_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        for label in longpoll_spec.CHANNEL_SCENARIO_LABELS:
            tok = ch_tok.get(label, "missing")
            ok = longpoll_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": longpoll_spec.IDEAL[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0

        cases_total += 2
        cases_passed += 1 if longpoll_spec.no_event_case_pass(ne_tok) else 0
        cases_passed += 1 if longpoll_spec.event_case_pass(ev_tok) else 0

        rec = {"channel": c["channel"], "poll_timeout_s": c["poll_timeout_s"],
               "expected_event_type": c["expected_event_type"],
               "reference_plan": plan,
               "observations": {"no_event": ne, "event": ev},
               "scenarios": scenarios}
        (GOLD_DIR / f"{c['channel']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct / total, 2) if total else None
    acc = round(100.0 * cases_passed / cases_total, 2) if cases_total else None
    summary = {
        "target": BASE_URL,
        "channels": len(consolidated),
        "cases_total": cases_total,
        "cases_passed": cases_passed,
        "empirical_longpoll_response_accuracy_pct": acc,
        "total_scenarios": total,
        "api_correct_scenarios": correct,
        "empirical_scenario_correctness_rate_pct": rate,
        "note": "Ground truth = the local longpoll-target's real observed token per "
                "(channel, scenario). One channel (inventory) is non-compliant: it returns "
                "200 + a non-empty body on a no-event poll (never 204 empty) and stalls ~3s "
                "after the event with the wrong event_type, so both its cases fail and the "
                "response accuracy is below 100% by design — that gap is a real QA finding, "
                "not an agent failure.",
    }
    (HERE / "gold.json").write_text(
        json.dumps({"summary": summary, "channels": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
