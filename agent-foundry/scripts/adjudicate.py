#!/usr/bin/env python3
# Used by: shared — documentation-gated bug adjudication for EVERY agent; used by report_doc_bugs, run_pipeline, orchestrate_full, guardrails.
"""Phase-3 adjudication loop (orchestrator-full.md §3), realized over the batch run.

The forge batch driver records per-agent metrics but never adjudicates individual
mismatches into reviewer-gated bug reports. This module closes that gap WITHOUT
touching the DummyJSON app:

  for every scenario mismatch (api_correct == false) in the run's *.cases.json:
    1. CAPABILITY FILTER (data/target-capabilities.json): if the agent probes a
       feature the local target does not have -> ledger outcome ENV-LIMITED,
       exclude_from_cicd, no bug (environmental, not a documentation defect).
    2. DOC ADJUDICATION (deterministic, mirrors the hardened documentation-reviewer):
       grep the cli/+reference/ corpus (newest-mtime file wins on conflict) for the
       disputed behavior and compare observed vs documented:
         - documented expected AND observed differs -> verdict "yes"  -> CONFIRMED BUG
         - documented AND observed matches           -> verdict "no"   -> EXPECTED-CORRECTED
         - not documented after full scan            -> "missing-docs" -> exclude_from_cicd
    3. On verdict "yes": materialize results/bug-reports/<BUG_ID>.json (the deterministic
       program the bug-reporter prose defers to), severity per §3.
  Then RECONCILE (Phase 3): bug rows == report files; every mismatch terminal; every
  missing-docs excluded from CI; write adjudication-ledger.json + index.json.

The LLM documentation-reviewer remains the SCORED agent; this loop uses the same
contract deterministically so it can run over thousands of mismatches for free. Point
the corpus at a richer doc set by editing the reviewer spec's cli_dir/reference_dir.

Usage:  python adjudicate.py <RUN_ID>
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import bugreport as BR  # noqa: E402  (materialiser: bug_paths, write_unverified_bug, indexes)
import bugreport_spec  # noqa: E402,F401  (re-exported: deterministic classifier constants for reconcile/tests)
import docreview  # noqa: E402  (run_cfg -> {cli_dir, reference_dir, doc_manifest})
import docreview_spec  # noqa: E402  (load_corpus, grep_corpus — newest-first)

# The materialiser reads its workspace/sandbox from module globals; bind them to this run's
# workspace so bug_paths() writes the BugReport tree under WS (the single path source — G-PATHS).
BR.WORKSPACE = WS
BR.SANDBOX_ROOT = WS

# The DummyJSON target is air-gapped (no [database]); unverified bugs capture the full
# artifact set minus the db dump (HF22 threshold keyed on this).
ADJUDICATE_DB_AVAILABLE = False

CAP_PATH = WS / "data" / "target-capabilities.json"
# Richer behavior corpus harvested from the live docs (project-root references/, OUTSIDE
# agent-foundry). Merged into the adjudication corpus so the loop can adjudicate against the
# REAL DummyJSON documentation. The reviewer's SCORED corpus is untouched.
EXTRA_DOCS = Path(os.environ.get(
    "FORGE_ADJUDICATION_DOCS", str(WS.parent / "references" / "dummyjson-com"))).resolve()
BUG_DIR = WS / "results" / "bug-reports"
STOPWORDS = {"the", "and", "for", "with", "status", "test", "case", "plan", "true", "false"}


def build_corpus() -> list[dict]:
    """Reviewer corpus (data/documentation-reviewer/cli+reference) MERGED with the richer
    harvested docs (references/dummyjson-com/), re-sorted newest-mtime-first so the
    newest-wins tie-break holds across both sources. The reviewer's scored corpus is reused
    read-only; this never edits it."""
    corpus = list(docreview_spec.load_corpus(docreview.run_cfg()))
    if EXTRA_DOCS.is_dir():
        for fp in sorted(EXTRA_DOCS.rglob("*.md")):
            if not fp.is_file() or fp.name.startswith("."):
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
            # Skip raw JSON RESPONSE CAPTURES — they are data, not documented behavior.
            if "Captured API response for" in text[:400]:
                continue
            # Skip IMAGE/binary captures (base64 blobs) — not prose docs, and they balloon the
            # reviewer brief to millions of chars (the bug that broke the reviewer). Detect by
            # filename or an actual base64 blob — NOT by an 'image not available' placeholder,
            # which appears in genuine prose docs (that over-broad filter dropped the real docs).
            if any(t in fp.name.lower() for t in ("image", "img", "png", "meta-png")):
                continue
            if "data:image" in text[:4000].lower() or any(len(ln) > 4000 for ln in text.splitlines()):
                continue
            modified = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            corpus.append({
                "file": str(fp), "folder": "reference-dummyjson", "modified": modified,
                "lines": [{"line": i, "text": ln} for i, ln in enumerate(text.splitlines(), 1)],
            })
    corpus.sort(key=lambda r: r["modified"], reverse=True)  # newest-first
    return corpus


def load_caps() -> dict:
    try:
        return json.loads(CAP_PATH.read_text())
    except OSError:
        return {"capabilities": {}, "agent_capability_map": {}}


def collect_mismatches(run_dir: Path) -> list[dict]:
    """Every api_correct==False scenario across the run's *.cases.json, flattened."""
    out: list[dict] = []
    for cf in sorted(run_dir.glob("api-tester-*.cases.json")):
        agent = cf.name[len("api-tester-"):-len(".cases.json")]
        try:
            data = json.loads(cf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for scn in _iter_scenarios(data):
            if scn.get("api_correct") is False:
                out.append({
                    "agent": agent,
                    "endpoint": scn.get("collection") or scn.get("endpoint") or scn.get("path") or "",
                    "scenario": scn.get("scenario", ""),
                    "expected": str(scn.get("ideal", "")),
                    "observed": str(scn.get("observed_token", "")),
                })
    return out


def _iter_scenarios(obj):
    """Yield every scenario dict anywhere in a cases.json (schemas nest differently)."""
    if isinstance(obj, dict):
        scns = obj.get("scenarios")
        if isinstance(scns, list):
            for s in scns:
                if isinstance(s, dict):
                    yield s
        for v in obj.values():
            yield from _iter_scenarios(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_scenarios(v)


def _keywords(m: dict) -> list[str]:
    raw = re.split(r"[^a-zA-Z0-9]+", f"{m['scenario']} {m['endpoint']}")
    kws = [w.lower() for w in raw if len(w) > 2 and w.lower() not in STOPWORDS]
    return list(dict.fromkeys(kws))  # de-dup, keep order


def _value_in_line(value: str, line: str) -> bool:
    v = value.strip().lower()
    if not v or v in ("missing", "absent", "n/a", "none"):
        return False  # non-values from the scenario harness, not doc tokens
    return re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", line.lower()) is not None


def _is_prose(line: str) -> bool:
    """A documented-behavior line must be natural-language prose — not a JSON field, an
    image/base64 blob, or a code line. This is what stops response-data and binary captures
    from becoming a phantom 'source of truth' for a numeric/boolean scenario token."""
    s = line.strip()
    if not s or len(s) < 12:
        return False
    low = s.lower()
    if s.startswith(("![", "<!--", "```", "fetch(", "//", "*", "|", "{", "}", "[", "-")):
        return False
    if "data:image" in low or "base64" in low or "image not available" in low:
        return False
    if re.match(r'^"?[\w-]+"?\s*:', s):  # JSON "key": value  /  key: value data line
        return False
    letters = sum(c.isalpha() for c in s)
    if letters / len(s) < 0.55:  # mostly symbols/digits => data, not prose
        return False
    return len(re.findall(r"[A-Za-z]{2,}", s)) >= 5  # at least a few real words


def adjudicate_one(m: dict, corpus: list[dict]) -> dict:
    """Deterministic verdict mirroring the hardened reviewer: newest-mtime file wins."""
    hits = docreview_spec.grep_corpus(corpus, _keywords(m))  # already newest-first
    if not hits:
        return {"verdict": "missing-docs", "source_of_truth": None,
                "documented_expected": None, "observed": m["observed"],
                "reason": "No cli/ or reference/ line documents this behavior."}
    # Newest-wins, but the source of truth must be a line that actually STATES the disputed
    # value (expected or observed) — not a title/heading that merely matched a keyword.
    # hits are newest-file-first; the first value-bearing hit is the newest authoritative line.
    val_hits = [h for h in hits
                if _is_prose(h["text"])
                and (_value_in_line(m["expected"], h["text"]) or _value_in_line(m["observed"], h["text"]))]
    if not val_hits:
        return {"verdict": "missing-docs",
                "source_of_truth": {"file": hits[0]["file"], "line": hits[0]["line"], "text": hits[0]["text"]},
                "other_matches": hits[1:6], "documented_expected": None, "observed": m["observed"],
                "reason": "Matching doc lines do not state the specific disputed value."}
    sot = val_hits[0]
    others = [h for h in hits if h is not sot][:5]
    line = sot["text"]
    doc_has_expected = _value_in_line(m["expected"], line)
    doc_has_observed = _value_in_line(m["observed"], line)
    observed_is_real = _value_in_line(m["observed"], m["observed"])  # False for missing/absent/n/a
    if doc_has_expected and not doc_has_observed and observed_is_real:
        verdict, reason = "yes", f"Docs document '{m['expected']}'; observed '{m['observed']}' differs."
    elif doc_has_observed:
        verdict, reason = "no", f"Observed '{m['observed']}' matches the documented behavior; expected was wrong."
    else:
        verdict, reason = "missing-docs", "Matching doc line does not state the specific disputed value."
    return {"verdict": verdict,
            "source_of_truth": {"file": sot["file"], "line": sot["line"], "text": line},
            "other_matches": others,
            "documented_expected": line if verdict in ("yes", "no") else None,
            "observed": m["observed"], "reason": reason}


def severity(m: dict) -> str:
    exp, obs = m["expected"].lower(), m["observed"].lower()
    deny = any(c in exp for c in ("401", "403", "denied", "unauthorized", "forbidden"))
    got_2xx = bool(re.match(r"2\d\d", obs)) or obs in ("true", "200")
    if deny and got_2xx:
        return "CRITICAL"
    exp_class, obs_class = exp[:1], obs[:1]
    if exp_class in "45" and obs_class == "5":
        return "HIGH"
    if exp_class.isdigit() and obs_class.isdigit() and exp_class != obs_class:
        return "HIGH"
    return "MEDIUM"


def write_bug(run_id: str, idx: int, m: dict, verdict: dict) -> str:
    BUG_DIR.mkdir(parents=True, exist_ok=True)
    bug_id = f"BUG-{run_id}-{idx:04d}"
    sev = severity(m)
    report = {
        "bug_id": bug_id, "run_id": run_id, "severity": sev, "priority": "P1" if sev in ("CRITICAL", "HIGH") else "P3",
        "agent": m["agent"], "endpoint": m["endpoint"], "sub_test": m["scenario"],
        "documented_expected": verdict.get("documented_expected"), "observed": m["observed"],
        "source_of_truth": verdict.get("source_of_truth"),
        "reviewer_verdict": "yes",
        "title": f"{m['agent']}: {m['scenario']} on {m['endpoint']} — expected {m['expected']}, got {m['observed']}",
    }
    (BUG_DIR / f"{bug_id}.json").write_text(json.dumps(report, indent=2))
    return bug_id


def _documented_topic(m: dict) -> bool:
    key = (m.get("scenario", "") + m.get("agent", "")).lower()
    return any(t in key for t in ("limit", "skip", "sort", "page", "auth", "expire", "token", "filter", "search"))


def _bug_report_text(m: dict) -> str:
    return (
        f"Title: [{m['agent']}] {m['scenario']} on {m['endpoint']} — expected {m['expected']}, got {m['observed']}\n\n"
        f"Steps to Reproduce:\n"
        f"  1. Exercise the {m['agent']} scenario '{m['scenario']}' against {m['endpoint']}\n"
        f"  2. Observe the result token\n\n"
        f"Expected Result:\n  {m['expected']}\n\n"
        f"Actual Result:\n  {m['observed']}\n\n"
        f"Severity: Medium\nPriority: P3\n\n"
        f"Notes / Workaround: agent={m['agent']}; scenario={m['scenario']}\n")


def _reviewer_invoke():
    """Build the LLM documentation-reviewer invoker (same wiring as its run.py)."""
    from runners.utils import load_system_prompt
    from runners.subagent_runner import build_invoker
    from docreview_prompt import user_message
    md = WS / "agents" / "general" / "documentation-reviewer" / "subagent" / "general-documentation-reviewer.md"
    system = load_system_prompt(md)
    return build_invoker(WS, system, user_message)


def escalate(rows: list, corpus: list, run_id: str, limit: int) -> dict:
    """Send missing-docs rows (with a REAL observed value) to the now-accurate LLM
    documentation-reviewer for the inference the deterministic pass won't risk. Deduped by
    disputed behavior, documented-topic first, capped at `limit` (capped count is logged —
    no silent truncation). Updates rows in place; returns an escalation log."""
    import docreview  # extract_json
    eligible = [r for r in rows
                if r["outcome"] == "missing-docs" and _value_in_line(r["observed"], r["observed"])]
    # de-dup by disputed behavior; documented-topic first
    seen, unique = {}, []
    for r in sorted(eligible, key=lambda r: (not _documented_topic(r), r["agent"], r["scenario"])):
        k = (r["agent"], r["scenario"], r["expected"], r["observed"])
        seen.setdefault(k, []).append(r)
        if k not in [u[0] for u in unique]:
            unique.append((k, r))
    capped = unique[limit:]
    unique = unique[:limit]
    invoke = _reviewer_invoke()
    log = {"eligible": len(eligible), "unique_behaviors": len(seen),
           "escalated": len(unique), "capped": len(capped),
           "invalid_verdict": 0, "reclassified_bug": 0, "reclassified_no": 0, "results": []}
    valid = ("yes", "no", "missing-docs")
    for k, r in unique:
        parsed = docreview_spec.parse_bug_report(_bug_report_text(r))
        candidates = docreview_spec.grep_corpus(corpus, _keywords(r))
        the_brief = docreview_spec.brief(parsed, corpus, candidates, 3)
        try:
            decision = docreview.extract_json(invoke(the_brief)) or {}
        except Exception as exc:  # noqa: BLE001
            decision = {"verdict": "missing-docs", "reason": f"escalation error: {exc}"}
        verdict = decision.get("verdict")
        if verdict not in valid:  # 14b often returns an invalid verdict on OOD inputs
            log["invalid_verdict"] += 1
            verdict = "missing-docs"  # safe: never reclassify on a malformed verdict
        log["results"].append({"behavior": list(k), "llm_verdict": verdict,
                               "raw_verdict": decision.get("verdict")})
        for row in seen[k]:
            row["adjudicated_by"] = "llm-reviewer"
            row["llm_verdict"] = decision
            if verdict == "yes":
                bug_id = write_bug(run_id, _next_bug_index(run_id), row, {
                    "documented_expected": decision.get("documented_expected"),
                    "source_of_truth": decision.get("source_of_truth")})
                row.update({"outcome": "BUG", "reviewer_verdict": "yes",
                            "severity": severity(row), "bug_id": bug_id, "exclude_from_cicd": False,
                            "source_of_truth": decision.get("source_of_truth")})
                log["reclassified_bug"] += 1
            elif verdict == "no":
                row.update({"outcome": "EXPECTED-CORRECTED", "reviewer_verdict": "no",
                            "exclude_from_cicd": False,
                            "source_of_truth": decision.get("source_of_truth")})
                log["reclassified_no"] += 1
            # missing-docs / invalid: unchanged (safe)
    return log


def _next_bug_index(run_id: str) -> int:
    return len(list(BUG_DIR.glob(f"BUG-{run_id}-*.json"))) + 1


def _ctx_from_row(row: dict) -> dict:
    """The mismatch context handed to the materialiser (one bug's worth of signals)."""
    return {
        "agent": row.get("agent", ""),
        "endpoint": row.get("endpoint", ""),
        "scenario": row.get("scenario", ""),
        "expected": row.get("expected", ""),
        "observed": row.get("observed", ""),
        "spec_path": row.get("spec_path", ""),
        "stderr": row.get("stderr", ""),
        "severity": row.get("severity") or severity(row),
    }


def materialize_new_tree(run_id: str, rows: list) -> dict:
    """Phase-B materialisation over the FINAL adjudication rows (run after escalation so no
    reclassified row leaves an orphan file — HF18). Writes:
      * every missing-docs row -> an unverified bug under unverified_bugs/{category}/ and
        stamps the row with unverified_bug_id + category (HF13);
      * every BUG (verdict yes) row -> a verified mirror under verified_bugs/ (decision #10);
      * the two SEPARATE indexes (HF16).
    Report-only: nothing here touches CI membership or the exit code (HF15)."""
    counters: dict = {}
    unverified_entries: list = []
    verified_entries: list = []
    for row in rows:
        if row.get("outcome") == "missing-docs":
            report = BR.write_unverified_bug(run_id, _ctx_from_row(row), counters,
                                             ADJUDICATE_DB_AVAILABLE, workspace=WS)
            row["unverified_bug_id"] = report["bug_id"]
            row["category"] = report["category"]
            row["category_reason"] = report["category_reason"]
            unverified_entries.append(report["_meta"]["index_entry"])
        elif row.get("outcome") == "BUG":
            sot = row.get("source_of_truth") or {
                "file": None, "line": None, "text": row.get("documented_expected")}
            ctx = dict(_ctx_from_row(row), source_of_truth=sot)
            report = BR.write_verified_bug(run_id, ctx, counters, ADJUDICATE_DB_AVAILABLE, workspace=WS)
            row["verified_report_path"] = report["_meta"]["report_path"]
            verified_entries.append(report["_meta"]["index_entry"])
    BR.write_unverified_index(run_id, unverified_entries, workspace=WS)
    BR.write_verified_index(run_id, verified_entries, workspace=WS)
    return {"unverified": len(unverified_entries), "verified": len(verified_entries)}


def run(run_id: str, do_escalate: bool = False, escalate_limit: int = 40) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    caps = load_caps()
    cap_map = caps.get("agent_capability_map", {})
    cap_defs = caps.get("capabilities", {})
    corpus = build_corpus()

    mismatches = collect_mismatches(run_dir)
    rows, bug_ids = [], []
    counts = {"PASS": 0, "BUG": 0, "EXPECTED-CORRECTED": 0, "missing-docs": 0, "ENV-LIMITED": 0}

    for i, m in enumerate(mismatches):
        unsupported = [c for c in cap_map.get(m["agent"], []) if not cap_defs.get(c, {}).get("supported", True)]
        if unsupported:
            row = {**m, "reviewer_verdict": "n/a", "outcome": "ENV-LIMITED",
                   "exclude_from_cicd": True, "unsupported_caps": unsupported, "bug_id": None,
                   "reason": f"Target lacks capability: {', '.join(unsupported)}"}
            counts["ENV-LIMITED"] += 1
        else:
            v = adjudicate_one(m, corpus)
            if v["verdict"] == "yes":
                bug_id = write_bug(run_id, len(bug_ids) + 1, m, v)
                bug_ids.append(bug_id)
                row = {**m, "reviewer_verdict": "yes", "outcome": "BUG", "exclude_from_cicd": False,
                       "severity": severity(m), "source_of_truth": v["source_of_truth"],
                       "bug_id": bug_id, "reason": v["reason"]}
                counts["BUG"] += 1
            elif v["verdict"] == "no":
                row = {**m, "reviewer_verdict": "no", "outcome": "EXPECTED-CORRECTED",
                       "exclude_from_cicd": False, "source_of_truth": v["source_of_truth"],
                       "bug_id": None, "reason": v["reason"]}
                counts["EXPECTED-CORRECTED"] += 1
            else:
                row = {**m, "reviewer_verdict": "missing-docs", "outcome": "missing-docs",
                       "exclude_from_cicd": True, "bug_id": None, "reason": v["reason"]}
                counts["missing-docs"] += 1
        rows.append(row)

    # Phase 3b — LLM escalation: send missing-docs-with-real-observed to the (now-accurate)
    # documentation-reviewer for the inference the deterministic pass won't risk.
    escalation = None
    if do_escalate:
        escalation = escalate(rows, corpus, run_id, escalate_limit)

    # Recompute counts + bug_ids from the (possibly escalation-mutated) rows.
    from collections import Counter
    counts = {k: 0 for k in ("PASS", "BUG", "EXPECTED-CORRECTED", "missing-docs", "ENV-LIMITED")}
    counts.update(Counter(r["outcome"] for r in rows))
    bug_ids = [r["bug_id"] for r in rows if r["outcome"] == "BUG" and r.get("bug_id")]

    # Phase-B materialisation of the NEW per-run/per-agent tree (unverified + verified mirror
    # + the two indexes). Runs after escalation so a reclassified row never orphans a file.
    tree_counts = materialize_new_tree(run_id, rows)

    ledger = {"run_id": run_id, "total_mismatches": len(mismatches),
              "outcomes": counts, "escalation": escalation,
              "unverified_tree": tree_counts, "rows": rows}
    (run_dir / "adjudication-ledger.json").write_text(json.dumps(ledger, indent=2))

    # Bug index (legacy — dual-written for one release for readers of results/bug-reports/)
    BUG_DIR.mkdir(parents=True, exist_ok=True)
    (BUG_DIR / "index.json").write_text(json.dumps(
        {"run_id": run_id, "bug_ids": bug_ids, "count": len(bug_ids)}, indent=2))

    # Phase-3 reconciliation (HF2/HF3/HF5/HF12) + unverified HF13-HF26
    recon = reconcile(run_id, run_dir, rows, bug_ids)
    ledger["reconciliation"] = recon
    (run_dir / "adjudication-ledger.json").write_text(json.dumps(ledger, indent=2))
    return ledger


def _unverified_gate(run_id: str, rows: list) -> dict:
    """HF13-HF26 over the new tree via the pure forge-gate evaluate core (single source of the
    invariant logic — the gate and reconcile agree by construction)."""
    gate_dir = WS / "agents" / "general" / "bug-reporter" / "forge-gate"
    if str(gate_dir) not in sys.path:
        sys.path.insert(0, str(gate_dir))
    try:
        import unverified_bug_gate as G  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "problems": [f"gate import failed: {exc}"], "checks": {}}
    bp = BR.bug_paths(run_id, workspace=WS)
    unv = json.loads(bp.unverified_index.read_text()) if bp.unverified_index.is_file() else {}
    ver = json.loads(bp.verified_index.read_text()) if bp.verified_index.is_file() else {}
    result = G.evaluate(rows, bp.tree, unv, ver, ADJUDICATE_DB_AVAILABLE)
    return {"status": result.status, "problems": result.problems, "checks": result.checks,
            "counts": result.counts}


def reconcile(run_id: str, run_dir: Path, rows: list, bug_ids: list) -> dict:
    problems = []
    bug_rows = [r for r in rows if r["outcome"] == "BUG"]
    files = list(BUG_DIR.glob(f"BUG-{run_id}-*.json"))
    if len(bug_rows) != len(files):
        problems.append(f"HF5: bug rows={len(bug_rows)} != bug files={len(files)}")
    for r in bug_rows:
        if r.get("reviewer_verdict") != "yes":
            problems.append(f"HF12: BUG without verdict 'yes': {r.get('scenario')}")
    for r in rows:
        if r["outcome"] == "missing-docs" and not r.get("exclude_from_cicd"):
            problems.append(f"HF12: missing-docs not excluded from CI: {r.get('scenario')}")
        if r["outcome"] not in ("BUG", "EXPECTED-CORRECTED", "missing-docs", "ENV-LIMITED", "PASS"):
            problems.append(f"HF2: non-terminal outcome: {r.get('scenario')}")

    # HF13-HF26: the unverified-bug tree, indexes, and report-only invariants.
    unverified = _unverified_gate(run_id, rows)
    if unverified.get("status") != "pass":
        problems.extend(unverified.get("problems", []))

    return {"ok": not problems, "problems": problems,
            "bug_rows": len(bug_rows), "bug_files": len(files),
            "unverified": unverified}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    if not args:
        print("usage: python adjudicate.py <RUN_ID> [--escalate] [--limit N]", file=sys.stderr)
        sys.exit(2)
    do_escalate = ("--escalate" in flags) or os.environ.get("FORGE_ADJUDICATE_ESCALATE") in ("1", "true")
    limit = int(os.environ.get("FORGE_ESCALATE_LIMIT", "40"))
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    led = run(args[0], do_escalate=do_escalate, escalate_limit=limit)
    print(f"[adjudicate] mismatches={led['total_mismatches']} outcomes={led['outcomes']}")
    if led.get("escalation"):
        e = led["escalation"]
        print(f"  escalation: eligible={e['eligible']} unique={e['unique_behaviors']} "
              f"escalated={e['escalated']} capped={e['capped']}")
    r = led["reconciliation"]
    print(f"  reconciliation: ok={r['ok']} bug_rows={r['bug_rows']} bug_files={r['bug_files']}"
          + (f" problems={r['problems']}" if r["problems"] else ""))
    sys.exit(0 if r["ok"] else 2)


if __name__ == "__main__":
    main()
