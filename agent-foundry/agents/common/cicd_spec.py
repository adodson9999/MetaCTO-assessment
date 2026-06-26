"""Canonical structure for the API "CI/CD Pipeline Runner" task (general position).

ONE definition of the pipeline classification + the per-field evaluation, shared by:
  - the deterministic gold reference (data/run-cicd-pipeline/build_gold.py), and
  - the harness (agents/common/cicd.py) — which scores whatever pipeline-summary an
    agent emitted on exactly the same field scheme.

Pure: no env, no I/O, no LLM, no HTTP, no subprocess. Keeps agent output and the gold
summary on the same (scenario x field) key scheme so the judge can compare them
field-for-field.

What the agent actually does (the measurable analytical core). The "CI/CD Pipeline
Runner" task (read manifest -> install Ollama -> pull model -> serve -> spawn every
enabled agent as a subprocess in batches of 4 -> capture stdout/stderr -> classify ->
emit pipeline-summary.json -> exit 1 on any failure) splits into two halves:

  * the DETERMINISTIC half (install Ollama, pull the model, start/stop the server,
    spawn the subprocesses, enforce the 300s timeout, manage PIDs, set the pipeline
    exit code, block deployment) is the CI harness's job — NOT the agent's, and the
    agent is debate-gated against performing any of it (cicd_prompt L11); and

  * the ANALYTICAL half — given one pipeline run's captured artifacts (the [backend]
    config block, the manifest, and each listed agent's {exit_code, timed_out, captured
    stdout}) classify every ENABLED agent and emit the exact ten-field
    pipeline-summary.json — is the agent's job. This is what the four frameworks
    implement and what the judge measures, exactly mirroring the run-regression-suite
    precedent (agent emits the report; a separate program acts on it).

Why fixtures (Phase-2). The task's own inputs are local, air-gapped fixtures under
data/run-cicd-pipeline/scenarios/<scenario>/ (a manifest.json + per-agent captured
stdout files), one scenario per classification shape. DummyJSON exposes no CI surface
and is never touched. Backend = Ollama, local; the Ollama server is NOT started by this
build (the agent never starts it, and the phase-4 script only probes it read-only).

The classification contract (the exact algorithm the agent must reproduce), with an
EXPLICIT precedence so the three failure buckets are mutually exclusive (the task's
step-6/step-7 prose leaves the timed-out-and-also-unparseable case ambiguous; the
debate gate pins it):

  ENABLED        = manifest objects whose `enabled` is literally true. Objects with
                   enabled=false, or with no enabled key, are excluded entirely.
  agents_total   = count of ENABLED.
  For each ENABLED agent, in this precedence order (first match wins):
    1. TIMED_OUT  if its execution record is marked timed out (exit code 124).
    2. MALFORMED  else if json.loads of its FULL captured stdout raises (empty or
                  whitespace-only stdout counts as a parse failure).
    3. FAILED     else if its exit code is non-zero.
    4. PASSED     else (exit code 0 AND stdout parses as valid JSON).
  agents_passed  = count of PASSED.
  agents_failed  = count of FAILED + MALFORMED + TIMED_OUT (the three partition the
                   non-passing enabled agents; no agent is in two buckets).

The emitted pipeline-summary has EXACTLY these ten fields (task-mandated names):
  run_id, model, model_digest, agents_total, agents_passed, agents_failed,
  failed_agents (list of names), malformed_agents (list of names),
  timed_out_agents (list of names), timestamp.

Metric — Pipeline Agent Pass Rate = agents_passed / agents_total * 100. Pass = exactly
100 (every enabled agent exited 0 with valid-JSON stdout); Fail = any value < 100 (a
single failed/malformed/timed-out agent sets FAIL_COUNT > 0 and blocks deployment, no
tolerance). The forge judge ranks the four frameworks on Pipeline-Summary Fidelity (the
fraction of scenario x field cells matching gold) because the headline Pass Rate is a
property of the fixtures, not the framework.
"""
from __future__ import annotations

import json

# --------------------------------------------------------------------------- #
# The scenario catalogue: each is one full pipeline run's captured artifacts in a
# named classification shape. This is the static truth; build_gold.py materialises the
# fixtures + cicd_spec.json (the agents' briefing input) and derives the gold summaries.
#
# Each scenario carries the [backend] config block the pipeline read, the resolved
# model_digest (from `ollama list`), the RUN_ID + TIMESTAMP, the manifest.json content,
# and the per-listed-agent execution record {exit_code, timed_out, stdout}. Execution
# records are provided for EVERY manifest entry (enabled or not) so the enabled-filter
# is genuinely exercised.
# --------------------------------------------------------------------------- #
SCENARIOS = [
    {
        "scenario": "clean_all_pass",
        "note": "Every enabled agent exits 0 with valid-JSON stdout; one disabled agent "
                "is present and must be excluded. Pipeline PASSES (100%).",
        "backend": {"provider": "ollama", "model": "llama3.1:8b"},
        "model_digest": "42182419e950",
        "run_id": "2026-06-26T14-30-00",
        "timestamp": "2026-06-26T14:33:07+00:00",
        "manifest": [
            {"name": "auth-flow-checker", "spec_path": "agents/auth-flow-checker.prompt.md", "enabled": True},
            {"name": "schema-validator", "spec_path": "agents/schema-validator.prompt.md", "enabled": True},
            {"name": "rate-limit-prober", "spec_path": "agents/rate-limit-prober.prompt.md", "enabled": True},
            {"name": "pagination-checker", "spec_path": "agents/pagination-checker.prompt.md", "enabled": True},
            {"name": "legacy-soap-tester", "spec_path": "agents/legacy-soap-tester.prompt.md", "enabled": False},
        ],
        "executions": {
            "auth-flow-checker": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "auth-flow-checker", "status": "pass", "checks": 12}'},
            "schema-validator": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "schema-validator", "status": "pass", "violations": 0}'},
            "rate-limit-prober": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "rate-limit-prober", "status": "pass", "limit": 100}'},
            "pagination-checker": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "pagination-checker", "status": "pass", "pages": 3}'},
            # disabled: its record is ignored entirely (excluded by the enabled-filter).
            "legacy-soap-tester": {"exit_code": 1, "timed_out": False, "stdout": "this agent is disabled and must not be classified"},
        },
    },
    {
        "scenario": "mixed_batch",
        "note": "Six enabled agents across two batches of four: one non-zero exit "
                "(FAILED), one zero-exit-but-non-JSON stdout (MALFORMED), one timed out "
                "(TIMED_OUT, exit 124), three pass. Pipeline FAILS (33.33%).",
        "backend": {"provider": "ollama", "model": "llama3.1:8b"},
        "model_digest": "42182419e950",
        "run_id": "2026-06-26T15-02-44",
        "timestamp": "2026-06-26T15:09:31+00:00",
        "manifest": [
            {"name": "auth-flow-checker", "spec_path": "agents/auth-flow-checker.prompt.md", "enabled": True},
            {"name": "schema-validator", "spec_path": "agents/schema-validator.prompt.md", "enabled": True},
            {"name": "rate-limit-prober", "spec_path": "agents/rate-limit-prober.prompt.md", "enabled": True},
            {"name": "pagination-checker", "spec_path": "agents/pagination-checker.prompt.md", "enabled": True},
            {"name": "webhook-delivery-tester", "spec_path": "agents/webhook-delivery-tester.prompt.md", "enabled": True},
            {"name": "idempotency-prober", "spec_path": "agents/idempotency-prober.prompt.md", "enabled": True},
        ],
        "executions": {
            "auth-flow-checker": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "auth-flow-checker", "status": "pass"}'},
            # exit 1 -> FAILED (stdout is valid JSON, but exit code is non-zero).
            "schema-validator": {"exit_code": 1, "timed_out": False, "stdout": '{"agent": "schema-validator", "status": "fail", "violations": 4}'},
            # exit 0 but stdout is not JSON -> MALFORMED.
            "rate-limit-prober": {"exit_code": 0, "timed_out": False, "stdout": "Traceback (most recent call last):\n  RuntimeError: backend refused connection"},
            "pagination-checker": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "pagination-checker", "status": "pass"}'},
            # timed out -> TIMED_OUT (exit 124); its partial stdout would also fail to parse,
            # but TIMED_OUT takes precedence and it must NOT be double-counted as MALFORMED.
            "webhook-delivery-tester": {"exit_code": 124, "timed_out": True, "stdout": '{"agent": "webhook-delivery-tester", "status": "in_pro'},
            # exit 2 -> FAILED.
            "idempotency-prober": {"exit_code": 2, "timed_out": False, "stdout": '{"agent": "idempotency-prober", "status": "error"}'},
        },
    },
    {
        "scenario": "disabled_and_empty_stdout",
        "note": "Five manifest entries, two disabled (excluded). Of the three enabled: "
                "two pass, one exits 0 with EMPTY stdout (MALFORMED — empty is a parse "
                "failure). Pipeline FAILS (66.67%).",
        "backend": {"provider": "ollama", "model": "llama3.1:8b"},
        "model_digest": "42182419e950",
        "run_id": "2026-06-26T16-20-10",
        "timestamp": "2026-06-26T16:24:55+00:00",
        "manifest": [
            {"name": "auth-flow-checker", "spec_path": "agents/auth-flow-checker.prompt.md", "enabled": True},
            {"name": "deprecated-v1-tester", "spec_path": "agents/deprecated-v1-tester.prompt.md", "enabled": False},
            {"name": "schema-validator", "spec_path": "agents/schema-validator.prompt.md", "enabled": True},
            {"name": "experimental-grpc-prober", "spec_path": "agents/experimental-grpc-prober.prompt.md", "enabled": False},
            {"name": "cors-header-checker", "spec_path": "agents/cors-header-checker.prompt.md", "enabled": True},
        ],
        "executions": {
            "auth-flow-checker": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "auth-flow-checker", "status": "pass"}'},
            "deprecated-v1-tester": {"exit_code": 0, "timed_out": False, "stdout": '{"ignored": true}'},
            "schema-validator": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "schema-validator", "status": "pass"}'},
            "experimental-grpc-prober": {"exit_code": 124, "timed_out": True, "stdout": ""},
            # exit 0 but empty stdout -> MALFORMED (json.loads("") raises).
            "cors-header-checker": {"exit_code": 0, "timed_out": False, "stdout": ""},
        },
    },
    {
        "scenario": "timeout_precedence",
        "note": "Exercises the TIMED_OUT-over-MALFORMED precedence: one agent timed out "
                "(exit 124) with empty stdout (would also be a parse failure) and must be "
                "TIMED_OUT only; one FAILED, two pass. Pipeline FAILS (50%).",
        "backend": {"provider": "ollama", "model": "llama3.1:8b"},
        "model_digest": "42182419e950",
        "run_id": "2026-06-26T17-45-00",
        "timestamp": "2026-06-26T17:51:18+00:00",
        "manifest": [
            {"name": "soft-delete-prober", "spec_path": "agents/soft-delete-prober.prompt.md", "enabled": True},
            {"name": "ssl-tls-enforcer", "spec_path": "agents/ssl-tls-enforcer.prompt.md", "enabled": True},
            {"name": "bulk-op-tester", "spec_path": "agents/bulk-op-tester.prompt.md", "enabled": True},
            {"name": "correlation-id-checker", "spec_path": "agents/correlation-id-checker.prompt.md", "enabled": True},
        ],
        "executions": {
            # timed out with empty stdout -> TIMED_OUT only (precedence over MALFORMED).
            "soft-delete-prober": {"exit_code": 124, "timed_out": True, "stdout": ""},
            "ssl-tls-enforcer": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "ssl-tls-enforcer", "status": "pass"}'},
            "bulk-op-tester": {"exit_code": 0, "timed_out": False, "stdout": '{"agent": "bulk-op-tester", "status": "pass"}'},
            # exit 3 -> FAILED.
            "correlation-id-checker": {"exit_code": 3, "timed_out": False, "stdout": '{"agent": "correlation-id-checker", "status": "fail"}'},
        },
    },
]

# The ten exact output fields, in order. Each is one scored cell per scenario.
REPORT_FIELDS = [
    "run_id",
    "model",
    "model_digest",
    "agents_total",
    "agents_passed",
    "agents_failed",
    "failed_agents",
    "malformed_agents",
    "timed_out_agents",
    "timestamp",
]

# The four mutually-exclusive classification categories.
PASSED, FAILED, MALFORMED, TIMED_OUT = "PASSED", "FAILED", "MALFORMED", "TIMED_OUT"

TIMEOUT_EXIT_CODE = 124


# --------------------------------------------------------------------------- #
# Classification — one execution record -> exactly one category (precedence order)
# --------------------------------------------------------------------------- #
def stdout_parses_as_json(text: str) -> bool:
    """True iff json.loads of the FULL stdout text succeeds. Empty or whitespace-only
    stdout counts as a parse failure (json.loads('') raises)."""
    if text is None:
        return False
    try:
        json.loads(text)
        return True
    except Exception:  # noqa - any parse exception -> not valid JSON
        return False


def classify(exec_record: dict) -> str:
    """Classify one enabled agent's execution record into exactly one of
    PASSED / FAILED / MALFORMED / TIMED_OUT, with the gated precedence:

        1. TIMED_OUT  if timed out (record timed_out true, or exit code 124)
        2. MALFORMED  else if stdout does not parse as JSON
        3. FAILED     else if exit code != 0
        4. PASSED     else
    """
    rec = exec_record or {}
    exit_code = rec.get("exit_code")
    timed_out = bool(rec.get("timed_out")) or exit_code == TIMEOUT_EXIT_CODE
    if timed_out:
        return TIMED_OUT
    if not stdout_parses_as_json(rec.get("stdout", "")):
        return MALFORMED
    if exit_code != 0:
        return FAILED
    return PASSED


def enabled_agents(manifest: list) -> list:
    """The manifest entries whose `enabled` is literally true, in manifest order.
    Entries with enabled=false, or with no enabled key, are excluded."""
    return [m for m in (manifest or []) if m.get("enabled") is True]


# --------------------------------------------------------------------------- #
# The deterministic pipeline summary
# --------------------------------------------------------------------------- #
def build_reference_summary(scenario: dict) -> dict:
    """The canonical CORRECT ten-field pipeline-summary for one scenario, derived
    deterministically from the manifest + execution records. This is the gold; the
    agents must reproduce the same ten fields from their brief."""
    enabled = enabled_agents(scenario["manifest"])
    execs = scenario.get("executions", {})

    cats: dict[str, str] = {}
    for m in enabled:
        name = m["name"]
        cats[name] = classify(execs.get(name, {}))

    # Arrays preserve manifest order; each enabled name lands in exactly one bucket.
    order = [m["name"] for m in enabled]
    passed = [n for n in order if cats[n] == PASSED]
    failed_agents = [n for n in order if cats[n] == FAILED]
    malformed_agents = [n for n in order if cats[n] == MALFORMED]
    timed_out_agents = [n for n in order if cats[n] == TIMED_OUT]

    agents_total = len(enabled)
    agents_passed = len(passed)
    agents_failed = len(failed_agents) + len(malformed_agents) + len(timed_out_agents)

    return {
        "run_id": scenario["run_id"],
        "model": scenario["backend"]["model"],
        "model_digest": scenario["model_digest"],
        "agents_total": agents_total,
        "agents_passed": agents_passed,
        "agents_failed": agents_failed,
        "failed_agents": failed_agents,
        "malformed_agents": malformed_agents,
        "timed_out_agents": timed_out_agents,
        "timestamp": scenario["timestamp"],
    }


def pass_rate(summary: dict) -> float:
    """Pipeline Agent Pass Rate (%) = agents_passed / agents_total * 100, 2dp.
    Zero enabled agents => 0.0 (nothing could pass). Coerces counts defensively
    because this is also called on the untrusted agent summary (which may carry a
    stringified count)."""
    denom = _as_int(summary.get("agents_total")) or 0
    if not denom:
        return 0.0
    n = _as_int(summary.get("agents_passed")) or 0
    return round(100.0 * n / denom, 2)


def would_block_deployment(summary: dict) -> bool:
    """The task's gate: any non-passing enabled agent blocks deployment (pass rate
    strictly below 100)."""
    return (_as_int(summary.get("agents_failed")) or 0) > 0


# --------------------------------------------------------------------------- #
# Per-field scoring (agent summary vs gold summary) — the fidelity cells
# --------------------------------------------------------------------------- #
def _name_set(value) -> set:
    out = set()
    for x in value or []:
        if isinstance(x, str):
            out.add(x)
        elif isinstance(x, dict) and x.get("name") is not None:
            out.add(str(x["name"]))
    return out


def score_summary(agent_summary: dict, gold_summary: dict) -> dict:
    """Return {field: bool} for each of the ten REPORT_FIELDS — whether the agent's
    value matches gold. The three name-array cells score on the NAME SET (the
    load-bearing classification result); ordering and duplicates are reported
    separately by report_conformance, not here."""
    a = agent_summary if isinstance(agent_summary, dict) else {}
    cells: dict[str, bool] = {}
    cells["run_id"] = str(a.get("run_id")) == str(gold_summary["run_id"])
    cells["model"] = str(a.get("model")) == str(gold_summary["model"])
    cells["model_digest"] = str(a.get("model_digest")) == str(gold_summary["model_digest"])
    cells["agents_total"] = _as_int(a.get("agents_total")) == gold_summary["agents_total"]
    cells["agents_passed"] = _as_int(a.get("agents_passed")) == gold_summary["agents_passed"]
    cells["agents_failed"] = _as_int(a.get("agents_failed")) == gold_summary["agents_failed"]
    cells["failed_agents"] = _name_set(a.get("failed_agents")) == _name_set(gold_summary["failed_agents"])
    cells["malformed_agents"] = _name_set(a.get("malformed_agents")) == _name_set(gold_summary["malformed_agents"])
    cells["timed_out_agents"] = _name_set(a.get("timed_out_agents")) == _name_set(gold_summary["timed_out_agents"])
    cells["timestamp"] = str(a.get("timestamp")) == str(gold_summary["timestamp"])
    return cells


def report_conformance(raw_summary: dict, gold_summary: dict) -> dict:
    """DETERMINISTIC structural exactness of the agent's RAW summary vs the canonical
    gold summary, scored BEFORE the tolerant score_summary() normalisation. This is the
    discriminator that separates frameworks when fidelity ties at 100%: a summary that
    only scores full fidelity because score_summary() is lenient (ints-as-strings,
    extra keys, name objects instead of strings, mis-ordered arrays) loses conformance
    points here.

    Returns {"earned": int, "total": int, "issues": [str]}.
    """
    issues: list[str] = []
    earned = 0
    total = 0
    a = raw_summary if isinstance(raw_summary, dict) else {}

    def pt(ok: bool, msg: str):
        nonlocal earned, total
        total += 1
        if ok:
            earned += 1
        else:
            issues.append(msg)

    # Exactly the ten keys, no more, no fewer.
    keys = set(a.keys())
    want = set(REPORT_FIELDS)
    pt(keys == want, f"keys differ: extra={sorted(keys - want)} missing={sorted(want - keys)}")

    # Copy-through string fields exact.
    pt(a.get("run_id") == gold_summary["run_id"], "run_id not exact")
    pt(a.get("model") == gold_summary["model"], "model not exact")
    pt(a.get("model_digest") == gold_summary["model_digest"], "model_digest not exact")
    pt(a.get("timestamp") == gold_summary["timestamp"], "timestamp not exact")

    # Counts are native ints (not stringified) and exact.
    for f in ("agents_total", "agents_passed", "agents_failed"):
        pt(isinstance(a.get(f), int) and a[f] == gold_summary[f], f"{f} not an exact int")

    # Each name array: a list of plain strings, set-exact, and order-exact vs gold.
    for f in ("failed_agents", "malformed_agents", "timed_out_agents"):
        arr = a.get(f)
        well_formed = isinstance(arr, list) and all(isinstance(x, str) for x in arr)
        pt(well_formed and arr == gold_summary[f],
           f"{f} not an exact ordered string list (gold={gold_summary[f]})")

    # The three failure buckets must partition (no name appears in two buckets, and
    # their union size equals agents_failed).
    fa, ma, ta = (_name_set(a.get("failed_agents")), _name_set(a.get("malformed_agents")),
                  _name_set(a.get("timed_out_agents")))
    disjoint = not (fa & ma) and not (fa & ta) and not (ma & ta)
    union_ok = len(fa | ma | ta) == (a.get("agents_failed") if isinstance(a.get("agents_failed"), int) else -1)
    pt(disjoint and union_ok, "failure buckets do not partition agents_failed")

    return {"earned": earned, "total": total, "issues": issues}


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
