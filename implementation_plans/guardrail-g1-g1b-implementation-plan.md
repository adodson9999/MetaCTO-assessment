# G1 / G1b Guardrail Implementation Plan

**Date:** 2026-06-26  
**Revision:** 2 — expanded to cover every agent and every harness file explicitly  
**Target directory:** `agent-foundry/`

---

## Problem Statement

Two independent failure modes, both silent:

**Failure A — test-case-creator produces 0 test cases with no error**  
`agent-foundry/agents/general/test-case-creator/subagent/run.py` line 31 (same line in all 4 framework variants):  
```python
return testcase.extract_json_array(invoke(brief)) or []
```
`extract_json_array()` returns `None` on malformed LLM output. `or []` converts `None` to `[]`. The harness records `emitted_count: 0` and continues. No retry. No error sentinel. 0 test cases written to the registry with no indication of failure.

**Failure B — api-tester agents write staging findings to no location**  
Each of the 40 api-tester agents runs its domain harness and records cases to `results/runs/{RUN_ID}/{agent}.cases.json`, but writes nothing to a staging location. The orchestrator's G1b step has no concrete findings to pass to test-case-creator. test-case-creator is therefore forced to generate test cases from a spec alone, with no evidence of what each agent actually observed.

---

## Full Scope of Changes

### Files to MODIFY (44 files total)

#### Group A — Domain harness files (one per api-tester agent): add staging write

Each harness has a `run_*_test(agent, generate)` driver function. The same pattern change applies to all 40. The specific function name, spec-item variable name, and findings field names differ per harness — those differences are documented in the per-harness table below.

| Harness file | Agent directory | `run_*_test()` function | Item variable |
|---|---|---|---|
| `agents/common/auditlog.py` | `verify-audit-log-generation` | `run_auditlog_test` | `cfg` (collection) |
| `agents/common/auth_harness.py` | `test-authentication-flows` | `run_auth_test` | `scenario` |
| `agents/common/authz_contract.py` | `check-authorization-rules` | `run_authz_test` | `ep` |
| `agents/common/bulk.py` | `test-bulk-operation-endpoints` | `run_bulk_test` | `ep` |
| `agents/common/caching.py` | `verify-caching-headers` | `run_caching_test` | `ep` |
| `agents/common/cid.py` | `validate-correlation-id-propagation` | `run_cid_test` | `ep` |
| `agents/common/clarity_contract.py` | `verify-error-message-clarity` | `run_clarity_test` | `ep` |
| `agents/common/cn.py` | `verify-content-type-negotiation` | `run_cn_test` | `ep` |
| `agents/common/concurrency.py` | `test-concurrent-request-handling` | `run_concurrency_test` | `ep` |
| `agents/common/contract.py` | `validate-request-payloads` | `run_contract_test` | `ep` |
| `agents/common/crud_contract.py` | `verify-crud-operation-integrity` | `run_crud_test` | `ep` |
| `agents/common/defectdensity.py` | `track-defect-density` | `run_defectdensity_test` | `ep` |
| `agents/common/enum_contract.py` | `verify-enum-value-restrictions` | `run_enum_test` | `ep` |
| `agents/common/eventdriven.py` | `test-event-driven-api-triggers` | `run_eventdriven_test` | `ep` |
| `agents/common/gqldepth.py` | `validate-graphql-depth-limits` | `run_gqldepth_test` | `ep` |
| `agents/common/header.py` | `validate-header-propagation` | `run_header_test` | `ep` |
| `agents/common/idempotency.py` | `test-idempotency-of-endpoints` | `run_idempotency_test` | `ep` |
| `agents/common/ip_allowlist.py` | `test-ip-allowlist-enforcement` | `run_ip_allowlist_test` | `ep` |
| `agents/common/longpoll.py` | `test-long-polling-support` | `run_longpoll_test` | `ep` |
| `agents/common/multipart.py` | `test-multipart-form-data-handling` | `run_multipart_test` | `ep` |
| `agents/common/nps.py` | `measure-api-consumer-satisfaction` | `run_nps_test` | `cfg` |
| `agents/common/null_contract.py` | `validate-null-empty-fields` | `run_null_test` | `ep` |
| `agents/common/oauth.py` | `verify-third-party-oauth-integration` | `run_oauth_test` | `ep` |
| `agents/common/pagination.py` | `test-pagination-behavior` | `run_pagination_test` | `ep` |
| `agents/common/postman.py` | `create-postman-collection` | `run_postman_test` | `ep` |
| `agents/common/queryparam.py` | `validate-query-parameter-handling` | `run_queryparam_test` | `ep` |
| `agents/common/ratelimit.py` | `test-rate-limit-enforcement` | `run_ratelimit_test` | `ep` |
| `agents/common/regression.py` | `run-regression-suite` | `run_regression_test` | `ep` |
| `agents/common/retryafter.py` | `validate-retry-after-header-compliance` | `run_retryafter_test` | `ep` |
| `agents/common/routing.py` | `test-api-gateway-routing` | `run_routing_test` | `ep` |
| `agents/common/schema_contract.py` | `validate-json-schema-responses` | `run_schema_test` | `ep` |
| `agents/common/searchfilter.py` | `validate-search-and-filter-queries` | `run_searchfilter_test` | `ep` |
| `agents/common/softdelete.py` | `test-soft-delete-behavior` | `run_softdelete_test` | `ep` |
| `agents/common/sorting.py` | `verify-sorting-behavior` | `run_sorting_test` | `ep` |
| `agents/common/status_contract.py` | `verify-response-status-codes` | `run_status_test` | `ep` |
| `agents/common/timeout.py` | `test-timeout-handling` | `run_timeout_test` | `ep` |
| `agents/common/tls.py` | `test-ssl-tls-enforcement` | `run_tls_test` | `ep` |
| `agents/common/upload.py` | `test-file-upload-and-download` | `run_upload_test` | `ep` |
| `agents/common/versioning.py` | `validate-api-versioning-behavior` | `run_versioning_test` | `ep` |
| `agents/common/webhook.py` | `test-webhook-delivery` | `run_webhook_test` | `ep` |

> **Note on function name and item variable:** Before editing each harness, open it and confirm the actual function name and loop variable name. The table above uses inferred names based on file naming conventions. Confirm before editing — do not guess.

#### Group B — test-case-creator harness: add retry + ERROR sentinel

| File | Change |
|---|---|
| `agents/common/testcase.py` | Modify `agent_brief()` to accept `retry_prefix`; modify `run_testcase_test()` with 3-attempt retry loop and ERROR sentinel write |

#### Group C — test-case-creator framework run.py files: no code change, but verify
All 4 call `testcase.run_testcase_test(AGENT, generate)` and `testcase.agent_brief(cfg)`. The retry flows through `testcase.py` automatically. No code changes required, but each must be verified to call `testcase.agent_brief(cfg)` — not a local copy — so the retry prefix is picked up.

| File | Verify line |
|---|---|
| `agents/general/test-case-creator/subagent/run.py` | line 30: `brief = testcase.agent_brief(cfg)` |
| `agents/general/test-case-creator/claude_sdk/run.py` | line 30: `brief = testcase.agent_brief(cfg)` |
| `agents/general/test-case-creator/crewai/run.py` | line 30: `brief = testcase.agent_brief(cfg)` |
| `agents/general/test-case-creator/langgraph/run.py` | line 30: `brief = testcase.agent_brief(cfg)` |

### Files to CREATE (1 file)

| File | Purpose |
|---|---|
| `agents/common/staging.py` | Shared read utilities for G1b orchestration step to load staged findings and pass them to test-case-creator |

---

## Change Pattern: Group A — Staging Write in Every Harness

### What to read before editing each harness

Open the harness file and locate:
1. The main driver function (`run_*_test(agent, generate)`)
2. The loop that iterates over spec items (endpoints, collections, scenarios)
3. The variable that holds results for a single item within that loop
4. The path where results are written at the end of the loop iteration

### Pattern to add — staging write after each item's result is finalized

Inside the item loop, immediately after the per-item result is finalized (after all HTTP calls for that item are done and before moving to the next item), add:

```python
        # G1 staging write — write per-item findings for G1b orchestration
        _write_staging_findings(agent, item_id, item_label, step_results)
```

Where:
- `item_id` is the unique identifier for this item (slug, collection name, scenario id — whatever the harness uses)  
- `item_label` is a human-readable description (path, name, title)  
- `step_results` is the list of result dicts collected for this item in this iteration

### Staging helper function — add once to EACH harness file

Add this function near the top of each harness file, below the sandbox guard and above the main driver. It is self-contained and has no cross-file dependencies beyond the harness's own `WORKSPACE`, `RUN_ID`, and `_assert_sandbox` (which every harness already defines).

```python
# --------------------------------------------------------------------------- #
# G1 staging write
# --------------------------------------------------------------------------- #
def _write_staging_findings(
    agent: str,
    item_id: str,
    item_label: str,
    step_results: list[dict],
) -> None:
    """Write per-item step findings to the G1 staging directory.

    Path: results/runs/{RUN_ID}/staging/{agent}/{item_id}-findings.json

    Called once per item (endpoint / collection / scenario) after all steps
    for that item are complete. The G1b orchestration step reads these files
    and passes them to test-case-creator as evidence of what this agent observed.

    Args:
        agent:        Full agent name string (e.g. 'api-tester-verify-audit-log-generation').
        item_id:      Unique slug/id for this item within the agent's spec.
        item_label:   Human-readable description (path, collection name, etc.).
        step_results: List of result dicts collected for this item. Each dict
                      must contain at least: 'assertion_result' ('PASS'/'FAIL'),
                      'assertion_detail' (str). All other keys are optional and
                      written verbatim.
    """
    staging_dir = WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{item_id}-findings.json"
    _assert_sandbox(out_path)

    findings = []
    for i, r in enumerate(step_results, start=1):
        findings.append({
            "step_number": i,
            "item_id": item_id,
            "item_label": item_label,
            **r,
        })

    out_path.write_text(json.dumps({
        "agent": agent,
        "item_id": item_id,
        "item_label": item_label,
        "run_id": RUN_ID,
        "findings": findings,
    }, indent=2))
```

### What counts as a step_result dict

Each harness accumulates results differently. The minimum required fields are:

```python
{
    "assertion_result": "PASS",   # or "FAIL" or "ERROR"
    "assertion_detail": "..."     # what was checked and what happened
}
```

Additional fields from the harness (http_status, sent_body, actual_class, etc.) are passed through verbatim via `**r`. Do not strip them.

### Example: contract.py (validate-request-payloads)

The endpoint loop in `run_contract_test()` already accumulates `ep_cases`. After the per-endpoint case collection block and before moving to the next endpoint, add:

```python
        _write_staging_findings(
            agent=agent,
            item_id=ep["slug"],
            item_label=f"{ep['method']} {ep['path']}",
            step_results=[
                {
                    "assertion_result": "PASS" if c.get("actual_class") == c.get("expected_class") else "FAIL",
                    "assertion_detail": (
                        f"category={c['category']} label={c.get('label','')} "
                        f"sent HTTP {c['method']} {c['path']} → "
                        f"status {c['actual_code']} (class={c['actual_class']}, expected={c['expected_class']})"
                    ),
                    **c,
                }
                for c in ep_cases
            ],
        )
```

### Example: auditlog.py (verify-audit-log-generation)

After each collection's scenarios are evaluated and results recorded, before moving to the next collection, add:

```python
        _write_staging_findings(
            agent=agent,
            item_id=cfg["name"],
            item_label=cfg.get("description", cfg["name"]),
            step_results=[
                {
                    "assertion_result": "PASS" if r.get("passed") else "FAIL",
                    "assertion_detail": r.get("detail", ""),
                    **r,
                }
                for r in collection_results
            ],
        )
```

> **For each harness you edit:** read the driver function, find the per-item result accumulation variable (the list that gets appended to inside the loop), and call `_write_staging_findings()` with that variable after the loop body finishes for each item.

---

## Change Pattern: Group B — Retry + ERROR Sentinel in testcase.py

### Change B1: Modify `agent_brief()` — accept retry_prefix

**File:** `agent-foundry/agents/common/testcase.py`  
**Function:** `agent_brief()` (lines 117–124)

**Current:**
```python
def agent_brief(cfg: dict) -> str:
    """Compact, unambiguous per-agent brief handed to the LLM."""
    return "\n".join([
        f"agent_name: {cfg['name']}",
        "how_text: |",
        *[f"  {line}" for line in cfg["how_text"].splitlines()],
        f"metric_line: {cfg['metric_line']}",
    ])
```

**Replace with:**
```python
def agent_brief(cfg: dict) -> str:
    """Compact, unambiguous per-agent brief handed to the LLM.

    If cfg contains 'retry_prefix' (str), it is prepended to the brief.
    retry_prefix is injected by run_testcase_test() on retry attempts 2 and 3
    to enforce JSON array output format. It is never present on attempt 1.
    """
    parts = [
        f"agent_name: {cfg['name']}",
        "how_text: |",
        *[f"  {line}" for line in cfg["how_text"].splitlines()],
        f"metric_line: {cfg['metric_line']}",
    ]
    brief = "\n".join(parts)
    prefix = cfg.get("retry_prefix", "")
    return f"{prefix}\n\n{brief}" if prefix else brief
```

### Change B2: Replace per-agent loop in `run_testcase_test()` — add retry + sentinel

**File:** `agent-foundry/agents/common/testcase.py`  
**Function:** `run_testcase_test()` (lines 201–258)  
**Target block:** the `for cfg in cfgs:` loop (lines 216–226)

**Current loop block:**
```python
    for cfg in cfgs:
        try:
            cases = generate(cfg) or []
            if not isinstance(cases, list):
                cases = []
            gen_error = None
        except Exception as e:  # noqa
            cases, gen_error = [], f"{type(e).__name__}: {e}"
        emitted_registry.extend([c for c in cases if isinstance(c, dict)])
        per_agent.append({"agent_spec": cfg["name"], "emitted_count": len(cases),
                          "error": gen_error})
```

**Replace with:**
```python
    _RETRY_PREFIXES = [
        "",   # attempt 1: no prefix
        (
            "CRITICAL: Your previous response was not a valid JSON array. "
            "Output ONLY a JSON array. Start with [ and end with ]. "
            "No other text, no markdown fences, no explanation."
        ),
        (
            "MANDATORY FORMAT — your response must be exactly this structure:\n"
            '[{"tc_id":"TC-1","agent":"<agent_name>","description":"...","steps":[...]}]\n'
            "Output ONLY the JSON array. Nothing else."
        ),
    ]
    MAX_ATTEMPTS = 3

    for cfg in cfgs:
        cases: list = []
        gen_error: str | None = None

        for attempt in range(MAX_ATTEMPTS):
            attempt_cfg = dict(cfg)
            if attempt > 0:
                attempt_cfg["retry_prefix"] = _RETRY_PREFIXES[attempt]

            try:
                result = generate(attempt_cfg) or []
                if not isinstance(result, list):
                    result = []
            except Exception as e:  # noqa
                gen_error = f"{type(e).__name__}: {e}"
                break  # exception is unrecoverable for this cfg; do not retry

            if result:
                cases = result
                gen_error = None
                break

            gen_error = f"empty output on attempt {attempt + 1} of {MAX_ATTEMPTS}"

        if not cases:
            sentinel = {
                "tc_id": f"TC-ERR-{cfg['name']}",
                "agent": cfg["name"],
                "run_id": RUN_ID,
                "outcome": "ERROR",
                "error": (
                    gen_error or
                    f"test-case-creator returned empty/unparseable output "
                    f"after {MAX_ATTEMPTS} attempts"
                ),
                "pass": False,
                "fail": False,
            }
            emitted_registry.append(sentinel)

        emitted_registry.extend([c for c in cases if isinstance(c, dict)])
        per_agent.append({
            "agent_spec": cfg["name"],
            "emitted_count": len(cases),
            "attempts": attempt + 1,
            "error": gen_error,
        })
```

---

## New File: `agents/common/staging.py`

Create this file. It is the read side of the staging protocol — used by the G1b orchestration block to load findings and build the brief passed to test-case-creator.

```python
"""G1/G1b staging file utilities — read side.

Write side: _write_staging_findings() added to each domain harness.
Read side: this module, called by the G1b orchestration step.

Staging files are written by api-tester agents at:
  results/runs/{RUN_ID}/staging/{agent_name}/{item_id}-findings.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")


def staging_dir(agent_name: str) -> Path:
    return WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent_name


def list_staging_files(agent_name: str) -> list[Path]:
    d = staging_dir(agent_name)
    if not d.exists():
        return []
    return sorted(d.glob("*-findings.json"))


def load_staging_findings(agent_name: str) -> list[dict]:
    """Load and merge all staged findings for a given agent into a flat list."""
    all_findings: list[dict] = []
    for path in list_staging_files(agent_name):
        try:
            data = json.loads(path.read_text())
            findings = data.get("findings", [])
            if isinstance(findings, list):
                all_findings.extend(findings)
        except Exception:  # noqa
            pass
    return all_findings


def staging_brief(agent_name: str) -> str:
    """Build a compact text block summarising staged findings for one agent.

    Prepended to the test-case-creator LLM brief by the G1b step.
    Returns empty string if no staged findings exist.
    """
    findings = load_staging_findings(agent_name)
    if not findings:
        return ""

    lines = [
        f"# Staged findings from {agent_name} ({len(findings)} steps observed)",
        "# Base your test cases on these actual observations, not on the spec alone.",
        "",
    ]
    for f in findings:
        result = f.get("assertion_result", "?")
        lines.append(
            f"  step {f.get('step_number','?')}: "
            f"item={f.get('item_id','?')} "
            f"[{result}] — {f.get('assertion_detail','')}"
        )
    return "\n".join(lines)


def staging_summary(run_id: str | None = None) -> dict:
    """Return {agent_name: {file_count, total_findings}} for all agents in a run."""
    rid = run_id or RUN_ID
    base = WORKSPACE / "results" / "runs" / rid / "staging"
    if not base.exists():
        return {}
    summary: dict[str, dict] = {}
    for agent_dir in sorted(base.iterdir()):
        if not agent_dir.is_dir():
            continue
        files = list(agent_dir.glob("*-findings.json"))
        total = 0
        for f in files:
            try:
                total += len(json.loads(f.read_text()).get("findings", []))
            except Exception:  # noqa
                pass
        summary[agent_dir.name] = {"file_count": len(files), "total_findings": total}
    return summary
```

---

## Implementation Order

Execute changes in this exact order. Do not skip ahead.

```
Step 1.  READ each harness file before editing it.
         Confirm: function name, loop variable, per-item result list variable.
         Do not assume — verify.

Step 2.  ADD _write_staging_findings() to agents/common/contract.py
         CALL it inside run_contract_test() after each endpoint's ep_cases are complete.
         CONFIRM: staging file appears at results/runs/manual/staging/api-tester-validate-request-payloads/

Step 3.  ADD _write_staging_findings() to the remaining 39 harness files.
         Order: alphabetical by filename.
         After each file: run that agent's subagent/run.py and confirm staging file written.

Step 4.  CREATE agents/common/staging.py

Step 5.  MODIFY agents/common/testcase.py — Change B1 (agent_brief)
Step 6.  MODIFY agents/common/testcase.py — Change B2 (retry loop)

Step 7.  VERIFY all 4 test-case-creator framework run.py files call testcase.agent_brief(cfg)
         on line 30. No code change needed if they do.
```

---

## Verification Checklist

### V1 — Staging file written by every api-tester agent

Run a single agent, e.g. validate-request-payloads:
```
FORGE_WORKSPACE=$(pwd)/agent-foundry python3 agent-foundry/agents/api-tester/validate-request-payloads/subagent/run.py
```
Confirm:
- `agent-foundry/results/runs/manual/staging/api-tester-validate-request-payloads/` exists
- One `{slug}-findings.json` file per endpoint in `data/openapi.json`
- Each file contains `findings` array with at least one entry
- Each entry has `assertion_result` of `PASS` or `FAIL`

Repeat this check for at minimum: `verify-audit-log-generation`, `test-authentication-flows`, `test-bulk-operation-endpoints`, `verify-caching-headers` — one from each harness family.

### V2 — Retry fires on empty LLM output (test-case-creator)

Temporarily monkeypatch `generate` to return `[]` on attempts 1 and 2:
```python
_counter = {}
orig = generate
def generate(cfg):
    n = _counter.get(cfg["name"], 0)
    _counter[cfg["name"]] = n + 1
    if n < 2:
        return []
    return orig(cfg)
```
Run test-case-creator subagent. Confirm in printed summary:
- `per_agent_spec[*].attempts` == 3
- `emitted_count` > 0

Remove monkeypatch.

### V3 — ERROR sentinel written on total failure

Monkeypatch `generate` to always return `[]`:
```python
generate = lambda cfg: []
```
Run test-case-creator subagent. Inspect `.emitted-registry.json`. Confirm:
- Entries with `"outcome": "ERROR"` and `tc_id` starting with `TC-ERR-`
- `emitted_count` == 0 in `per_agent_spec`
- No silent zero-case run without any error record

Remove monkeypatch.

### V4 — staging.py reads findings correctly

```python
import sys; sys.path.insert(0, "agent-foundry/agents/common")
import staging
print(staging.staging_summary())
brief = staging.staging_brief("api-tester-validate-request-payloads")
assert brief != ""
assert "step 1:" in brief
```

### V5 — End-to-end: api-tester → G1b → test-case-creator

Run the full orchestration sequence for one agent:
1. Run api-tester agent → staging files written (V1 confirmed)
2. G1b step loads staging brief via `staging.staging_brief(agent_name)`
3. test-case-creator invoked with staging brief prepended
4. Confirm `results/runs/{RUN_ID}/{tc_agent}.emitted-registry.json` has count > 0
5. Confirm no `TC-ERR-*` entries in emitted registry

---

## Complete File Change Summary

```
CREATE  agent-foundry/agents/common/staging.py

MODIFY  agent-foundry/agents/common/testcase.py
        — agent_brief(): add retry_prefix support
        — run_testcase_test(): add 3-attempt retry + ERROR sentinel

MODIFY (40 harness files — add _write_staging_findings function + call site):
        agent-foundry/agents/common/auditlog.py
        agent-foundry/agents/common/auth_harness.py
        agent-foundry/agents/common/authz_contract.py
        agent-foundry/agents/common/bulk.py
        agent-foundry/agents/common/caching.py
        agent-foundry/agents/common/cid.py
        agent-foundry/agents/common/clarity_contract.py
        agent-foundry/agents/common/cn.py
        agent-foundry/agents/common/concurrency.py
        agent-foundry/agents/common/contract.py
        agent-foundry/agents/common/crud_contract.py
        agent-foundry/agents/common/defectdensity.py
        agent-foundry/agents/common/enum_contract.py
        agent-foundry/agents/common/eventdriven.py
        agent-foundry/agents/common/gqldepth.py
        agent-foundry/agents/common/header.py
        agent-foundry/agents/common/idempotency.py
        agent-foundry/agents/common/ip_allowlist.py
        agent-foundry/agents/common/longpoll.py
        agent-foundry/agents/common/multipart.py
        agent-foundry/agents/common/nps.py
        agent-foundry/agents/common/null_contract.py
        agent-foundry/agents/common/oauth.py
        agent-foundry/agents/common/pagination.py
        agent-foundry/agents/common/postman.py
        agent-foundry/agents/common/queryparam.py
        agent-foundry/agents/common/ratelimit.py
        agent-foundry/agents/common/regression.py
        agent-foundry/agents/common/retryafter.py
        agent-foundry/agents/common/routing.py
        agent-foundry/agents/common/schema_contract.py
        agent-foundry/agents/common/searchfilter.py
        agent-foundry/agents/common/softdelete.py
        agent-foundry/agents/common/sorting.py
        agent-foundry/agents/common/status_contract.py
        agent-foundry/agents/common/timeout.py
        agent-foundry/agents/common/tls.py
        agent-foundry/agents/common/upload.py
        agent-foundry/agents/common/versioning.py
        agent-foundry/agents/common/webhook.py

VERIFY ONLY (no code changes — confirm testcase.agent_brief(cfg) call on line 30):
        agent-foundry/agents/general/test-case-creator/subagent/run.py
        agent-foundry/agents/general/test-case-creator/claude_sdk/run.py
        agent-foundry/agents/general/test-case-creator/crewai/run.py
        agent-foundry/agents/general/test-case-creator/langgraph/run.py

NO CHANGE (api-tester agent run.py files — harness changes cover them):
        agent-foundry/agents/api-tester/*/subagent/run.py  (all 40)
```

---

## Revision 3 — GitHub Actions CI Integration

**Added:** 2026-06-26  
**Supersedes:** any separate `ci-per-agent-parallel-jobs-plan.md` document for the api-tester kind.

This revision wires the G1/G1b guardrails into a chunked parallel GitHub Actions workflow organized by position (kind). Agents of the same kind are grouped into chunks of 20 and each chunk runs as one GHA job. This design scales to 2000+ agents without hitting GitHub's 256-job matrix limit (2000 agents ÷ 20 per chunk = 100 GHA jobs).

**Kind layout:**
- `api-tester` — chunked, 20 agents per GHA job, always runs on push/PR.
- `general` — skipped on every automatic trigger. Only runs when explicitly enabled via `workflow_dispatch` input. Add `run_general: true` when dispatching manually if you need to validate test-case-creator, run-cicd-pipeline, or bug-reporter.

**Within each api-tester chunk job, three phases run per agent in sequence:**

1. **G1 phase** — runs the api-tester agent's `run.py`, which (after the harness edits in Group A) writes staging findings to `results/runs/{RUN_ID}/staging/api-tester-{agent}/`.
2. **G1b phase** — runs test-case-creator scoped to that one agent via `FORGE_TESTCASE_AGENT`. Change D3 auto-loads the staged findings and prepends them to the LLM brief. The B2 retry loop fires on malformed output. An ERROR sentinel is written on total failure after 3 attempts.
3. **Gate phase** — `scripts/ci_report_cases.py` checks that agent's output, exits 1 on ERROR sentinel or zero cases. Failures are collected and the chunk job exits 1 if any agent in the chunk failed.

**Adding more agents later:** add the directory under `agents/api-tester/`. The setup job auto-discovers all directories and recomputes chunks. No workflow YAML change needed.

---

### New Change D — `testcase.py`: CI scoping + staging brief auto-load

Three additive changes to `agents/common/testcase.py`. They do not conflict with Changes B1 and B2.

#### Change D1 — `agent_cfgs()`: add `FORGE_TESTCASE_AGENT` filter

**Where:** at the end of `agent_cfgs()`, replacing the existing bare `return cfgs`.

**Replace:**
```python
    return cfgs
```

**With:**
```python
    # D1: CI scoping — when FORGE_TESTCASE_AGENT is set, return only that agent's config.
    # The env var value must match cfg["name"] exactly
    # (e.g. "api-tester-validate-request-payloads").
    target = os.environ.get("FORGE_TESTCASE_AGENT", "").strip()
    if target:
        cfgs = [c for c in cfgs if c["name"] == target]
    return cfgs
```

#### Change D2 — `agent_brief()`: add `staging_prefix` support

**Where:** in `agent_brief()`, after Change B1 is applied. Replace the return logic.

**Current (after B1):**
```python
    prefix = cfg.get("retry_prefix", "")
    return f"{prefix}\n\n{brief}" if prefix else brief
```

**Replace with:**
```python
    # staging_prefix carries actual observations from the G1 harness run (set by D3).
    # retry_prefix is injected on attempt 2 and 3 to enforce JSON format (set by B2).
    # Order in the prompt: staging context first, then format correction, then the brief.
    staging_prefix = cfg.get("staging_prefix", "")
    retry_prefix   = cfg.get("retry_prefix", "")
    combined = "\n\n".join(p for p in [staging_prefix, retry_prefix] if p)
    return f"{combined}\n\n{brief}" if combined else brief
```

#### Change D3 — `run_testcase_test()`: auto-load staging brief before the retry loop

**Insertion 1** — at the top of `run_testcase_test()`, before `cfgs = agent_cfgs()`:

```python
    # D3a: Import staging module if available. Failures are silently suppressed —
    # the staging brief is optional evidence; test-case-creator works without it.
    _staging_mod = None
    try:
        import sys as _sys
        _sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
        import staging as _staging_mod  # type: ignore[import]
    except Exception:  # noqa: BLE001
        pass
```

**Insertion 2** — inside the `for cfg in cfgs:` loop, immediately before `for attempt in range(MAX_ATTEMPTS):`:

```python
        # D3b: Load staged findings for this agent and inject as staging_prefix.
        # staging_brief() returns "" if no staging files exist for this agent.
        if _staging_mod is not None:
            try:
                _stage_text = _staging_mod.staging_brief(cfg["name"])
                if _stage_text:
                    cfg = dict(cfg, staging_prefix=_stage_text)
            except Exception:  # noqa: BLE001
                pass
```

---

### New File: `scripts/ci_report_cases.py`

Create this file at `agent-foundry/scripts/ci_report_cases.py`.

```python
#!/usr/bin/env python3
"""CI gate: report test-case-creator output for one agent and fail on ERROR sentinel.

Exit code 0: at least one valid test case was generated for the target agent.
Exit code 1: zero valid test cases, or an ERROR sentinel is present.

Env vars:
  FORGE_WORKSPACE       path to agent-foundry root (required)
  FORGE_TESTCASE_AGENT  when set, filters the registry to entries for this agent only.
                        Must match the "agent" field or "tc_id" prefix in the registry.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
TARGET    = os.environ.get("FORGE_TESTCASE_AGENT", "").strip()

registry_path = (
    WORKSPACE / "results" / "general" / "test-case-creator" / "test-case-registry.json"
)

if not registry_path.exists():
    print(
        f"[CI ERROR] test-case-registry.json not found at {registry_path}\n"
        "Check that FORGE_WORKSPACE is correct and the G1b step ran.",
        file=sys.stderr,
    )
    sys.exit(1)

data    = json.loads(registry_path.read_text())
entries: list[dict] = data if isinstance(data, list) else data.get("test_cases", [])

if TARGET:
    relevant = [
        e for e in entries
        if e.get("agent") == TARGET
        or str(e.get("tc_id", "")).startswith(f"TC-ERR-{TARGET}")
    ]
else:
    relevant = entries

errors = [
    e for e in relevant
    if e.get("outcome") == "ERROR"
    or str(e.get("tc_id", "")).startswith("TC-ERR-")
]
cases  = [e for e in relevant if e not in errors]
label  = TARGET or "all agents"

print(f"[CI] {label}: {len(cases)} test case(s) generated, {len(errors)} ERROR sentinel(s)")

if errors:
    for e in errors:
        print(
            f"  SENTINEL: {e.get('tc_id')} — {e.get('error', 'no detail')}",
            file=sys.stderr,
        )
    sys.exit(1)

if not cases:
    print(
        f"[CI ERROR] 0 test cases and 0 ERROR sentinels for {label}.\n"
        "Registry exists but contains no relevant entries.\n"
        "Check FORGE_TESTCASE_AGENT matches the manifest name exactly.",
        file=sys.stderr,
    )
    sys.exit(1)

sys.exit(0)
```

---

### New File: `scripts/ci_gen_chunks.py`

Create this file at `agent-foundry/scripts/ci_gen_chunks.py`. The setup job in GHA calls it to compute the chunk-index array for the matrix dynamically. New agents added to the directory are auto-discovered with no workflow YAML change.

```python
#!/usr/bin/env python3
"""Generate the chunk-index JSON array for a GitHub Actions dynamic matrix.

Usage:
  python ci_gen_chunks.py <kind> [chunk_size]

Prints a JSON array of integers [0, 1, 2, ..., n_chunks-1] to stdout.
GHA reads this via: echo "chunks=$(python ci_gen_chunks.py api-tester 20)" >> $GITHUB_OUTPUT

Args:
  kind        Agent kind directory name under agents/ (e.g. "api-tester").
  chunk_size  Number of agents per chunk (default: 20).

Env vars:
  FORGE_WORKSPACE  path to agent-foundry root (default: current directory).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WORKSPACE  = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
KIND       = sys.argv[1] if len(sys.argv) > 1 else "api-tester"
CHUNK_SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 20

agents_dir = WORKSPACE / "agents" / KIND
if not agents_dir.is_dir():
    print(f"[ci_gen_chunks] ERROR: directory not found: {agents_dir}", file=sys.stderr)
    sys.exit(1)

agents   = sorted(p.name for p in agents_dir.iterdir() if p.is_dir())
n_chunks = max(1, (len(agents) + CHUNK_SIZE - 1) // CHUNK_SIZE)

print(json.dumps(list(range(n_chunks))))
```

---

### New File: `scripts/ci_run_chunk.py`

Create this file at `agent-foundry/scripts/ci_run_chunk.py`. Each GHA chunk job calls this script once. It runs G1 → G1b → gate for every agent in the chunk sequentially, collects failures, and exits 1 if any agent failed.

```python
#!/usr/bin/env python3
"""Run one chunk of agents sequentially: G1 (harness) → G1b (test-case-creator) → gate.

Each agent in the chunk runs to completion before the next starts.
All failures are collected and reported at the end; the job exits 1 if any failed.

Env vars (all required in CI):
  FORGE_WORKSPACE    path to agent-foundry root
  FORGE_RUN_ID       run identifier (e.g. github.run_id)
  FORGE_KIND         agent kind directory (default: "api-tester")
  FORGE_CHUNK_INDEX  zero-based index of this chunk (default: 0)
  FORGE_CHUNK_SIZE   number of agents per chunk (default: 20)
  FORGE_PROVIDER     backend provider (e.g. "claude-haiku")
  ANTHROPIC_API_KEY  Anthropic API key (required when FORGE_PROVIDER=claude-haiku)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORKSPACE   = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
RUN_ID      = os.environ.get("FORGE_RUN_ID", "manual")
KIND        = os.environ.get("FORGE_KIND", "api-tester")
CHUNK_INDEX = int(os.environ.get("FORGE_CHUNK_INDEX", "0"))
CHUNK_SIZE  = int(os.environ.get("FORGE_CHUNK_SIZE", "20"))

# Discover agents from the filesystem — same sort order as ci_gen_chunks.py.
agents_dir = WORKSPACE / "agents" / KIND
all_agents = sorted(p.name for p in agents_dir.iterdir() if p.is_dir())
start      = CHUNK_INDEX * CHUNK_SIZE
chunk      = all_agents[start : start + CHUNK_SIZE]

if not chunk:
    print(f"[ci_run_chunk] chunk {CHUNK_INDEX} is empty — nothing to do", file=sys.stderr)
    sys.exit(0)

print(
    f"[ci_run_chunk] chunk {CHUNK_INDEX}: {len(chunk)} agent(s) "
    f"(agents {start}–{start + len(chunk) - 1} of {len(all_agents)})"
)

base_env = {**os.environ, "FORGE_WORKSPACE": str(WORKSPACE), "FORGE_RUN_ID": RUN_ID}
failures: list[str] = []


def run(cmd: list[str], env: dict) -> int:
    """Run a subprocess and return its exit code."""
    result = subprocess.run(cmd, env=env)
    return result.returncode


for agent in chunk:
    full_name = f"{KIND}-{agent}"
    print(f"\n── {full_name} ──────────────────────────────────────")

    # ------------------------------------------------------------------
    # G1: run the api-tester agent harness.
    # Writes staging findings to results/runs/{RUN_ID}/staging/{full_name}/
    # ------------------------------------------------------------------
    g1_rc = run(
        [sys.executable, str(WORKSPACE / "agents" / KIND / agent / "subagent" / "run.py")],
        env=base_env,
    )
    if g1_rc != 0:
        failures.append(f"{full_name}: G1 agent run failed (exit {g1_rc})")
        continue   # skip G1b and gate — no staging files were written

    # ------------------------------------------------------------------
    # G1b: run test-case-creator scoped to this agent.
    # FORGE_TESTCASE_AGENT (Change D1) limits agent_cfgs() to one entry.
    # Change D3 auto-loads staged findings as staging_prefix.
    # Change B2 retries up to 3 times; writes ERROR sentinel on total failure.
    # We do not abort on non-zero exit — the gate step captures the outcome.
    # ------------------------------------------------------------------
    tc_env = {**base_env, "FORGE_TESTCASE_AGENT": full_name}
    run(
        [sys.executable,
         str(WORKSPACE / "agents/general/test-case-creator/subagent/run.py")],
        env=tc_env,
    )

    # ------------------------------------------------------------------
    # Gate: ci_report_cases.py reads test-case-registry.json filtered to
    # this agent. Exits 1 if an ERROR sentinel is present or cases == 0.
    # ------------------------------------------------------------------
    gate_rc = run(
        [sys.executable, str(WORKSPACE / "scripts" / "ci_report_cases.py")],
        env=tc_env,
    )
    if gate_rc != 0:
        failures.append(f"{full_name}: test-case gate failed")


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
passed = len(chunk) - len(failures)
print(f"\n[ci_run_chunk] chunk {CHUNK_INDEX} complete: {passed}/{len(chunk)} passed")

if failures:
    print(f"[ci_run_chunk] FAILURES in chunk {CHUNK_INDEX}:", file=sys.stderr)
    for f in failures:
        print(f"  {f}", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
```

---

### New File: `.github/workflows/agent-ci.yml`

Create this file at the repository root. The `setup-api-tester` job auto-discovers agent directories and computes the chunk matrix at runtime — no YAML changes needed when agents are added.

```yaml
name: "Agent CI — chunked parallel jobs by position (G1/G1b guardrails)"

on:
  push:
    branches: ["main", "develop"]
    paths:
      - "agent-foundry/**"
      - ".github/workflows/agent-ci.yml"
  pull_request:
    branches: ["main", "develop"]
    paths:
      - "agent-foundry/**"
      - ".github/workflows/agent-ci.yml"
  workflow_dispatch:
    inputs:
      run_general:
        description: "Run general agents (test-case-creator, run-cicd-pipeline, bug-reporter)"
        required: false
        default: "false"
        type: choice
        options: ["false", "true"]

env:
  PYTHON_VERSION: "3.11"
  NODE_VERSION:   "20"
  CHUNK_SIZE:     "20"

jobs:
  # -----------------------------------------------------------------------
  # POSITION: api-tester
  # Setup job: discover all api-tester agent directories and compute chunk
  # indices. Output is a JSON array consumed by the matrix below.
  # -----------------------------------------------------------------------
  setup-api-tester:
    name: "api-tester / setup (compute chunks)"
    runs-on: ubuntu-latest
    outputs:
      chunks: ${{ steps.gen.outputs.chunks }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - id: gen
        env:
          FORGE_WORKSPACE: ${{ github.workspace }}/agent-foundry
        run: |
          CHUNKS=$(python agent-foundry/scripts/ci_gen_chunks.py api-tester ${{ env.CHUNK_SIZE }})
          echo "chunks=$CHUNKS" >> $GITHUB_OUTPUT
          echo "Chunk array: $CHUNKS"

  # -----------------------------------------------------------------------
  # POSITION: api-tester
  # One GHA job per chunk. Each job runs 20 agents sequentially via
  # ci_run_chunk.py: G1 (harness) → G1b (scoped test-case-creator) → gate.
  # fail-fast: false — all chunks always complete regardless of failures.
  # timeout-minutes: 90 — 20 agents × ~4 min each + startup overhead.
  # -----------------------------------------------------------------------
  api-tester:
    name: "api-tester / chunk-${{ matrix.chunk_index }}"
    needs: setup-api-tester
    runs-on: ubuntu-latest
    timeout-minutes: 90
    strategy:
      fail-fast: false
      matrix:
        chunk_index: ${{ fromJson(needs.setup-api-tester.outputs.chunks) }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python ${{ env.PYTHON_VERSION }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Set up Node ${{ env.NODE_VERSION }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}

      - name: Install Python dependencies
        run: pip install litellm --break-system-packages

      - name: Install DummyJSON server dependencies
        run: npm ci --prefix agent-foundry/dummyjson

      - name: Start DummyJSON API server (port 8888)
        run: node agent-foundry/dummyjson/server.js &

      - name: Start LiteLLM proxy (port 4000)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: litellm --model anthropic/claude-haiku-4-5 --port 4000 &

      - name: Wait for services (ports 8888 and 4000)
        run: |
          for PORT in 8888 4000; do
            for I in $(seq 1 20); do
              nc -z 127.0.0.1 $PORT 2>/dev/null && echo "port $PORT ready" && break
              sleep 2
            done
          done

      # ------------------------------------------------------------------
      # Run the chunk: G1 → G1b → gate for each of the 20 agents.
      # ci_run_chunk.py discovers the agent list from the filesystem,
      # slices chunk_index*20 : chunk_index*20+20, and runs each agent.
      # ------------------------------------------------------------------
      - name: "Run chunk ${{ matrix.chunk_index }} (api-tester, ${{ env.CHUNK_SIZE }} agents)"
        env:
          FORGE_WORKSPACE:   ${{ github.workspace }}/agent-foundry
          FORGE_RUN_ID:      ${{ github.run_id }}
          FORGE_KIND:        api-tester
          FORGE_CHUNK_INDEX: ${{ matrix.chunk_index }}
          FORGE_CHUNK_SIZE:  ${{ env.CHUNK_SIZE }}
          FORGE_PROVIDER:    claude-haiku
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python agent-foundry/scripts/ci_run_chunk.py

      - name: "Upload results for chunk ${{ matrix.chunk_index }}"
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: "results-api-tester-chunk-${{ matrix.chunk_index }}"
          path: |
            agent-foundry/results/runs/${{ github.run_id }}/staging/
            agent-foundry/results/general/test-case-creator/
          retention-days: 7

  # -----------------------------------------------------------------------
  # POSITION: general
  # Skipped on every automatic trigger (push / pull_request).
  # Only runs when workflow_dispatch is used with run_general=true.
  # General agents do not have domain harnesses and do not write staging
  # files, so the G1/G1b guardrail flow does not apply to them.
  # -----------------------------------------------------------------------
  general:
    name: "general (skipped unless manually triggered)"
    runs-on: ubuntu-latest
    timeout-minutes: 30
    if: ${{ github.event_name == 'workflow_dispatch' && inputs.run_general == 'true' }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - run: pip install litellm --break-system-packages
      - run: npm ci --prefix agent-foundry/dummyjson
      - run: node agent-foundry/dummyjson/server.js &
      - name: Start LiteLLM proxy
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: litellm --model anthropic/claude-haiku-4-5 --port 4000 &
      - name: Wait for services
        run: |
          for PORT in 8888 4000; do
            for I in $(seq 1 20); do
              nc -z 127.0.0.1 $PORT 2>/dev/null && break; sleep 2; done; done
      - name: Run general agents
        env:
          FORGE_WORKSPACE:   ${{ github.workspace }}/agent-foundry
          FORGE_RUN_ID:      ${{ github.run_id }}
          FORGE_PROVIDER:    claude-haiku
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          for AGENT in test-case-creator run-cicd-pipeline bug-reporter; do
            echo "── general/$AGENT"
            python agent-foundry/agents/general/$AGENT/subagent/run.py || true
          done
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: results-general
          path: agent-foundry/results/
          retention-days: 7
```

---

### Updated Implementation Order (Revision 3 additions)

Insert these steps after Step 7:

```
Step 8.  MODIFY agents/common/testcase.py — Change D1
         Replace bare `return cfgs` in agent_cfgs() with the FORGE_TESTCASE_AGENT filter block.

Step 9.  MODIFY agents/common/testcase.py — Change D2
         In agent_brief(), replace the single-prefix return logic with the two-prefix
         (staging_prefix + retry_prefix) combined return logic.

Step 10. MODIFY agents/common/testcase.py — Change D3
         Add D3a import block at the top of run_testcase_test().
         Add D3b staging-brief injection inside the for-cfg loop, before the retry loop.

Step 11. CREATE agent-foundry/scripts/ci_report_cases.py

Step 12. CREATE agent-foundry/scripts/ci_gen_chunks.py

Step 13. CREATE agent-foundry/scripts/ci_run_chunk.py

Step 14. CREATE .github/workflows/agent-ci.yml
         After creating it, run the setup job locally to confirm chunk output:
           FORGE_WORKSPACE=agent-foundry python agent-foundry/scripts/ci_gen_chunks.py api-tester 20
         Confirm output is a JSON array of integers with length ceil(n_agents / 20).
```

---

### Updated File Change Summary (Revision 3 additions)

```
CREATE  .github/workflows/agent-ci.yml
        — setup-api-tester job: discovers directories, computes chunk indices dynamically
        — api-tester job (matrix of chunk indices): 20 agents per chunk, fail-fast disabled
          each chunk job calls ci_run_chunk.py: G1 → G1b → gate per agent
        — general job: skipped on push/PR; opt-in only via workflow_dispatch run_general=true

CREATE  agent-foundry/scripts/ci_gen_chunks.py
        — reads agents/{kind}/ directory, computes [0..n_chunks-1], prints JSON array
        — called by setup-api-tester job to populate the matrix

CREATE  agent-foundry/scripts/ci_run_chunk.py
        — reads FORGE_KIND, FORGE_CHUNK_INDEX, FORGE_CHUNK_SIZE from env
        — discovers agent list from filesystem (same sort as ci_gen_chunks.py)
        — for each agent in chunk: G1 run.py → G1b test-case-creator → ci_report_cases.py
        — collects all failures, exits 1 if any agent in the chunk failed

CREATE  agent-foundry/scripts/ci_report_cases.py
        — reads test-case-registry.json filtered by FORGE_TESTCASE_AGENT
        — exits 1 on ERROR sentinel or zero cases; exits 0 on success

MODIFY  agent-foundry/agents/common/testcase.py  (three additions, Revision 3)
        — D1: agent_cfgs(): FORGE_TESTCASE_AGENT filter (replaces bare return)
        — D2: agent_brief(): staging_prefix + retry_prefix combined (replaces single-prefix return)
        — D3: run_testcase_test(): D3a import block + D3b per-cfg staging brief injection
```

---

### Verification Checklist (Revision 3 additions)

#### V6 — FORGE_TESTCASE_AGENT scoping returns exactly one config

```python
import os, sys
os.environ["FORGE_WORKSPACE"] = "agent-foundry"
os.environ["FORGE_TESTCASE_AGENT"] = "api-tester-validate-request-payloads"
sys.path.insert(0, "agent-foundry/agents/common")
import testcase
cfgs = testcase.agent_cfgs()
assert len(cfgs) == 1, f"expected 1, got {len(cfgs)}"
assert cfgs[0]["name"] == "api-tester-validate-request-payloads"
print("V6 PASS")
```

#### V7 — Staging brief is prepended to the LLM brief (requires V1 staging files to exist)

```python
import os, sys
os.environ["FORGE_WORKSPACE"] = "agent-foundry"
os.environ["FORGE_RUN_ID"] = "manual"
sys.path.insert(0, "agent-foundry/agents/common")
import staging, testcase

cfgs = testcase.agent_cfgs()
cfg = next(c for c in cfgs if c["name"] == "api-tester-validate-request-payloads")
stage_text = staging.staging_brief("api-tester-validate-request-payloads")
assert stage_text != "", "no staging brief — run the agent first (V1)"
cfg_with_staging = dict(cfg, staging_prefix=stage_text)
brief = testcase.agent_brief(cfg_with_staging)
first_line_of_staging = stage_text.splitlines()[0]
assert first_line_of_staging in brief, "staging prefix missing from brief"
assert "agent_name:" in brief, "core brief missing from output"
print("V7 PASS")
```

#### V8 — ci_report_cases.py exits 1 on ERROR sentinel, 0 on valid cases

```bash
mkdir -p agent-foundry/results/general/test-case-creator

# V8a: exits 0 when valid cases present
echo '[{"tc_id":"TC-1","agent":"api-tester-validate-request-payloads","outcome":"PASS"}]' \
  > agent-foundry/results/general/test-case-creator/test-case-registry.json
FORGE_WORKSPACE=agent-foundry \
FORGE_TESTCASE_AGENT=api-tester-validate-request-payloads \
python agent-foundry/scripts/ci_report_cases.py
echo "exit $?"   # must be 0

# V8b: exits 1 when ERROR sentinel present
echo '[{"tc_id":"TC-ERR-api-tester-validate-request-payloads","agent":"api-tester-validate-request-payloads","outcome":"ERROR","error":"llm returned empty"}]' \
  > agent-foundry/results/general/test-case-creator/test-case-registry.json
FORGE_WORKSPACE=agent-foundry \
FORGE_TESTCASE_AGENT=api-tester-validate-request-payloads \
python agent-foundry/scripts/ci_report_cases.py
echo "exit $?"   # must be 1

#### V9 — ci_gen_chunks.py produces correct chunk count and indices

```bash
# With 40 api-tester agents and chunk size 20 → expect [0,1]
FORGE_WORKSPACE=agent-foundry python agent-foundry/scripts/ci_gen_chunks.py api-tester 20
# must print: [0, 1]

# Scaling check: confirm formula ceil(n/20)
# e.g. 41 agents → [0,1,2];  20 agents → [0];  1 agent → [0]
```

#### V10 — ci_run_chunk.py runs the correct slice of agents

```bash
# Dry-run by monkeypatching subprocess.run to print agent name and return 0.
# Or run for real against chunk 0 (agents 0-19) in a dev environment:
FORGE_WORKSPACE=agent-foundry \
FORGE_RUN_ID=manual \
FORGE_KIND=api-tester \
FORGE_CHUNK_INDEX=0 \
FORGE_CHUNK_SIZE=20 \
FORGE_PROVIDER=claude-haiku \
python agent-foundry/scripts/ci_run_chunk.py

# Confirm output lines include:
#   [ci_run_chunk] chunk 0: 20 agent(s) (agents 0–19 of 40)
#   ── api-tester-check-authorization-rules ──...
#   ...
#   [ci_run_chunk] chunk 0 complete: N/20 passed
```
```
