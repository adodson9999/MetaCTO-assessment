#!/usr/bin/env python3
"""n601 — Postman Collection Creator (production CLI).

The faithful, deterministic implementation of the twelve-step n601 contract: read the
registry summary, gap pre-check, filter involves_http_call=true, build one Postman v2.1
request item per HTTP test case, group into per-agent folders, assemble
results/postman-collection.json, read it back + recursively count request items, assert
the count equals the registry HTTP test-case count, write a gaps file for any
unrepresented tc_id, write the summary, run a Newman dry-run, and exit with the spec's
codes/messages.

This is the standalone n601 program. The four forge agents (LangGraph / CrewAI / Claude
SDK / Claude Code subagent) each EMIT the Postman Generation Contract this CLI uses, and
the judge measures how faithfully they reproduce it; this CLI runs that same contract end
to end against the real results/ files.

n601 makes NO HTTP calls of its own and NEVER touches DummyJSON.

Usage:
    python scripts/postman_collection_cli__create-postman-collection.py [--workspace .] [--seed-from-fixture]

Exit codes (per spec):
    0  collection COMPLETE (gap_count == 0)
    1  aborted (registry gaps) / INCOMPLETE (gap_count > 0) / no HTTP test cases
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--seed-from-fixture", action="store_true",
                    help="copy the registry/summary fixtures into results/ if absent "
                         "(the sibling n600 normally produces them)")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    sys.path.insert(0, str(ws / "agents" / "common"))
    import postman_spec  # noqa

    spec = json.loads((ws / "data" / "create-postman-collection" / "postman_spec.json").read_text())
    reg_path = ws / spec["registry_path"]
    sum_path = ws / spec["summary_path"]

    if a.seed_from_fixture:
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        if not reg_path.exists():
            reg_path.write_text((ws / spec["registry_fixture"]).read_text())
        if not sum_path.exists():
            sum_path.write_text((ws / spec["summary_fixture"]).read_text())

    # Step 1 — registry summary gap pre-check
    if not sum_path.exists():
        _err(f"Registry summary not found at {spec['summary_path']}. Run n600 first "
             "(or pass --seed-from-fixture to use the bundled fixture).")
        return 1
    summary = json.loads(sum_path.read_text())
    if summary.get("gaps_found") is True:
        gap_count = summary.get("gap_count", "?")
        _err(f"Postman collection generation aborted: registry has {gap_count} gaps. "
             "Re-run n600 until coverage_rate = 100.0 before running n601.")
        return 1

    # Step 2 — read registry, filter HTTP test cases
    if not reg_path.exists():
        _err(f"Registry not found at {spec['registry_path']}. Run n600 first "
             "(or pass --seed-from-fixture).")
        return 1
    registry = json.loads(reg_path.read_text())
    contract = postman_spec.reference_contract(spec)
    http_tcs = postman_spec.filter_http(registry, contract)
    http_tc_count = len(http_tcs)
    if http_tc_count == 0:
        _err("No HTTP test cases found in registry. Verify n600 ran against "
             "HTTP-calling agents.")
        return 1

    # Steps 3-8 — build the collection
    iso_date = datetime.now(timezone.utc).date().isoformat()
    postman_id = str(uuid.uuid4())
    collection = postman_spec.build_collection(http_tcs, contract, iso_date, postman_id)

    coll_out = ws / spec["collection_out"]
    coll_out.parent.mkdir(parents=True, exist_ok=True)
    coll_out.write_text(json.dumps(collection, indent=2))

    # Step 9 — read back + recursive walk
    reloaded = json.loads(coll_out.read_text())
    item_count = postman_spec.recursive_item_count(reloaded)
    names = {it.get("name") for it in postman_spec.collect_request_items(reloaded)}
    missing = [{"tc_id": tc.get("tc_id"), "agent": tc.get("agent")}
               for tc in http_tcs if tc.get("tc_id") not in names]
    gaps_found = item_count != http_tc_count
    if gaps_found:
        (ws / spec["gaps_out"]).write_text(json.dumps(missing, indent=2))

    agents_covered = len({tc.get("agent") for tc in http_tcs if tc.get("tc_id") in names})
    coverage_rate = postman_spec.coverage_rate(item_count, http_tc_count)

    # Step 11 — Newman dry-run (non-aborting warning)
    sys.path.insert(0, str(ws / "agents" / "common"))
    import postman as harness  # noqa
    newman_valid, newman_detail = harness.newman_dry_run(coll_out)
    if newman_valid is False:
        _err(f"Newman dry-run validation failed: {newman_detail}")

    # Step 10 — summary
    summary_out = {
        "collection_file": spec["collection_out"],
        "http_test_cases_in_registry": http_tc_count,
        "postman_items_created": item_count,
        "coverage_rate": round(100.0 * item_count / http_tc_count, 2) if http_tc_count else 0.0,
        "gaps_found": gaps_found,
        "gap_count": http_tc_count - item_count,
        "agents_covered": agents_covered,
        "collection_name": collection["info"]["name"],
        "newman_valid": newman_valid,
        "newman_detail": newman_detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (ws / spec["summary_out"]).write_text(json.dumps(summary_out, indent=2))

    # Step 12 — final verdict
    if gaps_found:
        _err(f"Postman collection INCOMPLETE: {http_tc_count - item_count} HTTP test "
             f"cases have no collection item. See {spec['gaps_out']}.")
        return 1
    print(f"Postman collection COMPLETE: {item_count} items covering {agents_covered} "
          f"agents. Newman validation: {newman_valid}.")
    print(f"  -> {spec['collection_out']}  (coverage_rate={coverage_rate}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
