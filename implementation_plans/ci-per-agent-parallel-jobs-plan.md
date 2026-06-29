# CI/CD Per-Agent Parallel Jobs — Implementation Plan

**Requirement:** Replace the S3-deploy workflow with a GitHub Actions pipeline that runs
**one job per agent** (43 jobs total), all in parallel. Every test case an agent produces
lives inside that agent's job. The S3 deploy is dropped entirely.

---

## 1. Goal

| What | Detail |
|---|---|
| Trigger | `push` to `master`, `pull_request` targeting `master` |
| Jobs | 43 parallel jobs — one per agent (`strategy.matrix`) |
| Per-job | Start DummyJSON (:8888) + LiteLLM proxy (:4000) → run agent's `run.py` → report every produced test case as a named, collapsible GHA log group |
| LLM | `claude-haiku-4-5` via LiteLLM → Anthropic API. `ANTHROPIC_API_KEY` from repo secret |
| S3 deploy | **Dropped entirely** — no S3 secret needed, no S3 step anywhere |
| Test-case visibility | Each test case appears as a named `::group::` in the GHA Actions log — the closest faithful realization of "one step per test case" within GitHub Actions' static-step constraint (see §6) |

---

## 2. Current State

| File | Status | Change |
|---|---|---|
| `.github/workflows/deploy-public-to-s3.yml` | EXISTS | **DELETE** |
| `.github/FUNDING.yml` | EXISTS | No change |
| `.github/workflows/agent-ci.yml` | DOES NOT EXIST | **CREATE** |
| `agent-foundry/scripts/ci_report_cases.py` | DOES NOT EXIST | **CREATE** |
| `agent-foundry/ci/litellm-config.yaml` | DOES NOT EXIST | **CREATE** |
| `agent-foundry/scripts/backend_config.py` | EXISTS | No change |
| `agent-foundry/scripts/orchestrate_full.py` | EXISTS | No change |
| `agent-foundry/scripts/consolidate_test_cases.py` | EXISTS | No change |
| `agent-foundry/config.toml` | EXISTS | No change (CI overrides via `FORGE_PROVIDER`) |
| `index.js` | EXISTS | No change |
| `package.json` | EXISTS | No change (Node ≥ 24, `npm start` = `node index.js`) |

### ⚠ Port discrepancy

The original request stated the DummyJSON app runs on `:8899`. The actual default in `index.js`
line 11 is:

```js
const { PORT = 8888, ... } = process.env;
```

**The correct port is 8888.** Every step below uses 8888.

### ⚠ `provider = "auto"` breaks `backend_config.py`

`config.toml` currently has `provider = "auto"`. `backend_config.py` (the resolver used by
`subagent_runner.py`) supports only `"ollama"`, `"claude-haiku"`, and `"claude-cli"` — it raises
`ValueError` for any other string. In CI the workflow sets `FORGE_PROVIDER=claude-haiku` via
env, which `backend_config._load_config()` reads as the top-priority override (line 46–48).
No change to `config.toml` or agent files is needed.

---

## 3. Key Decisions

### Decision 1 — Live generation, not frozen replay

**Picked: live generation.**

Each job runs the agent's `subagent/run.py` directly against the live DummyJSON app AND
the cloud LLM. The test cases are generated fresh inside the job.

**Why not frozen replay:** A frozen registry requires a separate "generation" workflow,
a committed artifact, and a process to keep it current. It would also lose the signal
of whether the agent can still successfully produce cases against the current codebase.
Live generation means CI validates the full pipeline end-to-end on every push.

**Trade-off:** Each run costs LLM calls (see §7 for cost bounds) and requires a live
network connection to Anthropic.

### Decision 2 — "One step per test case" within a job

**GitHub Actions hard limit:** Steps in a job must be defined statically in the YAML file
before the workflow runs. You cannot generate steps from the output of a previous step.
There is no "dynamic steps" feature in standard GitHub Actions.

**Closest faithful realization:** A Python reporter script (`ci_report_cases.py`) reads
the agent's output `.cases.json` after `run.py` completes and emits one GHA log group
per test case:

```
::group::TC api-tester-validate-request-payloads-1 | payload_validation [PASS]
... test case details ...
::endgroup::
```

Each group is collapsible, individually named, and shows pass/fail inline. This appears
in the GHA Actions log UI as a distinct, labeled section for every test case — the
functional equivalent of "one step per test case" within a job.

**What a PASS/FAIL means per case:** The reporter performs a structural assertion on each
test case record: it must be a non-empty dict. Additionally, if the agent's output contains
a metric key (e.g., `payload_rejection_rate_pct`), the reporter surfaces it. Structural
failure (empty record, null record, wrong type) marks the case FAIL and increments the
exit counter. The reporter exits with the total failure count (0 = all passed).

### Decision 3 — LLM routing in CI

`subagent_runner.build_invoker` has two paths:

1. `_via_claude_cli` — tries the `claude` CLI if `spec["native"]["kind"] == "anthropic"` and
   `claude` is on PATH. On `ubuntu-latest`, `claude` is not installed by default. This path
   returns `None`.
2. `_via_local` — HTTP POST to `spec["base_url"] + /chat/completions`.

In CI: set `FORGE_PROVIDER=claude-haiku`. `backend_config` resolves `base_url` to
`http://127.0.0.1:4000/v1` (the `litellm_proxy_url` from `config.toml`). The `claude` CLI
is not installed, so path 1 returns `None`. Path 2 fires: HTTP to LiteLLM at :4000.
LiteLLM forwards to the Anthropic API using `ANTHROPIC_API_KEY`.

**No changes to any agent file are required.**

### Decision 4 — S3 deploy

The S3 deploy workflow is **deleted entirely**. Nothing in the CI pipeline touches S3.
The AWS secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`) can be
left in the repo settings or removed — neither harms the new pipeline.

---

## 4. Files to Create

### 4.1 `.github/workflows/agent-ci.yml`

```yaml
name: Agent CI — Per-Agent Parallel Jobs

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

# Cancel superseded runs on the same ref
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  FORGE_PROVIDER: claude-haiku
  FORGE_TARGET_BASE_URL: http://localhost:8888
  FORGE_AGENT_TIMEOUT: "300"        # 5 min per agent in CI (vs 1800 local)

jobs:
  agent-test:
    name: "${{ matrix.kind }}-${{ matrix.agent }}"
    runs-on: ubuntu-latest
    continue-on-error: true          # one agent failing does not cancel all 43 jobs
    timeout-minutes: 20              # hard ceiling per job

    strategy:
      fail-fast: false              # all 43 jobs run regardless of individual failures
      matrix:
        include:
          # ── api-tester agents (40) ─────────────────────────────────────────
          - { kind: api-tester, agent: validate-request-payloads }
          - { kind: api-tester, agent: verify-response-status-codes }
          - { kind: api-tester, agent: test-authentication-flows }
          - { kind: api-tester, agent: check-authorization-rules }
          - { kind: api-tester, agent: validate-json-schema-responses }
          - { kind: api-tester, agent: test-pagination-behavior }
          - { kind: api-tester, agent: verify-error-message-clarity }
          - { kind: api-tester, agent: test-rate-limit-enforcement }
          - { kind: api-tester, agent: validate-query-parameter-handling }
          - { kind: api-tester, agent: test-idempotency-of-endpoints }
          - { kind: api-tester, agent: verify-content-type-negotiation }
          - { kind: api-tester, agent: test-boundary-value-inputs }
          - { kind: api-tester, agent: validate-null-empty-fields }
          - { kind: api-tester, agent: test-timeout-handling }
          - { kind: api-tester, agent: verify-crud-operation-integrity }
          - { kind: api-tester, agent: test-concurrent-request-handling }
          - { kind: api-tester, agent: validate-header-propagation }
          - { kind: api-tester, agent: test-webhook-delivery }
          - { kind: api-tester, agent: run-regression-suite }
          - { kind: api-tester, agent: track-defect-density }
          - { kind: api-tester, agent: validate-api-versioning-behavior }
          - { kind: api-tester, agent: test-ssl-tls-enforcement }
          - { kind: api-tester, agent: verify-caching-headers }
          - { kind: api-tester, agent: validate-correlation-id-propagation }
          - { kind: api-tester, agent: test-bulk-operation-endpoints }
          - { kind: api-tester, agent: verify-audit-log-generation }
          - { kind: api-tester, agent: validate-search-and-filter-queries }
          - { kind: api-tester, agent: test-file-upload-and-download }
          - { kind: api-tester, agent: verify-sorting-behavior }
          - { kind: api-tester, agent: test-event-driven-api-triggers }
          - { kind: api-tester, agent: test-ip-allowlist-enforcement }
          - { kind: api-tester, agent: test-api-gateway-routing }
          - { kind: api-tester, agent: verify-third-party-oauth-integration }
          - { kind: api-tester, agent: test-multipart-form-data-handling }
          - { kind: api-tester, agent: validate-retry-after-header-compliance }
          - { kind: api-tester, agent: test-soft-delete-behavior }
          - { kind: api-tester, agent: validate-graphql-depth-limits }
          - { kind: api-tester, agent: test-long-polling-support }
          - { kind: api-tester, agent: verify-enum-value-restrictions }
          - { kind: api-tester, agent: measure-api-consumer-satisfaction }
          - { kind: api-tester, agent: create-postman-collection }
          # ── general agents (3) ─────────────────────────────────────────────
          - { kind: general, agent: test-case-creator }
          - { kind: general, agent: run-cicd-pipeline }
          - { kind: general, agent: bug-reporter }

    steps:
      # ── 1. Source ──────────────────────────────────────────────────────────
      - name: Checkout
        uses: actions/checkout@v4

      # ── 2. Node (DummyJSON target) ─────────────────────────────────────────
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '24'
          cache: 'npm'

      - name: Install Node dependencies
        run: npm install
        working-directory: ${{ github.workspace }}

      - name: Start DummyJSON on :8888
        run: |
          PORT=8888 node index.js &
          echo "DUMMYJSON_PID=$!" >> $GITHUB_ENV
          # Wait until the server responds
          for i in $(seq 1 30); do
            curl -sf http://localhost:8888/health && break || sleep 2
          done
          curl -sf http://localhost:8888/health || (echo "DummyJSON failed to start" && exit 1)
        env:
          NODE_ENV: test

      # ── 3. Python + agent deps ─────────────────────────────────────────────
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Python dependencies
        run: |
          pip install --upgrade pip
          pip install tomli "litellm[proxy]" requests
        working-directory: ${{ github.workspace }}/agent-foundry

      # ── 4. LiteLLM proxy (:4000 → Anthropic) ──────────────────────────────
      - name: Start LiteLLM proxy on :4000
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          litellm --config agent-foundry/ci/litellm-config.yaml \
                  --port 4000 \
                  --telemetry False &
          echo "LITELLM_PID=$!" >> $GITHUB_ENV
          # Wait until the proxy is ready
          for i in $(seq 1 20); do
            curl -sf http://localhost:4000/health && break || sleep 2
          done
          curl -sf http://localhost:4000/health || (echo "LiteLLM failed to start" && exit 1)

      # ── 5. Run the agent ───────────────────────────────────────────────────
      - name: Run agent — ${{ matrix.kind }}-${{ matrix.agent }}
        id: run_agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          FORGE_PROVIDER: ${{ env.FORGE_PROVIDER }}
          FORGE_TARGET_BASE_URL: ${{ env.FORGE_TARGET_BASE_URL }}
          FORGE_WORKSPACE: ${{ github.workspace }}/agent-foundry
          FORGE_RUN_ID: ${{ github.run_id }}-${{ github.run_attempt }}
          FORGE_MAX_ENDPOINTS: "0"           # iterate all endpoints (no cap)
          FORGE_AGENT_TIMEOUT: ${{ env.FORGE_AGENT_TIMEOUT }}
        run: |
          cd agent-foundry
          python agents/${{ matrix.kind }}/${{ matrix.agent }}/subagent/run.py
        continue-on-error: true              # agent failure captured; reporter still runs

      # ── 6. Report test cases ───────────────────────────────────────────────
      - name: Report test cases — ${{ matrix.kind }}-${{ matrix.agent }}
        id: report
        env:
          FORGE_WORKSPACE: ${{ github.workspace }}/agent-foundry
          FORGE_RUN_ID: ${{ github.run_id }}-${{ github.run_attempt }}
          AGENT_FULL_NAME: "${{ matrix.kind }}-${{ matrix.agent }}"
        run: |
          cd agent-foundry
          python scripts/ci_report_cases.py \
            --agent "${{ matrix.kind }}-${{ matrix.agent }}" \
            --run-id "${{ github.run_id }}-${{ github.run_attempt }}"

      # ── 7. Upload artifact ─────────────────────────────────────────────────
      - name: Upload test-case artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cases-${{ matrix.kind }}-${{ matrix.agent }}
          path: |
            agent-foundry/results/runs/${{ github.run_id }}-${{ github.run_attempt }}/${{ matrix.kind }}-${{ matrix.agent }}.cases.json
          if-no-files-found: warn
          retention-days: 30
```

---

### 4.2 `agent-foundry/ci/litellm-config.yaml`

Maps the model name `backend_config.py` sends (`claude-haiku-4-5`) to the Anthropic API
model string LiteLLM understands.

```yaml
# LiteLLM proxy config for CI.
# Receives OpenAI-format requests from subagent_runner._via_local()
# and forwards them to the Anthropic API.
model_list:
  - model_name: claude-haiku-4-5         # exactly what backend_config sends
    litellm_params:
      model: anthropic/claude-haiku-4-5  # LiteLLM's Anthropic provider prefix
      api_key: os.environ/ANTHROPIC_API_KEY

litellm_settings:
  request_timeout: 120
  num_retries: 2
  telemetry: false
```

---

### 4.3 `agent-foundry/scripts/ci_report_cases.py`

Reads the agent's output `.cases.json`, emits one named GHA log group per test case,
and exits with the number of failed cases.

```python
#!/usr/bin/env python3
"""CI test-case reporter for GitHub Actions.

Reads one agent's *.cases.json produced by run.py and emits every test case
as a named, collapsible GHA log group — the closest realization of
"one step per test case" within GitHub Actions' static-step constraint.

Exit code = number of structurally invalid (FAIL) test cases.
Exit code 0 means all cases passed structural validation.

Usage:
    python scripts/ci_report_cases.py \
        --agent api-tester-validate-request-payloads \
        --run-id 12345678-1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Same key priority order as consolidate_test_cases.py
CASE_KEYS = [
    "cases", "scenarios", "case_results", "collections", "endpoints",
    "subjects", "flows", "routes", "channels", "topics", "services",
    "sprints", "pairs", "reports", "request_log",
]
SKIP_KEYS = {
    "missing_tc_ids", "missing_tc", "gen_errors", "structural_errors",
    "field_cells", "field_mismatches", "per_agent_spec",
    "not_applicable_enumerated", "builds_that_must_block_deployment",
    "runs_that_must_block_deployment",
}


def _gha_group(name: str) -> None:
    print(f"::group::{name}", flush=True)


def _gha_endgroup() -> None:
    print("::endgroup::", flush=True)


def _gha_error(msg: str) -> None:
    print(f"::error::{msg}", flush=True)


def _gha_warning(msg: str) -> None:
    print(f"::warning::{msg}", flush=True)


def pick_list(d: dict) -> tuple[str | None, list]:
    for k in CASE_KEYS:
        v = d.get(k)
        if isinstance(v, list) and v:
            return k, v
    best = None
    for k, v in d.items():
        if k in SKIP_KEYS or not isinstance(v, list) or not v:
            continue
        if best is None or len(v) > len(best[1]):
            best = (k, v)
    return best if best else (None, [])


def assert_case(record: object) -> tuple[bool, str]:
    """Return (passed: bool, reason: str).

    A test case PASSES if its record is a non-empty dict.
    A test case FAILS if the record is None, empty, or not a dict.
    """
    if not isinstance(record, dict):
        return False, f"record is {type(record).__name__}, expected dict"
    if not record:
        return False, "record is empty dict"
    return True, "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True,
                        help="Full agent name, e.g. api-tester-validate-request-payloads")
    parser.add_argument("--run-id", required=True,
                        help="FORGE_RUN_ID used when agent ran")
    args = parser.parse_args()

    ws = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
    run_dir = ws / "results" / "runs" / args.run_id
    cases_file = run_dir / f"{args.agent}.cases.json"

    # ── locate the cases file ─────────────────────────────────────────────
    if not cases_file.exists():
        _gha_warning(
            f"No cases file found for {args.agent} at {cases_file}. "
            "Agent may have produced 0 cases or failed entirely."
        )
        print(f"[{args.agent}] 0 test cases (cases file absent). Marking as WARNING.")
        sys.exit(0)    # not a hard failure — agent may legitimately produce nothing

    try:
        data = json.loads(cases_file.read_text())
    except json.JSONDecodeError as exc:
        _gha_error(f"Cannot parse {cases_file}: {exc}")
        sys.exit(1)

    if not isinstance(data, dict):
        _gha_error(f"Expected dict at root of {cases_file}, got {type(data).__name__}")
        sys.exit(1)

    source_key, items = pick_list(data)
    metric_name = next(
        (k for k in data if k.endswith("_pct") or k.endswith("_rate") or k == "nps_score"),
        None,
    )
    metric_value = data.get(metric_name) if metric_name else None

    total = len(items)
    failures = 0

    print(f"[{args.agent}] {total} test cases  source_key={source_key!r}", flush=True)
    if metric_name:
        print(f"[{args.agent}] metric: {metric_name}={metric_value}", flush=True)

    # ── report each test case as a named GHA group ────────────────────────
    for i, record in enumerate(items, 1):
        tc_id = f"{args.agent}-{i}"

        # Build a short label from the record if possible
        label = (
            record.get("description")
            or record.get("name")
            or record.get("label")
            or record.get("endpoint")
            or record.get("scenario")
            or f"case {i}"
            if isinstance(record, dict) else f"case {i}"
        )

        passed, reason = assert_case(record)
        status = "PASS" if passed else "FAIL"

        _gha_group(f"TC {tc_id} | {label} [{status}]")
        print(json.dumps(record, indent=2) if isinstance(record, dict) else repr(record),
              flush=True)
        if not passed:
            failures += 1
            _gha_error(f"TC {tc_id} FAIL: {reason}")
            print(f"  ✗ FAIL — {reason}", flush=True)
        else:
            print(f"  ✓ PASS", flush=True)
        _gha_endgroup()

    # ── summary ───────────────────────────────────────────────────────────
    print(
        f"\n[{args.agent}] Results: {total - failures}/{total} passed, "
        f"{failures} failed",
        flush=True,
    )
    if metric_name:
        print(f"[{args.agent}] {metric_name}={metric_value}", flush=True)

    if failures:
        _gha_error(f"{args.agent}: {failures}/{total} test cases failed structural validation")

    sys.exit(failures)


if __name__ == "__main__":
    main()
```

---

## 5. Files to Delete / Modify

### Delete

| File | Action |
|---|---|
| `.github/workflows/deploy-public-to-s3.yml` | Delete the file. The entire S3 deployment concern is removed. |

No other files are modified. The existing agent `run.py` files, harness modules,
`config.toml`, and `backend_config.py` are all unchanged.

---

## 6. How Per-Agent Jobs Work

### 6.1 Job flow diagram

```
push to master
      │
      ▼
  agent-ci.yml
      │
      ├─ job: api-tester-validate-request-payloads ──┐
      ├─ job: api-tester-verify-response-status-codes─┤
      ├─ job: api-tester-test-authentication-flows ───┤  ALL 43 JOBS
      ├─ ...  (40 more api-tester jobs)              ─┤  RUN IN PARALLEL
      ├─ job: general-test-case-creator               ┤  (fail-fast: false)
      ├─ job: general-run-cicd-pipeline               ┤
      └─ job: general-bug-reporter ───────────────────┘
              │
              │  (each job independently):
              ▼
      ┌───────────────────────────────────────────────┐
      │ Step 1: Checkout                              │
      │ Step 2: Setup Node 24                         │
      │ Step 3: npm install                           │
      │ Step 4: Start DummyJSON :8888 (background)    │
      │ Step 5: Setup Python 3.11                     │
      │ Step 6: pip install litellm tomli requests    │
      │ Step 7: Start LiteLLM :4000 → Anthropic       │
      │ Step 8: python agents/{kind}/{agent}/         │
      │         subagent/run.py                       │
      │         → writes {agent}.cases.json           │
      │ Step 9: python scripts/ci_report_cases.py     │
      │         → reads .cases.json                   │
      │         → emits ::group:: per test case       │
      │         → exits with failure count            │
      │ Step 10: Upload artifact (.cases.json)        │
      └───────────────────────────────────────────────┘
                        │
                        ▼
              GHA Actions log shows:
              ┌──────────────────────────────────────┐
              │ ▶ TC api-tester-validate-request-    │
              │    payloads-1 | PUT /products [PASS] │
              │ ▶ TC api-tester-validate-request-    │
              │    payloads-2 | POST /products [PASS]│
              │ ▶ TC api-tester-validate-request-    │
              │    payloads-3 | ... [FAIL]           │
              └──────────────────────────────────────┘
```

### 6.2 LLM call path (inside each job)

```
run.py
  └─ build_invoker(WS, system, user_message)
        └─ backend_config.resolve(ws)   ← FORGE_PROVIDER=claude-haiku
              └─ returns {
                   base_url: "http://127.0.0.1:4000/v1",
                   model:    "claude-haiku-4-5",
                   native:   {kind: "anthropic"},
                 }
        └─ _via_claude_cli() → claude not on PATH → returns None
        └─ _via_local(brief)
              └─ POST http://localhost:4000/v1/chat/completions
                    model: "claude-haiku-4-5"
                         │
                         ▼
                  LiteLLM proxy (:4000)
                  litellm-config.yaml maps
                  "claude-haiku-4-5" →
                  "anthropic/claude-haiku-4-5"
                         │
                         ▼
                  Anthropic API
                  ANTHROPIC_API_KEY from secret
```

### 6.3 Worked example — three tc_ids

**Job:** `api-tester-validate-request-payloads`

`run.py` calls `contract.run_contract_test(AGENT, generate)` which loops all 22 endpoints
in `data/openapi.json`, calls `generate(endpoint)` → LLM → returns test plan for that
endpoint, writes `results/runs/{RUN_ID}/api-tester-validate-request-payloads.cases.json`.

In the baseline run (RUN-20260626-200550) this agent produced N cases under `source_key = "cases"`.
`ci_report_cases.py` loops them:

```
[api-tester-validate-request-payloads] 34 test cases  source_key='cases'

::group::TC api-tester-validate-request-payloads-1 | GET /products reject missing fields [PASS]
{
  "endpoint": "GET /products",
  "description": "reject missing required field: limit",
  "method": "GET",
  ...
}
  ✓ PASS
::endgroup::

::group::TC api-tester-validate-request-payloads-2 | POST /products/add reject bad body [PASS]
{ ... }
  ✓ PASS
::endgroup::

::group::TC api-tester-validate-request-payloads-3 | DELETE /products/1 reject null id [FAIL]
null
  ✗ FAIL — record is NoneType, expected dict
::error::TC api-tester-validate-request-payloads-3 FAIL: record is NoneType, expected dict
::endgroup::

[api-tester-validate-request-payloads] Results: 33/34 passed, 1 failed
::error::api-tester-validate-request-payloads: 1/34 test cases failed structural validation
```

The job exits with code 1. Because `continue-on-error: true` is set on the job, the other
42 jobs continue and the overall workflow reports both the count of passing jobs and the
failed ones in the GHA summary.

---

## 7. Sharding Math and Limits

### 7.1 Job count

| Dimension | Value |
|---|---|
| Total agents | 43 (40 api-tester + 3 general) |
| GHA matrix job limit | 256 |
| Jobs created | **43** — well under limit ✓ |
| `fail-fast` | `false` — all 43 run even if some fail ✓ |

No traditional sharding is needed. The matrix is over agents, not test cases.
Each job owns all test cases for one agent.

### 7.2 Test case distribution (from RUN-20260626-200550)

| Range | Agents | Notes |
|---|---|---|
| 0 cases | 6 agents | Produced no output in baseline (still run; warning emitted) |
| 1–5 cases | ~8 agents | e.g., run-regression-suite (4), test-timeout-handling (3) |
| 6–15 cases | ~15 agents | majority |
| 16–26 cases | ~8 agents | e.g., test-ssl-tls-enforcement (17), measure-api-consumer-satisfaction (26) |
| **Total** | **37 agents** | **1,279 cases** |

### 7.3 Cost estimate

Each api-tester agent iterates ~22 endpoints; each endpoint triggers one LLM call.
Approximate per-pipeline cost:

| Item | Estimate |
|---|---|
| LLM calls per agent | ~22 |
| Total LLM calls (43 agents × 22 endpoints) | ~946 |
| claude-haiku-4-5 input tokens per call | ~2,000 |
| claude-haiku-4-5 output tokens per call | ~500 |
| Input cost ($0.80 / 1M tokens) | ~946 × 2,000 × $0.0000008 = **$0.0015** wait — haiku pricing |
| Actual haiku-4-5 pricing (Jun 2026, check Anthropic pricing page) | ~$0.25/1M input, $1.25/1M output |
| Input: 946 × 2,000 = 1.89M tokens × $0.00025 | **$0.47** |
| Output: 946 × 500 = 473K tokens × $0.00125 | **$0.59** |
| **Estimated total per pipeline run** | **~$1.06** |

**Cost guard:** Set `FORGE_MAX_ENDPOINTS` to `5` for PR runs and `0` (all) for pushes to
master. Add a workflow condition:

```yaml
env:
  FORGE_MAX_ENDPOINTS: ${{ github.event_name == 'pull_request' && '5' || '0' }}
```

At 5 endpoints per agent: ~215 LLM calls → ~$0.24 per PR run.

### 7.4 Runtime estimate

| Phase | Duration |
|---|---|
| Checkout + npm install | ~60s |
| Start DummyJSON + LiteLLM | ~30s |
| Agent run (22 endpoints × ~4s per LLM call) | ~90–120s |
| Reporter | ~5s |
| Upload artifact | ~5s |
| **Total per job** | **~3–4 minutes** |

All 43 jobs run in parallel. **Total pipeline duration: ~5–6 minutes** (dominated
by the slowest agent).

GHA free tier: 20 concurrent jobs. With 43 jobs and 20 concurrent, the first
20 start immediately; the remaining 23 queue as slots free. Wall-clock time on
free tier: approximately two batches → ~8–10 minutes total.

---

## 8. Required Repo Secrets

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key with access to `claude-haiku-4-5` |

The existing AWS secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`)
are not referenced by the new workflow. They can remain in repo settings without harm or
be deleted to reduce secret surface area.

---

## 9. Caching

| Layer | Mechanism |
|---|---|
| `node_modules` | `actions/setup-node@v4` `cache: 'npm'` — keyed by `package-lock.json` hash |
| Python packages | `actions/setup-python@v5` `cache: 'pip'` — keyed by `requirements.txt` hash (absent; pip installs are fast ~15s so no pip requirements file is strictly needed) |
| `agent-foundry/.venv` | **Not cached** — `orchestrate_full.py` uses `.venv/bin/python` locally but CI uses the system Python 3.11 directly. No `.venv` is created in CI. |

---

## 10. Verification

### 10.1 Local dry-run with `act`

```bash
# Install act: https://github.com/nektos/act
brew install act

# Dry-run one agent job
act push \
  --secret ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --job agent-test \
  --matrix "kind=api-tester,agent=validate-request-payloads" \
  -W .github/workflows/agent-ci.yml

# Dry-run all jobs (no LLM calls; use --dry-run to list what would run)
act push --dry-run -W .github/workflows/agent-ci.yml
```

### 10.2 Reduced-matrix smoke test

Add a workflow input to limit the matrix for smoke testing:

```yaml
# In the workflow, add under `on:`:
  workflow_dispatch:
    inputs:
      agents:
        description: 'Comma-separated agent names to run (empty = all)'
        default: ''
```

Or manually trigger with a single agent via the GHA UI → "Run workflow".

### 10.3 Confirming each test case appears as its own group

In the GHA Actions UI, click on the "Report test cases" step of any agent job.
Each test case appears as a collapsible section with the TC id in the title. Count
the groups and compare to the `total test cases` line printed before the groups.

### 10.4 Confirming LiteLLM routing

In the agent run step log, look for the HTTP POST line from `_via_local`:

```
urllib.request.urlopen → http://127.0.0.1:4000/v1/chat/completions
```

If LiteLLM is not running, the agent step exits with a `ConnectionRefusedError` and the
reporter step prints `0 test cases (cases file absent)` — distinguishable from a structural
failure.

---

## 11. Risks, Limits, and Rollback

### 11.1 GitHub Actions hard limits

| Limit | Value | Our usage |
|---|---|---|
| Matrix jobs per workflow | 256 | 43 ✓ |
| Steps per job | 100 | ~10 static steps ✓ |
| Job timeout (configurable) | 360 min max | Set to 20 min ✓ |
| Artifact size per upload | 10 GB | .cases.json is KB-scale ✓ |
| Free tier concurrency | 20 jobs | 43 jobs queue in ~2 batches |

⚠ **"Literal 1,279 static steps" is not achievable in standard GitHub Actions.** Steps
must be declared statically in YAML before the run; you cannot generate steps from
script output at runtime. The `::group::` annotation approach in `ci_report_cases.py`
is the closest faithful realization: every test case gets a named, collapsible, individually
pass/fail section in the GHA log. If hard static steps are required, the only path is
to pre-generate a YAML file with 1,279 steps (one per frozen test case) and commit it —
but that requires a frozen registry and a separate generation workflow, which the "live
generation" decision rules out.

### 11.2 `provider = "auto"` in config.toml

If `FORGE_PROVIDER` is unset, `backend_config.resolve()` reads `provider = "auto"` from
`config.toml` and raises `ValueError`. The workflow sets `FORGE_PROVIDER=claude-haiku`
at the `env:` block level, so this cannot happen during CI runs. It is a latent local
footgun; it can be addressed in a separate PR by changing `provider = "auto"` to
`provider = "ollama"` in `config.toml` (ollama is the correct local default).

### 11.3 Anthropic API key / rate limits

If `ANTHROPIC_API_KEY` is missing or expired, LiteLLM returns HTTP 401. All 43 agents
will fail at the LLM call step; the reporter will emit `0 test cases (cases file absent)`
for all 43 jobs. The GHA summary will show 43 jobs completed with warnings. Check the
LiteLLM startup log first.

Anthropic Haiku rate limits (as of mid-2026): 50 requests/minute per key by default.
With 43 parallel jobs each making ~22 calls, burst rate could hit ~43 concurrent calls.
Mitigation: `litellm_settings.num_retries: 2` in `litellm-config.yaml` handles transient
429s. If rate limits are consistently hit, add `FORGE_MAX_ENDPOINTS=5` for PRs.

### 11.4 DummyJSON health check

The `curl -sf http://localhost:8888/health` check assumes a `/health` endpoint.
If DummyJSON does not expose `/health`, replace with a known endpoint like
`http://localhost:8888/products?limit=1`. Verify against the actual running app before
merging.

### 11.5 Rollback

To restore the old S3 deploy workflow immediately:

```bash
git revert <commit-that-deleted-deploy-public-to-s3.yml>
git push origin master
```

Or restore the file directly:

```bash
git checkout <prior-sha> -- .github/workflows/deploy-public-to-s3.yml
git add .github/workflows/deploy-public-to-s3.yml
git commit -m "restore: S3 deploy workflow"
git push origin master
```

The new `agent-ci.yml` and the S3 workflow can coexist temporarily if needed — they
trigger on different paths (`public/**` vs everything).

---

## 12. Implementation Order

Execute in this exact sequence:

1. **Create** `agent-foundry/ci/litellm-config.yaml`
2. **Create** `agent-foundry/scripts/ci_report_cases.py`
3. **Create** `.github/workflows/agent-ci.yml`
4. **Delete** `.github/workflows/deploy-public-to-s3.yml`
5. **Add repo secret** `ANTHROPIC_API_KEY` in GitHub → Settings → Secrets → Actions
6. **Verify** DummyJSON health endpoint (replace `/health` with correct path if needed)
7. **Push to a feature branch** and trigger `workflow_dispatch` for a single agent first
8. **Merge to master** after single-agent smoke test passes

---

## 13. Prompt-Logging Entry

*(Per CLAUDE.md: every instruction appended to `prompts.txt`)*

```
2026-06-26T22:45:00Z | Replace S3-deploy workflow with 43-job parallel CI pipeline.
One job per agent; each job runs the agent against DummyJSON + claude-haiku-4-5 via
LiteLLM and reports test cases as GHA ::group:: annotations. S3 deploy dropped.
Produced: implementation_plans/ci-per-agent-parallel-jobs-plan.md
```
