#!/usr/bin/env python3
"""Unverified-Bug Gate — enforcer for the missing-docs -> categorized-bug feature.

Mirrors the code-review gate pattern: a pure-Python core, ``evaluate(...) -> GateResult``,
that checks HF13-HF26 deterministically over a materialised run (the BugReport tree + the
adjudication ledger rows + the two indexes). The gate never invokes a model; its pass/fail
is entirely deterministic and unit-tested (test_unverified_bug_gate.py).

  exit 0 = pass (clean run, or feature does not apply — no missing-docs rows and no tree)
  exit 1 = gate failure (any HF13-HF26 violation)
  exit 2 = setup error (reports dir missing when rows exist, unreadable inputs, ...)

Usage:
    python unverified_bug_gate.py --workspace <foundry> --run-id <RUN_ID> [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _load_spec():
    """Import bugreport_spec + bugreport from the foundry, wherever we are invoked from."""
    here = Path(__file__).resolve()
    # forge-gate/ -> bug-reporter/ -> general/ -> agents/ -> agent-foundry/
    ws = here.parents[4]
    sys.path.insert(0, str(ws / "agents" / "common"))
    sys.path.insert(0, str(ws / "scripts"))
    import bugreport_spec  # noqa: E402
    return bugreport_spec


BSPEC = _load_spec()
CATEGORY_TO_PREFIX = BSPEC.CATEGORY_TO_PREFIX
PREFIX_TO_CATEGORY = {v: k for k, v in CATEGORY_TO_PREFIX.items()}
CATEGORY_ORDER = BSPEC.CATEGORY_ORDER
SEV_RANK = BSPEC.SEV_RANK
UNVERIFIED_CATEGORIES = BSPEC.UNVERIFIED_CATEGORIES
VERIFIED_ARTIFACT_THRESHOLD = {False: 7, True: 8}


@dataclass
class GateResult:
    applies: bool
    status: str  # "pass" | "fail" | "error"
    checks: dict = field(default_factory=dict)     # {"HF13": bool, ...}
    problems: list = field(default_factory=list)   # human-readable BROKEN reasons
    counts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "pass"


# --------------------------------------------------------------------------- #
# On-disk scanning
# --------------------------------------------------------------------------- #
def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa
        return default


def scan_unverified_reports(reports_root: Path) -> list:
    """Every unverified report file with its on-disk category path segment. Unverified bugs live in
    ONE top-level tree grouped by category: BugReport/unverified/{category}/{ID}.json (the owning
    agent is recorded per report in finding_agent, not in the path)."""
    out = []
    uv_root = reports_root / "unverified"
    if not uv_root.is_dir():
        return out
    for cat_dir in sorted(p for p in uv_root.iterdir() if p.is_dir()):
        for rp in sorted(cat_dir.glob("*.json")):
            rec = _read_json(rp, None)
            if isinstance(rec, dict):
                out.append({"path": rp, "agent_seg": rec.get("finding_agent"),
                            "category_seg": cat_dir.name, "report": rec})
    return out


def scan_verified_reports(reports_root: Path) -> list:
    out = []
    for agent_dir in sorted(p for p in reports_root.iterdir() if p.is_dir()) if reports_root.is_dir() else []:
        vd = agent_dir / "verified_bugs"
        if not vd.is_dir():
            continue
        for rp in sorted(vd.glob("*.json")):
            rec = _read_json(rp, None)
            if isinstance(rec, dict):
                out.append({"path": rp, "agent_seg": agent_dir.name, "report": rec})
    return out


# --------------------------------------------------------------------------- #
# The pure decision core — HF13..HF26
# --------------------------------------------------------------------------- #
def _prefix_of(bug_id: str) -> str:
    return str(bug_id).split("-", 1)[0]


def evaluate(rows: list, reports_root: Path, unverified_index: dict,
             verified_index: dict, db_available: bool) -> GateResult:
    """Deterministic HF13-HF26 check. Returns a GateResult; status 'pass' only when every
    applicable check holds, 'fail' on any BROKEN, 'error' on a setup problem."""
    rows = rows or []
    unverified_index = unverified_index or {}
    verified_index = verified_index or {}
    md_rows = [r for r in rows if r.get("outcome") == "missing-docs"]
    applies = bool(md_rows) or reports_root.is_dir()

    if not applies:
        return GateResult(applies=False, status="pass",
                          checks={}, problems=[], counts={"missing_docs_rows": 0})

    if md_rows and not reports_root.is_dir():
        return GateResult(applies=True, status="error",
                          problems=["setup: missing-docs rows present but BugReport tree absent"],
                          counts={"missing_docs_rows": len(md_rows)})

    uv_files = scan_unverified_reports(reports_root)
    v_files = scan_verified_reports(reports_root)
    problems: list = []
    checks: dict = {}

    def fail(hf: str, msg: str) -> None:
        checks[hf] = False
        problems.append(f"{hf}: {msg}")

    def ok(hf: str) -> None:
        checks.setdefault(hf, True)

    # ---- HF13 undocumented != dropped --------------------------------------
    ok("HF13")
    file_ids = {u["report"].get("bug_id") for u in uv_files}
    for r in md_rows:
        uid = r.get("unverified_bug_id")
        if not uid:
            fail("HF13", f"missing-docs row has no unverified_bug_id: {r.get('scenario')}")
        elif r.get("category") not in UNVERIFIED_CATEGORIES:
            fail("HF13", f"missing-docs row category invalid: {r.get('category')!r}")
        elif uid not in file_ids:
            fail("HF13", f"no report file for unverified_bug_id {uid}")

    # ---- HF14 deterministic category ---------------------------------------
    ok("HF14")
    for r in md_rows:
        sig = BSPEC.normalize_signals(
            expected=r.get("expected", ""), observed=r.get("observed", ""),
            spec_path=r.get("spec_path", ""), agent=r.get("agent", ""),
            scenario_text=r.get("scenario", ""), stderr=r.get("stderr", ""))
        expect_cat = BSPEC.build_category(sig)
        if r.get("category") != expect_cat:
            fail("HF14", f"row category {r.get('category')} != build_category {expect_cat} "
                         f"for {r.get('agent')}/{r.get('scenario')}")

    # ---- HF15 report-only ---------------------------------------------------
    ok("HF15")
    for r in md_rows:
        if r.get("exclude_from_cicd") is False:
            fail("HF15", f"missing-docs row not excluded from CI: {r.get('scenario')}")
    # unverified ids must not appear in any BUG add-set proxy (verified index)
    v_ids = {e.get("bug_id") for e in verified_index.get("bugs", [])}
    for u in uv_files:
        if u["report"].get("bug_id") in v_ids:
            fail("HF15", f"unverified id {u['report'].get('bug_id')} leaked into verified index")

    # ---- HF16 ID/index separation ------------------------------------------
    ok("HF16")
    for u in uv_files:
        if _prefix_of(u["report"].get("bug_id")) == "BUG":
            fail("HF16", f"unverified report carries BUG- id: {u['path'].name}")
    for e in unverified_index.get("bugs", []):
        if _prefix_of(e.get("bug_id")) == "BUG":
            fail("HF16", f"BUG- id in unverified index: {e.get('bug_id')}")
    for e in verified_index.get("bugs", []):
        if _prefix_of(e.get("bug_id")) != "BUG":
            fail("HF16", f"non-BUG id in verified index: {e.get('bug_id')}")

    # ---- HF17 vulnerability visibility / order -----------------------------
    ok("HF17")
    uv_index_bugs = unverified_index.get("bugs", [])
    vuln_files = [u for u in uv_files if u["report"].get("category") == "vulnerability"]
    vuln_in_index = [e for e in uv_index_bugs if e.get("category") == "vulnerability"]
    if len(vuln_files) != len(vuln_in_index):
        fail("HF17", f"vulnerability files={len(vuln_files)} but index vulns={len(vuln_in_index)}")
    if vuln_in_index:
        first_n = uv_index_bugs[:len(vuln_in_index)]
        if any(e.get("category") != "vulnerability" for e in first_n):
            fail("HF17", "vulnerability bugs are not sorted first in unverified-index")

    # ---- HF18 bidirectional denominator ------------------------------------
    ok("HF18")
    row_ids = {r.get("unverified_bug_id") for r in md_rows if r.get("unverified_bug_id")}
    if len(uv_files) != len(row_ids):
        fail("HF18", f"unverified files={len(uv_files)} != rows-with-id={len(row_ids)}")
    for fid in file_ids:
        if fid not in row_ids:
            fail("HF18", f"orphan report file (no ledger row): {fid}")
    for rid in row_ids:
        if rid not in file_ids:
            fail("HF18", f"dangling ledger row (no report file): {rid}")
    idx_ids = [e.get("bug_id") for e in uv_index_bugs]
    if sorted(idx_ids) != sorted(file_ids):
        fail("HF18", "unverified index ids do not map 1:1 to report files")

    # ---- HF19 ID uniqueness -------------------------------------------------
    ok("HF19")
    all_ids = [u["report"].get("bug_id") for u in uv_files] + [v["report"].get("bug_id") for v in v_files]
    seen: set = set()
    for bid in all_ids:
        if bid in seen:
            fail("HF19", f"duplicate bug_id: {bid}")
        seen.add(bid)

    # ---- HF20 path <-> category <-> prefix ---------------------------------
    ok("HF20")
    for u in uv_files:
        rep_cat = u["report"].get("category")
        id_cat = PREFIX_TO_CATEGORY.get(_prefix_of(u["report"].get("bug_id")))
        if not (u["category_seg"] == rep_cat == id_cat):
            fail("HF20", f"misfiled report {u['path'].name}: path={u['category_seg']} "
                         f"field={rep_cat} id={id_cat}")

    # ---- HF21 finding-agent integrity --------------------------------------
    ok("HF21")
    row_by_id = {r.get("unverified_bug_id"): r for r in md_rows}
    for u in uv_files:
        rep = u["report"]
        fa = rep.get("finding_agent")
        row = row_by_id.get(rep.get("bug_id"), {})
        if not fa:
            fail("HF21", f"empty finding_agent in {u['path'].name}")
        elif not (fa == u["agent_seg"] == row.get("agent")):
            fail("HF21", f"finding_agent mismatch {u['path'].name}: report={fa} "
                         f"path={u['agent_seg']} row={row.get('agent')}")
        if not rep.get("finding_endpoint") and rep.get("finding_endpoint") != "":
            fail("HF21", f"finding_endpoint absent in {u['path'].name}")

    # ---- HF22 full-capture parity ------------------------------------------
    ok("HF22")
    threshold = VERIFIED_ARTIFACT_THRESHOLD[bool(db_available)]
    for u in uv_files:
        comp = u["report"].get("artifact_completeness", {})
        for must in ("screenshot", "recording", "logs"):
            if not comp.get(must):
                fail("HF22", f"{u['path'].name} missing {must}")
        if bool(comp.get("db_dump")) != bool(db_available):
            fail("HF22", f"{u['path'].name} db_dump={comp.get('db_dump')} but db_available={db_available}")
        if u["report"].get("complete_artifact_count", 0) < threshold:
            fail("HF22", f"{u['path'].name} complete_artifact_count "
                         f"{u['report'].get('complete_artifact_count')} < {threshold}")

    # ---- HF23 citation isolation -------------------------------------------
    ok("HF23")
    for u in uv_files:
        rep = u["report"]
        if rep.get("documentation_cited") is not False or rep.get("source_of_truth") is not None:
            fail("HF23", f"unverified {u['path'].name} leaks a citation")
    for v in v_files:
        rep = v["report"]
        if rep.get("documentation_cited") is not True or rep.get("source_of_truth") is None:
            fail("HF23", f"verified {v['path'].name} missing its citation")

    # ---- HF24 verdict <-> branch -------------------------------------------
    ok("HF24")
    for u in uv_files:
        if u["report"].get("reviewer_verdict") != "missing-docs":
            fail("HF24", f"non-missing-docs report in unverified tree: {u['path'].name}")
    for v in v_files:
        if v["report"].get("reviewer_verdict") != "yes":
            fail("HF24", f"non-yes report in verified tree: {v['path'].name}")

    # ---- HF25 index integrity & total sort ---------------------------------
    ok("HF25")
    by_cat_declared = unverified_index.get("by_category", {})
    for c in UNVERIFIED_CATEGORIES:
        actual = sum(1 for u in uv_files if u["report"].get("category") == c)
        if by_cat_declared.get(c, 0) != actual:
            fail("HF25", f"by_category[{c}]={by_cat_declared.get(c)} != actual {actual}")
    expected_order = sorted(
        uv_index_bugs,
        key=lambda e: (CATEGORY_ORDER.get(e.get("category"), 9), SEV_RANK.get(e.get("severity"), 9),
                       str(e.get("finding_agent", "")), str(e.get("bug_id", ""))))
    if [e.get("bug_id") for e in uv_index_bugs] != [e.get("bug_id") for e in expected_order]:
        fail("HF25", "unverified index is not in total §4.2 sort order")

    # ---- HF26 determinism / idempotency ------------------------------------
    # The gate cannot re-run the materialiser; it verifies no wall-clock leaked into the
    # unverified output (the byte-for-byte double-run is proven by test_idempotent_materialize).
    ok("HF26")
    if "generated_at" in unverified_index:
        fail("HF26", "unverified index carries a wall-clock 'generated_at' (nondeterministic)")

    status = "fail" if problems else "pass"
    counts = {"missing_docs_rows": len(md_rows), "unverified_files": len(uv_files),
              "verified_files": len(v_files)}
    return GateResult(applies=True, status=status, checks=checks, problems=problems, counts=counts)


def build_receipt(run_id: str, result: GateResult) -> dict:
    return {
        "gate": "unverified-bug",
        "run_id": run_id,
        "applies": result.applies,
        "status": result.status,
        "ts": datetime.now(timezone.utc).isoformat(),
        "checks": result.checks,
        "problems": result.problems,
        "counts": result.counts,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _gather(ws: Path, run_id: str):
    """Load the ledger rows + the two indexes + db_available for a materialised run."""
    sys.path.insert(0, str(ws / "agents" / "common"))
    import bugreport as BR  # noqa: E402
    BR.WORKSPACE = ws
    BR.SANDBOX_ROOT = ws
    bp = BR.bug_paths(run_id, workspace=ws)
    ledger = _read_json(ws / "results" / "runs" / run_id / "adjudication-ledger.json", {"rows": []})
    unv = _read_json(bp.unverified_index, {})
    ver = _read_json(bp.verified_index, {})
    fixture = _read_json(ws / "results" / "runs" / run_id / "bug-reporter-live" / "fixture.json", {})
    db_available = bool(fixture.get("db_available", False))
    return ledger.get("rows", []), bp.tree, unv, ver, db_available


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Unverified-bug gate (HF13-HF26).")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="report applies/status without failing on setup gaps")
    args = ap.parse_args(argv[1:])
    ws = Path(args.workspace).resolve()

    out_dir = ws / "results" / "_global"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.run_id:
        if args.dry_run:
            print("unverified-bug gate (dry-run): no run-id given; nothing to check.")
            return 0
        print("ERROR: --run-id is required (or pass --dry-run).", file=sys.stderr)
        return 2

    try:
        rows, tree, unv, ver, db_available = _gather(ws, args.run_id)
    except Exception as exc:  # noqa
        print(f"ERROR: could not gather run inputs: {exc}", file=sys.stderr)
        return 2

    result = evaluate(rows, tree, unv, ver, db_available)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    (out_dir / f"unverified-bug-{ts}.json").write_text(
        json.dumps(build_receipt(args.run_id, result), indent=2))

    print(f"unverified-bug gate: status={result.status} applies={result.applies} "
          f"counts={result.counts}")
    if result.status == "fail":
        for p in result.problems:
            print(f"  BROKEN  {p}")
        return 1
    if result.status == "error":
        for p in result.problems:
            print(f"  ERROR  {p}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
