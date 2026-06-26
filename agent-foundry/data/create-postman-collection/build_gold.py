#!/usr/bin/env python3
"""Deterministic GOLD reference for the api-tester / create-postman-collection task ("n601").
NOT one of the four agents — it is the canonical truth the judge scores fidelity against.

It builds the canonical CORRECT Postman Generation Contract
(postman_spec.reference_contract) and applies it to the registry fixture through the SAME
shared building path the agents use (postman_spec.build_collection / evaluate). It records
the REAL observed token per scenario, so an agent that emits the same contract reproduces
these tokens exactly.

No LLM, no server, no HTTP — n601 is a pure JSON->JSON transform. DummyJSON is never used
and never modified.

Rebuild any time:
    python data/create-postman-collection/build_gold.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(WS / "agents" / "common"))

import postman_spec  # noqa: E402

OUT_DIR = WS / "data" / "create-postman-collection"
SPEC = json.loads((OUT_DIR / "postman_spec.json").read_text())


def main() -> int:
    registry = json.loads((WS / SPEC["registry_fixture"]).read_text())
    summary = json.loads((WS / SPEC["summary_fixture"]).read_text())
    cfg = SPEC

    contract = postman_spec.reference_contract(cfg)
    http_tcs = postman_spec.filter_http(registry, contract)
    collection = postman_spec.build_collection(
        http_tcs, contract, SPEC["gold_date"], SPEC["gold_uuid"])
    item_count = postman_spec.recursive_item_count(collection)
    http_tc_count = len(http_tcs)
    rate = postman_spec.coverage_rate(item_count, http_tc_count)

    observed = postman_spec.evaluate(collection, registry, summary, cfg)
    ideal = postman_spec.ideal_for(registry, cfg)

    scenarios = []
    total = correct = 0
    for label in postman_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = postman_spec.correct(label, tok, ideal)
        scenarios.append({"scenario": label, "ideal": ideal[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    gold = {
        "task": "api-tester / create-postman-collection",
        "alias": "n601",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "registry_fixture": SPEC["registry_fixture"],
        "http_tc_count": http_tc_count,
        "postman_item_count": item_count,
        "postman_coverage_rate_pct": rate,
        "reference_contract": contract,
        "reference_collection": collection,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "scenarios": scenarios,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "gold.json").write_text(json.dumps(gold, indent=2))
    (OUT_DIR / "gold").mkdir(exist_ok=True)
    for s in scenarios:
        (OUT_DIR / "gold" / f"{s['scenario']}.json").write_text(json.dumps(s, indent=2))
    # also save the canonical reference collection for inspection
    (OUT_DIR / "gold" / "reference-collection.json").write_text(json.dumps(collection, indent=2))

    print("GOLD built — api-tester / create-postman-collection (n601)")
    print(f"  registry      : {SPEC['registry_fixture']}")
    print(f"  HTTP test cases : {http_tc_count}")
    print(f"  Postman items   : {item_count}")
    print(f"  Postman Coverage Rate = {rate}%  (gap_count={http_tc_count - item_count})")
    print(f"  scenarios api-correct = {correct}/{total}")
    for s in scenarios:
        mark = "ok " if s["api_correct"] else "DIFF"
        print(f"    [{mark}] {s['scenario']:24} ideal={str(s['ideal']):6} observed={s['observed_token']}")
    return 0 if correct == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
