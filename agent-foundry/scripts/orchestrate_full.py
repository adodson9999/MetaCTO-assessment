#!/usr/bin/env python3
# Used by: shared core (API_TESTERS/GENERALS + run loop) — used by ALL agent workflows via make_all_test_cases, produce_all_testcases, run_pipeline, build_postman, handoff_all, full_framework_runs.
"""orchestration-full driver — faithful realization of the /orchestration-full skill.

Runs every api-tester agent (40) + every general agent (3) for one RUN_ID against
the live local target. Each agent's run.py self-iterates all endpoints in
data/openapi.json, so invoking each agent once == "every agent runs on every
endpoint" (skill invariant #2/#7).

Deviations from the skill prose, with reasons:
  - Per-agent timeout is 1800s, not 300s: 22 endpoints on a local 14b model
    routinely exceed 300s. A killed agent is recorded as a "Code Update" outcome
    (skill invariant #4 — agent ran, fixture/time not applicable, no bug).
  - The "per-endpoint x per-agent" matrix collapses to "per-agent (self-iterating
    endpoints)" because that is how the harness is actually built. The endpoint
    list is still recorded in state for transparency.

Resumable: agents already in agents_completed are skipped. State is written after
every agent (skill invariant #9). No output is discarded (invariant #10).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ["FORGE_WORKSPACE"]).resolve()
TARGET = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
PY = str(WS / ".venv" / "bin" / "python")
PER_AGENT_TIMEOUT = int(os.environ.get("FORGE_AGENT_TIMEOUT", "1800"))

API_TESTERS = [
    "validate-request-payloads", "verify-response-status-codes", "test-authentication-flows",
    "check-authorization-rules", "validate-json-schema-responses", "test-pagination-behavior",
    "verify-error-message-clarity", "test-rate-limit-enforcement", "validate-query-parameter-handling",
    "test-idempotency-of-endpoints", "verify-content-type-negotiation", "validate-null-empty-fields",
    "test-timeout-handling", "verify-crud-operation-integrity", "test-concurrent-request-handling",
    "validate-header-propagation", "test-webhook-delivery", "run-regression-suite",
    "track-defect-density", "validate-api-versioning-behavior", "test-ssl-tls-enforcement",
    "verify-caching-headers", "validate-correlation-id-propagation", "test-bulk-operation-endpoints",
    "verify-audit-log-generation", "validate-search-and-filter-queries", "test-file-upload-and-download",
    "verify-sorting-behavior", "test-event-driven-api-triggers", "test-ip-allowlist-enforcement",
    "test-api-gateway-routing", "verify-third-party-oauth-integration", "test-multipart-form-data-handling",
    "validate-retry-after-header-compliance", "test-soft-delete-behavior", "validate-graphql-depth-limits",
    "test-long-polling-support", "verify-enum-value-restrictions", "measure-api-consumer-satisfaction",
    "create-postman-collection",
]
# test-case-creator is NOT a batch agent here — it is invoked PER api-tester, right after
# each one finishes (bounded, ~5 cases), then the run moves on. This is forced by guardrail
# G11. The single 200-case batch call is forbidden (it timed out on the 14b).
PRODUCER = "test-case-creator"
GENERALS = ["documentation-reviewer", "run-cicd-pipeline", "bug-reporter"]
TCC_AGENT_TIMEOUT = int(os.environ.get("FORGE_TESTCASE_AGENT_TIMEOUT", "300"))  # bounded per-agent


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_scoped_producer(run_dir: Path, run_id: str, agent_name: str) -> dict:
    """PER-AGENT producer: author ONLY this api-tester's cases (FORGE_TESTCASE_AGENT), bounded
    by TCC_AGENT_TIMEOUT so it can never hang the run. Persists the agent's registry slice and
    returns an invocation record {agent, mode:'per-agent', cases, seconds, timed_out, sentinel}.
    This is the producer-per-agent pattern guardrail G11 forces; a batch call is never made."""
    target = f"api-tester-{agent_name}"
    rec = {"agent": target, "mode": "per-agent", "started_at": now(),
           "cases": 0, "seconds": 0.0, "timed_out": False, "sentinel": True}
    rp = WS / "agents" / "general" / PRODUCER / "subagent" / "run.py"
    full_manifest = WS / "data" / "test-case-creator" / "manifest.full.json"
    if not rp.exists() or not full_manifest.exists():
        rec["reason"] = "producer run.py or manifest.full.json missing"
        return rec
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_TESTCASE_MANIFEST=str(full_manifest), FORGE_TESTCASE_AGENT=target)
    pdir = run_dir / "agents" / "general-test-case-creator"
    pdir.mkdir(parents=True, exist_ok=True)
    t0 = datetime.now(timezone.utc)
    try:
        proc = subprocess.run([PY, str(rp)], cwd=str(WS), env=env,
                              capture_output=True, text=True, timeout=TCC_AGENT_TIMEOUT)
        (pdir / f"{run_id}-{agent_name}-stdout.txt").write_text(proc.stdout or "")
        (pdir / f"{run_id}-{agent_name}-stderr.txt").write_text(proc.stderr or "")
    except subprocess.TimeoutExpired:
        rec["timed_out"] = True
        (pdir / f"{run_id}-{agent_name}-stderr.txt").write_text(f"TIMEOUT after {TCC_AGENT_TIMEOUT}s\n")
    rec["seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)

    # Read this agent's emitted slice (scoped run => emitted-registry holds only this agent).
    try:
        emitted = json.loads((run_dir / "general-test-case-creator.emitted-registry.json").read_text())
    except (OSError, json.JSONDecodeError):
        emitted = []
    mine = [c for c in emitted if c.get("agent") == target
            or str(c.get("tc_id", "")).startswith(target)]
    real = [c for c in mine if c.get("outcome") != "ERROR"]
    slice_dir = run_dir / "test-case-registry"
    slice_dir.mkdir(parents=True, exist_ok=True)
    (slice_dir / f"{agent_name}.json").write_text(json.dumps(mine, indent=2))
    rec.update({"cases": len(real), "sentinel": (len(real) == 0)})
    return rec


def run_py_path(name: str) -> Path:
    p = WS / "agents" / "api-tester" / name / "subagent" / "run.py"
    if p.exists():
        return p
    return WS / "agents" / "general" / name / "subagent" / "run.py"


def load_endpoints() -> list[dict]:
    spec = json.loads((WS / "data" / "openapi.json").read_text())
    out = []
    for path, methods in spec["paths"].items():
        for method in methods:
            fam = path.split("/{")[0]
            out.append({"endpoint_id": f"{method.upper()}-{path}", "method": method.upper(),
                        "path": path, "url_family": fam})
    return out


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else "RUN-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = WS / "results" / "runs" / run_id
    (run_dir / "agents").mkdir(parents=True, exist_ok=True)
    state_file = run_dir / "orchestration-state.json"

    endpoints = load_endpoints()
    (run_dir / "endpoints.json").write_text(json.dumps(endpoints, indent=2))

    if state_file.exists():
        state = json.loads(state_file.read_text())
    else:
        state = {"run_id": run_id, "run_type": "full", "env_mode": "ollama",
                 "forge_workspace": str(WS), "target": TARGET, "started_at": now(),
                 "endpoint_count": len(endpoints), "agent_order": API_TESTERS + GENERALS,
                 "agents_completed": [], "agents": {}, "current_agent": None, "completed": False}
        state_file.write_text(json.dumps(state, indent=2))

    order = API_TESTERS + GENERALS
    producer_invocations = state.get("producer_invocations", [])
    for idx, name in enumerate(order, 1):
        if name in state["agents_completed"]:
            print(f"[{idx}/{len(order)}] SKIP (done): {name}", flush=True)
            continue

        kind = "api-tester" if name in API_TESTERS else "general"
        full = f"{kind}-{name}"
        rp = run_py_path(name)
        adir = run_dir / "agents" / full
        adir.mkdir(parents=True, exist_ok=True)
        out_f = adir / f"{run_id}-stdout.txt"
        err_f = adir / f"{run_id}-stderr.txt"

        state["current_agent"] = name
        state_file.write_text(json.dumps(state, indent=2))

        rec = {"agent": full, "kind": kind, "run_py": str(rp), "started_at": now()}
        if not rp.exists():
            rec.update({"outcome": "Code Update", "reason": "run.py not found",
                        "finished_at": now()})
            err_f.write_text("run.py not found\n")
            print(f"[{idx}/{len(order)}] MISSING: {name} -> Code Update", flush=True)
        else:
            env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
                       FORGE_TARGET_BASE_URL=TARGET, FORGE_MAX_ENDPOINTS="0")
            t0 = datetime.now(timezone.utc)
            print(f"[{idx}/{len(order)}] RUN: {name} ...", flush=True)
            try:
                proc = subprocess.run([PY, str(rp)], cwd=str(WS), env=env,
                                      capture_output=True, text=True, timeout=PER_AGENT_TIMEOUT)
                if proc.stdout: out_f.write_text(proc.stdout)
                if proc.stderr: err_f.write_text(proc.stderr)
                dt = (datetime.now(timezone.utc) - t0).total_seconds()
                # Artifacts present == real outcome; non-zero exit with artifacts is
                # often just the cosmetic summary-print KeyError (artifacts already written).
                cases = list(run_dir.glob(f"{full}*.cases.json")) + list(run_dir.glob(f"*{name}*.json"))
                if proc.returncode == 0:
                    rec.update({"outcome": "PASS", "returncode": 0, "seconds": round(dt, 1)})
                elif cases:
                    rec.update({"outcome": "PASS", "returncode": proc.returncode,
                                "note": "non-zero exit but artifacts written", "seconds": round(dt, 1)})
                else:
                    rec.update({"outcome": "Code Update", "returncode": proc.returncode,
                                "reason": "no artifacts", "seconds": round(dt, 1)})
                print(f"    -> {rec['outcome']} rc={proc.returncode} {round(dt,1)}s", flush=True)
            except subprocess.TimeoutExpired:
                dt = (datetime.now(timezone.utc) - t0).total_seconds()
                err_f.write_text(f"TIMEOUT after {PER_AGENT_TIMEOUT}s\n")
                rec.update({"outcome": "Code Update", "reason": f"timeout {PER_AGENT_TIMEOUT}s",
                            "seconds": round(dt, 1)})
                print(f"    -> TIMEOUT -> Code Update", flush=True)
            rec["finished_at"] = now()

        state["agents"][name] = rec
        state["agents_completed"].append(name)
        state["current_agent"] = None
        state_file.write_text(json.dumps(state, indent=2))

        # G11 — PER-AGENT PRODUCER: the moment this api-tester finishes, author its cases
        # (bounded), persist the slice, then move on. Never a single batch call.
        if name in API_TESTERS and rp.exists():
            prec = run_scoped_producer(run_dir, run_id, name)
            producer_invocations.append(prec)
            state["producer_invocations"] = producer_invocations
            state_file.write_text(json.dumps(state, indent=2))
            print(f"    -> producer({name}): {prec['cases']} cases {prec['seconds']}s"
                  + (" TIMEOUT" if prec["timed_out"] else "")
                  + (" SENTINEL" if prec["sentinel"] else ""), flush=True)

    # Merge per-agent registry slices into the single authoritative registry.
    combined, slice_dir = [], run_dir / "test-case-registry"
    for sl in sorted(slice_dir.glob("*.json")) if slice_dir.is_dir() else []:
        try:
            combined.extend(json.loads(sl.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    (run_dir / "test-case-registry.json").write_text(json.dumps(
        {"run_id": run_id, "writer": "test-case-creator (per-agent)",
         "agents_covered": len({c.get("agent") for c in combined}),
         "total_cases": len(combined), "cases": combined}, indent=2))
    (run_dir / "producer-invocations.json").write_text(json.dumps(
        {"run_id": run_id, "mode": "per-agent",
         "invocations": producer_invocations,
         "agents_with_cases": sum(1 for i in producer_invocations if i["cases"] > 0),
         "sentinels": sum(1 for i in producer_invocations if i["sentinel"]),
         "timeouts": sum(1 for i in producer_invocations if i["timed_out"])}, indent=2))

    # Phase 3 — finalize
    state["completed"] = True
    state["completed_at"] = now()
    state_file.write_text(json.dumps(state, indent=2))

    # execution_status = did the agent process run + write artifacts (drives resume/skip).
    # This is NOT a quality verdict; the guardrail layer computes the honest outcome below.
    execution_status = {}
    for r in state["agents"].values():
        execution_status[r["outcome"]] = execution_status.get(r["outcome"], 0) + 1

    # Phase 3b — guardrail layer: honest per-agent classification + G1..G10 checks.
    # Reclassifies "artifacts => PASS" into PASS/PARTIAL/FAIL/ENV-LIMITED/EMPTY/ERROR and
    # writes guardrails-report.json. Never touches the DummyJSON app.
    quality = {}
    guardrail_fail = False
    hard_fail = False
    try:
        import guardrails  # scripts/ is already on sys.path via PY's cwd; ensure import
    except ImportError:
        sys.path.insert(0, str(WS / "scripts"))
        import guardrails  # noqa: E402
    try:
        report = guardrails.run(run_id)
        quality = report.get("outcome_distribution", {})
        guardrail_fail = report.get("any_fail", False)
        hard_fail = report.get("any_hard_fail", False)
        print("GUARDRAILS:", json.dumps(quality), "any_fail=", guardrail_fail,
              "any_hard_fail=", hard_fail, flush=True)
        for c in report.get("checks", []):
            tag = " [HARD]" if c.get("hard") else ""
            print(f"  {c['id']} {c['name']}{tag}: {c['status']} — {c['detail']}", flush=True)
    except Exception as exc:  # noqa: BLE001 — finalize must never crash the run
        print(f"GUARDRAILS ERROR: {exc}", flush=True)

    # Phase 3c — adjudication loop (orchestrator-full.md §3): turn scenario mismatches
    # into reviewer-gated bug reports + a reconciled adjudication-ledger.json.
    adjudication = {}
    try:
        import adjudicate  # noqa: E402
        # Opt-in LLM escalation of missing-docs (FORGE_ADJUDICATE_ESCALATE=1); needs a backend
        # that generalizes — the local 14b reviewer does not (returns invalid verdicts on OOD
        # inputs), so default off and run it separately on a stronger model when wanted.
        do_esc = os.environ.get("FORGE_ADJUDICATE_ESCALATE") in ("1", "true")
        led = adjudicate.run(run_id, do_escalate=do_esc,
                             escalate_limit=int(os.environ.get("FORGE_ESCALATE_LIMIT", "40")))
        adjudication = {"total_mismatches": led["total_mismatches"],
                        "outcomes": led["outcomes"],
                        "escalation": led.get("escalation"),
                        "reconciliation_ok": led["reconciliation"]["ok"]}
        print("ADJUDICATION:", json.dumps(adjudication), flush=True)
    except Exception as exc:  # noqa: BLE001 — finalize must never crash the run
        print(f"ADJUDICATION ERROR: {exc}", flush=True)

    # Phase 3d — report bugs USING THE BUG-REPORTER AGENT on the live failed features
    # (FAIL/EMPTY/ERROR). The agent emits each report's decision; the deterministic step
    # materializes the files. Needs the backend; guarded so finalize never crashes.
    bug_reporting = {}
    try:
        import report_bugs  # noqa: E402
        bug_reporting = report_bugs.run(run_id)
        print("BUG-REPORTER:", json.dumps(bug_reporting), flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"BUG-REPORTER ERROR: {exc}", flush=True)

    # HARD guardrail enforcement: a hard-check failure (e.g. G11 per-agent producer not
    # enforced) marks the run BROKEN and exits non-zero. This is the "force it to happen".
    producer_summary = _read_json(run_dir / "producer-invocations.json", {})
    if hard_fail:
        state["completed"] = False
        state["status"] = "BROKEN"
        state_file.write_text(json.dumps(state, indent=2))

    summary = {"run_id": run_id, "run_type": "full", "started_at": state["started_at"],
               "completed_at": state["completed_at"], "endpoint_count": len(endpoints),
               "total_agents": len(order),
               "execution_status": execution_status,   # ran-and-wrote-artifacts (not quality)
               "quality_outcomes": quality,            # honest verdict from guardrails
               "producer": {"mode": "per-agent",
                            "agents_with_cases": producer_summary.get("agents_with_cases"),
                            "sentinels": producer_summary.get("sentinels"),
                            "timeouts": producer_summary.get("timeouts")},
               "adjudication": adjudication,           # §3 ledger summary (mismatch -> verdict -> bug)
               "bug_reporting": bug_reporting,         # bug-reporter agent over live failures
               "guardrails_any_fail": guardrail_fail,
               "guardrails_any_hard_fail": hard_fail,
               "status": "BROKEN" if hard_fail else "completed",
               "agents": {k: {"execution_status": v["outcome"], "seconds": v.get("seconds")}
                          for k, v in state["agents"].items()}}
    (run_dir / "pipeline-summary.json").write_text(json.dumps(summary, indent=2))
    print("DONE: execution=", json.dumps(execution_status), "quality=", json.dumps(quality),
          "status=", summary["status"], flush=True)
    if hard_fail:
        print("RUN BROKEN: a HARD guardrail failed (see G11/per-agent-producer).", flush=True)
        sys.exit(2)


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


if __name__ == "__main__":
    main()
