#!/usr/bin/env python3
# Used by: shared — documentation-gated bug pipeline for the full run (all agents).
"""Documentation-gated bug reporting (the policy).

A bug is a bug IFF:
  1. a manual tester agent observed UNEXPECTED behavior (observed != expected), and
  2. the LLM documentation-reviewer finds a line IN THE DOCUMENTATION that documents the
     expected behavior the agent was checking (verdict == "yes").

No root-cause analysis. No reviewing the DummyJSON implementation (local or remote). The
only inputs are the agent's observed-vs-expected and the documentation corpus (real
dummyjson.com docs + the curated reference set, merged, newest-file wins). Every reported
bug cites the EXACT doc file + line (+ source URL) that documents the violated behavior.

Usage:  python report_doc_bugs.py <RUN_ID> [--limit N] [--all]
Env:    FORGE_PROVIDER (ollama default; claude-cli for a stronger reviewer)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
import adjudicate as A          # noqa: E402  build_corpus/collect_mismatches/_reviewer_invoke/_keywords
import bugreport as BR          # noqa: E402  unverified/verified materialiser (single path source)
import docreview_spec           # noqa: E402
import docreview                # noqa: E402

BR.WORKSPACE = WS
BR.SANDBOX_ROOT = WS
DB_AVAILABLE = False            # DummyJSON target is air-gapped (no [database])

BUG_DIR = WS / "results" / "bug-reports"


def _ctx(m: dict) -> dict:
    return {"agent": m.get("agent", ""), "endpoint": m.get("endpoint", ""),
            "scenario": m.get("scenario", ""), "expected": m.get("expected", ""),
            "observed": m.get("observed", ""), "severity": A.severity(m)}
# map a corpus file to its published source URL (provenance from reference-link-factory)
URL_MAP = {
    "dummyjson-com-docs.md": "https://dummyjson.com/docs",
    "dummyjson-com-docs-auth.md": "https://dummyjson.com/docs/auth",
    "dummyjson-com.md": "https://dummyjson.com/",
}


def source_url(file_path: str | None) -> str | None:
    if not file_path:
        return None
    return URL_MAP.get(Path(file_path).name)


def dedupe(mismatches: list[dict]) -> list[dict]:
    """One representative per distinct disputed behavior (agent, scenario, expected, observed),
    carrying how many concrete cases it covers."""
    groups: dict[tuple, dict] = {}
    for m in mismatches:
        key = (m["agent"], m["scenario"], str(m["expected"]), str(m["observed"]))
        g = groups.setdefault(key, {**m, "occurrences": 0})
        g["occurrences"] += 1
    # documented-topic first so the most likely doc-backed bugs surface early
    topic = ("auth", "token", "login", "expire", "limit", "skip", "sort", "page", "filter", "search")
    return sorted(groups.values(),
                  key=lambda m: (not any(t in (m["scenario"] + m["agent"]).lower() for t in topic),
                                 m["agent"], m["scenario"]))


def review_one(m: dict, corpus: list, invoke) -> dict:
    """Ask the LLM documentation-reviewer whether this mismatch is a documented-behavior
    violation. Returns its 6-key verdict object (verdict, source_of_truth, ...)."""
    parsed = docreview_spec.parse_bug_report(A._bug_report_text(m))
    candidates = docreview_spec.grep_corpus(corpus, A._keywords(m))
    brief = docreview_spec.brief(parsed, corpus, candidates, 3)
    try:
        return docreview.extract_json(invoke(brief)) or {"verdict": "missing-docs"}
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "missing-docs", "reason": f"reviewer error: {exc}"}


def run(run_id: str, limit: int) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    corpus = A.build_corpus()
    uniq = dedupe(A.collect_mismatches(run_dir))
    considered = uniq if limit <= 0 else uniq[:limit]
    invoke = A._reviewer_invoke()

    BUG_DIR.mkdir(parents=True, exist_ok=True)
    bugs, rows = [], []
    counts = {"yes_BUG": 0, "no": 0, "missing-docs": 0, "invalid": 0}
    counters: dict = {}
    uv_entries: list = []
    v_entries: list = []
    for i, m in enumerate(considered, 1):
        v = review_one(m, corpus, invoke)
        verdict = v.get("verdict")
        sot = v.get("source_of_truth") if isinstance(v.get("source_of_truth"), dict) else None
        row = {"agent": m["agent"], "scenario": m["scenario"], "endpoint": m["endpoint"],
               "expected": m["expected"], "observed": m["observed"], "occurrences": m["occurrences"],
               "reviewer_verdict": verdict, "source_of_truth": sot, "reason": v.get("reason")}
        if verdict == "yes" and sot:
            bug_id = f"BUG-{run_id}-{len(bugs) + 1:04d}"
            url = source_url(sot.get("file"))
            report = {
                "bug_id": bug_id, "run_id": run_id, "agent": m["agent"],
                "title": f"{m['agent']}: {m['scenario']} on {m['endpoint']} — expected {m['expected']}, observed {m['observed']}",
                "unexpected_behavior": {"endpoint": m["endpoint"], "expected": m["expected"], "observed": m["observed"]},
                "documentation_evidence": {"file": sot.get("file"), "line": sot.get("line"),
                                           "text": sot.get("text"), "source_url": url},
                "reviewer_reason": v.get("reason"), "occurrences": m["occurrences"],
            }
            (BUG_DIR / f"{bug_id}.json").write_text(json.dumps(report, indent=2))
            bugs.append(bug_id)
            row["bug_id"] = bug_id
            counts["yes_BUG"] += 1
            # Mirror the documented bug into the new tree (decision #10).
            vrep = BR.write_verified_bug(run_id, dict(_ctx(m), source_of_truth=sot),
                                         counters, DB_AVAILABLE, workspace=WS)
            row["verified_report_path"] = vrep["_meta"]["report_path"]
            v_entries.append(vrep["_meta"]["index_entry"])
            print(f"  [{i}/{len(considered)}] BUG {bug_id}: {m['agent']}/{m['scenario']} "
                  f"exp {m['expected']} got {m['observed']} <- {Path(sot.get('file','')).name}:{sot.get('line')}", flush=True)
        elif verdict == "missing-docs":
            # missing-docs is no longer dropped: file a citation-free unverified bug (HF13).
            urep = BR.write_unverified_bug(run_id, _ctx(m), counters, DB_AVAILABLE, workspace=WS)
            row.update({"unverified_bug_id": urep["bug_id"], "category": urep["category"],
                        "category_reason": urep["category_reason"], "exclude_from_cicd": True})
            uv_entries.append(urep["_meta"]["index_entry"])
            counts["missing-docs"] += 1
            print(f"  [{i}/{len(considered)}] missing-docs -> {urep['bug_id']} "
                  f"({urep['category']}): {m['agent']}/{m['scenario']}", flush=True)
        else:
            counts[verdict if verdict == "no" else "invalid"] += 1
            print(f"  [{i}/{len(considered)}] {verdict}: {m['agent']}/{m['scenario']}", flush=True)
        rows.append(row)

    # The two SEPARATE indexes in the new tree (HF16).
    BR.write_unverified_index(run_id, uv_entries, workspace=WS)
    BR.write_verified_index(run_id, v_entries, workspace=WS)

    ledger = {"run_id": run_id, "policy": "bug = unexpected behavior + documentation-reviewer match (LLM); no RCA; no implementation review",
              "unique_disputed_behaviors": len(uniq), "considered": len(considered),
              "counts": counts, "bug_ids": bugs,
              "unverified_count": len(uv_entries), "rows": rows}
    (run_dir / "doc-bug-ledger.json").write_text(json.dumps(ledger, indent=2))
    (BUG_DIR / "index.json").write_text(json.dumps({"run_id": run_id, "bug_ids": bugs, "count": len(bugs)}, indent=2))
    print(f"\n[report_doc_bugs] unique={len(uniq)} considered={len(considered)} -> {counts}", flush=True)
    return ledger


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python report_doc_bugs.py <RUN_ID> [--limit N] [--all]", file=sys.stderr)
        sys.exit(2)
    limit = 0 if "--all" in sys.argv else (int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 12)
    run(sys.argv[1], limit)


if __name__ == "__main__":
    main()
