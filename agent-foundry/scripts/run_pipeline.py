#!/usr/bin/env python3
# Used by: orchestrator — clean per-run results/<date>/<time>/{TestCases,BugReport} layout across ALL agents.
"""Clean per-run output layout — the ONLY thing that lives under results/.

  results/<YYYY-MM-DD>/<HH-MM-SS>/
      TestCases/<agent>/cases.json   (every tested agent's 8-field test cases)
                       /cases.md
      BugReport/<agent>/cases.json   (ONLY agents whose FAILED test case the documentation-
                       /cases.md      reviewer confirmed: mismatch + a matching doc line -> bug;
                                      holds the failed test case(s) + the documentation evidence)

Nothing else under results/ — raw executor output is deleted after formatting; loose
folders/files are removed. Bug reporting is gated exactly by policy: a bug exists only when
the agent observed a mismatch AND the LLM documentation-reviewer finds a documentation line
that matches (verdict "yes"), citing the exact file+line.

Usage:
  python run_pipeline.py --source <RUN_ID> [--date YYYY-MM-DD --time HH-MM-SS]
        [--bug-limit N | --no-bugs]
  python run_pipeline.py --run [...]        # run all executors first, then build the layout
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
PY = str(WS / ".venv" / "bin" / "python")
TARGET = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
RESULTS = WS / "results"

import format_test_cases as F
import adjudicate as A
import orchestrate_full as O
import docreview_spec
import docreview
import core_requirements as CR
import core_testcases as CT
import core_postman as CP

TESTERS = [a for a in O.API_TESTERS if a != "create-postman-collection"]
CORE_AGENTS = set(CT.AGENT_OF_AREA.values())
_URL = {"dummyjson-com-docs.md": "https://dummyjson.com/docs",
        "dummyjson-com-docs-auth.md": "https://dummyjson.com/docs/auth",
        "dummyjson-com.md": "https://dummyjson.com/"}


def _val(prose: str) -> str | None:
    """Pull the value token out of an 8-field expected/actual sentence."""
    if not prose:
        return None
    m = re.search(r"(?:returns?|returned|equals)\s+'?([^'.\s]+)'?", prose)
    if m:
        return m.group(1)
    m = re.search(r"'([^']+)'", prose)
    return m.group(1) if m else None


def run_executor(run_dir: Path, run_id: str, agent: str) -> bool:
    rp = WS / "agents" / "api-tester" / agent / "subagent" / "run.py"
    if not rp.exists():
        return False
    # PYTHONPATH includes scripts/_record so sitecustomize installs the request recorder at startup,
    # capturing every API call this agent makes (per-agent, deduped) under results/runs/<RID>/requests/.
    rec_dir = str(WS / "scripts" / "_record")
    pp = rec_dir + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_TARGET_BASE_URL=TARGET, FORGE_MAX_ENDPOINTS="0",
               PYTHONPATH=pp, FORGE_RECORD_REQUESTS="1", FORGE_AGENT=agent)
    try:
        subprocess.run([PY, str(rp)], cwd=str(WS), env=env, capture_output=True, text=True, timeout=2400)
    except subprocess.TimeoutExpired:
        return False
    return F.find_cases_file(run_id, agent) is not None


def build_test_cases(out_root: Path, run_id: str) -> dict:
    """Format every tested agent's 8-field cases into TestCases/<agent>/; return per-agent
    {cases, fails} where fails are the Fail cases with parsed expected/observed for adjudication."""
    tc_root = out_root / "TestCases"
    per_agent = {}
    for agent in TESTERS:
        cf = F.find_cases_file(run_id, agent)
        if cf is None:
            continue
        try:
            data = json.loads(cf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        cases = F.format_agent(agent, data)
        d = tc_root / agent
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps(cases, indent=2))
        (d / "cases.md").write_text(F.to_markdown(agent, cases))
        fails = [{"tc": c, "expected": _val(c["expected_result"]), "observed": _val(c["actual_result"]),
                  "scenario": c["title_summary"]} for c in cases if c["status"] == "Fail"]
        per_agent[agent] = {"cases": cases, "fails": fails}
    return per_agent


def build_core_requirements(out_root: Path, target: str) -> dict:
    """Run the deterministic Core-Requirements contract (Auth / CRUD-products / Search & Filtering /
    Error handling) against the target, write DEEP 8-field TestCases for the three core agents
    (overriding any shallow harness output), and emit the Postman deliverable under Postman/.
    Returns {agent: {cases, fails}} so confirmed mismatches flow into BugReport like any other agent."""
    results = CR.run(target)
    by_agent = CT.to_testcases(results)
    tc_root = out_root / "TestCases"
    per_agent: dict = {a: {"cases": cases, "fails": []} for a, cases in by_agent.items()}
    for agent, cases in by_agent.items():
        d = tc_root / agent
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps(cases, indent=2))
        (d / "cases.md").write_text(CT.to_markdown(agent, cases))
    for sc in results:
        agent = CT.AGENT_OF_AREA.get(sc["area"])
        if not agent or sc["passed"] or sc["blocked"]:
            continue
        tc = next((c for c in by_agent[agent] if c["test_data"]["scenario_id"] == sc["id"]), None)
        if tc:
            per_agent[agent]["fails"].append({"tc": tc, "expected": str(sc["expected_status"]),
                                              "observed": str(sc["actual_status"]), "scenario": sc["title"]})
    # build_full adds a folder for every OTHER agent with real API-call test cases (already on
    # disk from build_test_cases), on top of the rich core-agent folders.
    collection, environment = CP.build_full(out_root, results)
    pm = out_root / "Postman"
    pm.mkdir(parents=True, exist_ok=True)
    (pm / "collection.json").write_text(json.dumps(collection, indent=2))
    (pm / "environment.json").write_text(json.dumps(environment, indent=2))
    blocked = sum(1 for r in results if r["blocked"])
    folders = len(collection["item"])
    reqs = sum(len(f["item"]) for f in collection["item"])
    print(f"Core requirements: {len(results)} scenarios across {len(by_agent)} core agents "
          f"({blocked} blocked); Postman collection: {folders} agent folders / {reqs} requests.", flush=True)
    return per_agent


def build_bug_reports(out_root: Path, per_agent: dict, bug_limit: int, do_bugs: bool) -> dict:
    """For each agent's FAILED test cases (mismatches), ask the documentation-reviewer; only a
    verdict 'yes' (a matching doc line) becomes a bug. Writes BugReport/<agent>/ ONLY for agents
    with >=1 confirmed bug, containing the failed test cases + the documentation evidence."""
    summary = {"agents_with_bugs": 0, "bugs": 0, "reviewed": 0, "considered": 0}
    if not do_bugs:
        return summary
    corpus = A.build_corpus()
    invoke = A._reviewer_invoke()
    br_root = out_root / "BugReport"
    # dedupe across agents to bound reviewer calls; adjudicate the CORE agents first so the
    # assessment's high-value, deterministic mismatches are never starved by a high-volume agent.
    seen, plan = {}, []
    ordered = ([a for a in per_agent if a in CORE_AGENTS]
               + [a for a in per_agent if a not in CORE_AGENTS])
    for agent in ordered:
        info = per_agent[agent]
        for f in info["fails"]:
            if f["expected"] is None or f["observed"] is None:
                continue
            key = (agent, f["scenario"], str(f["expected"]), str(f["observed"]))
            if key in seen:
                seen[key].append((agent, f))
            else:
                seen[key] = [(agent, f)]
                plan.append((key, agent, f))
    if bug_limit > 0:
        plan = plan[:bug_limit]
    verdicts = {}
    for key, agent, f in plan:
        m = {"agent": "api-tester-" + agent, "scenario": f["scenario"], "endpoint": "",
             "expected": f["expected"], "observed": f["observed"]}
        parsed = docreview_spec.parse_bug_report(A._bug_report_text(m))
        cand = docreview_spec.grep_corpus(corpus, A._keywords(m))
        brief = docreview_spec.brief(parsed, corpus, cand, 3)
        try:
            d = docreview.extract_json(invoke(brief)) or {}
        except Exception:  # noqa: BLE001
            d = {}
        summary["reviewed"] += 1
        verdicts[key] = d
    # collect confirmed bugs per agent
    bugs_by_agent: dict[str, list] = {}
    for key, occ in seen.items():
        d = verdicts.get(key)
        if not d or d.get("verdict") != "yes":
            continue
        sot = d.get("source_of_truth") if isinstance(d.get("source_of_truth"), dict) else None
        for agent, f in occ:
            evidence = {"reviewer_verdict": "yes",
                        "documentation": {"file": (sot or {}).get("file"), "line": (sot or {}).get("line"),
                                          "text": (sot or {}).get("text"),
                                          "source_url": _URL.get(Path((sot or {}).get("file", "")).name)},
                        "reason": d.get("reason")}
            bugs_by_agent.setdefault(agent, []).append({**f["tc"], "bug": evidence})
    for agent, bugs in bugs_by_agent.items():
        d = br_root / agent
        d.mkdir(parents=True, exist_ok=True)
        (d / "cases.json").write_text(json.dumps(bugs, indent=2))
        (d / "cases.md").write_text(_bug_md(agent, bugs))
        summary["bugs"] += len(bugs)
    summary["agents_with_bugs"] = len(bugs_by_agent)
    summary["considered"] = len(seen)
    return summary


def _bug_md(agent: str, bugs: list) -> str:
    out = [f"# Bug Report — {agent}", "", f"Confirmed documentation-backed bugs: {len(bugs)}", ""]
    for b in bugs:
        ev = b["bug"]; doc = ev["documentation"]
        out += [f"## {b['test_case_id']} — {b['title_summary']}",
                f"- **Expected:** {b['expected_result']}",
                f"- **Actual:** {b['actual_result']}",
                f"- **Status:** {b['status']}",
                f"- **Documentation evidence:** {doc.get('file')}:{doc.get('line')} "
                + (f"({doc.get('source_url')})" if doc.get("source_url") else ""),
                f"  > {doc.get('text')}",
                f"- **Reviewer reason:** {ev.get('reason')}", ""]
    return "\n".join(out)


def cleanup(run_id: str) -> list[str]:
    """Remove ONLY this api-tester run's transient output, leaving date-dir deliverables and any
    OTHER subsystem's artifacts untouched: delete results/runs/<run_id> (our executor data) — and
    runs/ only if it becomes empty — plus clearly-legacy api-tester strays (bug-reports/ or a
    top-level dir holding *.cases.json). Never touch code-review/*, another subsystem's runs/<id>,
    date dirs, or unknown files."""
    removed = []
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    runs = RESULTS / "runs"
    mine = runs / run_id
    if mine.exists():
        shutil.rmtree(mine, ignore_errors=True); removed.append(f"runs/{run_id}")
    if runs.is_dir() and not any(runs.iterdir()):
        runs.rmdir(); removed.append("runs(empty)")
    for child in RESULTS.iterdir():
        name = child.name
        if name == ".DS_Store":
            child.unlink(missing_ok=True); removed.append(name); continue
        if name == "runs" or "code-review" in name or (child.is_dir() and date_re.match(name)):
            continue
        if name == "bug-reports" or (child.is_dir() and any(child.glob("*.cases.json"))):
            shutil.rmtree(child, ignore_errors=True); removed.append(name)   # legacy api-tester stray
    return removed


def main() -> None:
    args = sys.argv[1:]

    def opt(flag, default=None):
        return args[args.index(flag) + 1] if flag in args else default

    date = opt("--date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tm = opt("--time") or datetime.now(timezone.utc).strftime("%H-%M-%S")
    run_id = opt("--source") or f"{date}_{tm}"
    out_root = RESULTS / date / tm
    do_bugs = "--no-bugs" not in args
    bug_limit = int(opt("--bug-limit", "40"))

    if "--run" in args:
        rd = RESULTS / "runs" / run_id
        (rd / "agents").mkdir(parents=True, exist_ok=True)
        for i, a in enumerate(TESTERS, 1):
            ok = F.find_cases_file(run_id, a) is not None or run_executor(rd, run_id, a)
            print(f"[exec {i}/{len(TESTERS)}] {a}: {'ok' if ok else 'FAIL'}", flush=True)

    print(f"building layout -> results/{date}/{tm}/", flush=True)
    per_agent = build_test_cases(out_root, run_id)
    print(f"TestCases: {len(per_agent)} agents", flush=True)
    import request_cases
    req_dir = RESULTS / "runs" / run_id / "requests"
    appended = request_cases.augment(out_root, req_dir, CORE_AGENTS)
    if appended:
        print(f"Recorded requests folded in: {sum(appended.values())} request-derived cases "
              f"across {len(appended)} agents.", flush=True)
    if "--no-core" not in args:
        core = build_core_requirements(out_root, TARGET)
        per_agent.update(core)   # deep core-requirement cases override the shallow harness output
    bug = build_bug_reports(out_root, per_agent, bug_limit, do_bugs)
    print(f"BugReport: {bug['agents_with_bugs']} agents / {bug['bugs']} bugs "
          f"(reviewed {bug['reviewed']} of {bug['considered']} unique mismatches)", flush=True)
    removed = cleanup(run_id)
    print(f"cleanup removed from results/: {removed}", flush=True)
    import guardrails
    gates = guardrails.core_gate(out_root)
    for g in gates:
        print(f"{g['id']} {g['name']}: {g['status']} — {g['detail']}", flush=True)
    print(f"DONE: results/{date}/{tm}/  TestCases={len(per_agent)} BugReportAgents={bug['agents_with_bugs']}", flush=True)
    if any(g["status"] == "FAIL" and g.get("hard") for g in gates):
        sys.exit(1)


if __name__ == "__main__":
    main()
