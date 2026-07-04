# Implementation Plan — Contract-Conformance Oracle rollout to ALL 39 api-tester agents

**Goal.** Apply one cross-cutting fix (from `suggested-fix.md`) to every one of the 39 agents so they
test like a manual API tester: assert the **universal HTTP/REST contract** (not the target's own docs),
emit a **`deviations[]`** findings channel, verify effects **black-box by read-back**, **soak** each
case, cover the **full documented surface**, and carry **no behaviour-anchored/lenient oracle**.

**Applies to:** all 39 agents in `agent-foundry/agents/api-tester/` (the set in
`agent-foundry/registry/coverage-manifest.json`).
**Prerequisite artifact:** `agent-foundry/references/contract-oracle.md` — the universal contract table
(the one in `suggested-fix.md` §1). The rollout creates it first; every agent cites it.
**Anti-bias invariant:** the guardrail encodes *universal conventions + the intended contract + the
documented surface only*. It never names a specific target bug. Same oracle on any API.

---

## 1. Hard guardrail (inserted VERBATIM into every agent — all four frameworks + the judge)

Insert this clause into each agent's system prompt, beside the existing Standard-compliance,
Code-review, and Runtime-feature-injection clauses. It is a **hard** guardrail: an agent that omits it,
or that still carries a behaviour-anchored oracle or a deviation-absorbing `also_accept`, **fails
closed** (non-zero exit, no results written).

```
## Contract-conformance oracle & deviation findings (hard guardrail)

Your expected outcome for every case is the UNIVERSAL HTTP/REST contract for that operation, read from
`agent-foundry/references/contract-oracle.md` — NEVER the target's own documentation or observed
behaviour. For each case emit `expected_by_contract` (the status + invariants from the contract table)
and, only when the target's documented expectation differs, `expected_by_docs`. A separate
deterministic harness fills `observed` and emits `deviations[]` — every case where observed differs
from expected_by_contract, or where expected_by_docs differs from expected_by_contract — as findings,
surfaced EVEN WHEN the response is acceptable by the target's own docs. Verify every effect BLACK-BOX by
read-back (a follow-up request): a create is proven by a follow-up GET returning the resource, a delete
by a follow-up GET returning 404, an update by a follow-up GET reflecting the change — never by a
database row, log line, or injected instrumentation the target may not expose; where such an assertion
is impossible black-box, degrade to the observable signal rather than skipping it. Repeat each case the
configured soak count and flag any non-deterministic result as a deviation. Enumerate the FULL
documented surface — every resource × every method, and every field/parameter including nested paths and
date/range; a documented capability that is unimplemented (404 or ignored) is a `missing_capability`
deviation. You MUST NOT encode the target's observed behaviour as the contract, and MUST NOT carry an
`also_accept` that admits a deviation from a standard code (e.g. accepting 200 for a creation the
contract fixes at 201); either is a hard-guardrail violation and fails closed.
```

---

## 2. Applying it to all 39 (the change)

For each agent in `coverage-manifest.json`, run `update-agent` to (a) insert the guardrail clause above
across all four frameworks + the judge, (b) **de-bias** the spec (strip every behaviour-as-contract
clause and deviation-absorbing `also_accept`), and (c) extend the emit contract with
`expected_by_contract` per case and a top-level `deviations[]`. Use the one-at-a-time runner pattern
(`RUN.md`) so each agent is completed, gate-verified, and recorded before the next.

Batch instruction (paste once; runs all 39, one at a time, resumable via `PROGRESS.md`):

```
For each agent in agent-foundry/registry/coverage-manifest.json, in order, run update-agent to: (1) create agent-foundry/references/contract-oracle.md from suggested-fix.md §1 if it does not yet exist; (2) insert the "Contract-conformance oracle & deviation findings (hard guardrail)" clause VERBATIM into the agent's system prompt across LangGraph, CrewAI, Claude Code subagent, and Claude Agent SDK and the judge, beside the Standard-compliance / Code-review / Runtime-feature-injection clauses; (3) de-bias its spec — remove any "documented soft-delete markers", "write-persistence (persisted or simulated) as the contract specifies", "follow-up read reflects the original", and any also_accept that admits a non-standard code — replacing each expectation with the contract-oracle value; (4) extend the emitted plan so every case carries expected_by_contract and the run emits deviations[]; (5) pass the code-review gate (≥85 every reviewer) and the golden + unit tests in §3–§4, holding or improving the baseline; then record the agent [x] in PROGRESS.md before the next. Keep every agent feature-agnostic and bug-blind. Do not skip an agent and do not weaken a gate.
```

---

## 3. Golden test cases (canonical, byte-stable — one per agent, same shape everywhere)

For a fixed canonical brief, the agent's emitted plan must match a golden that demonstrates the
guardrail. The invariant portion (identical across all 39) is:

```json
{
  "contract_oracle": "agent-foundry/references/contract-oracle.md",
  "soak": 3,
  "emits_deviations": true,
  "cases": [
    {
      "case": "create",
      "operation": "create",
      "expected_by_contract": { "status": 201, "invariants": ["id_or_location_present", "readback_reflects_create"] }
    },
    {
      "case": "delete",
      "operation": "delete",
      "expected_by_contract": { "status_class": "2xx", "invariants": ["readback_returns_404"] }
    },
    {
      "case": "list_sort",
      "operation": "list_sort",
      "expected_by_contract": { "status": 200, "invariants": ["output_monotonic_on_sort_key", "nested_keys_included"] }
    }
  ]
}
```

Golden rules (asserted byte-stable per `tests/golden/api-tester/<name>/golden.json`):
- every `case` carries `expected_by_contract`;
- create → `201`; delete → `readback_returns_404`; update → `readback_reflects_change`;
- **no** `case` has an `also_accept` that includes a lower/standard-code downgrade;
- top-level `emits_deviations: true` and `soak >= 2`;
- keys and case order are deterministic.

---

## 4. Unit tests (per agent — run against the emitted plan + the prompt)

`tests/api-tester/<name>/test_contract_oracle.py`:

```python
import json, pathlib, re, pytest

AGENT = "<name>"  # parametrized per agent by the harness
PLAN = json.loads(pathlib.Path(f"results/api-tester/{AGENT}/canonical_plan.json").read_text())
PROMPT = pathlib.Path(f"agents/api-tester/{AGENT}/subagent/api-tester-{AGENT}.md").read_text(encoding="utf-8")

BIAS_PHRASES = [
    "documented soft-delete markers",
    "as the contract specifies",
    "follow-up read reflects the original",
    "not actually persisted",
]

def test_prompt_has_contract_oracle_guardrail():
    assert "Contract-conformance oracle" in PROMPT, "guardrail clause missing"
    assert "agent-foundry/references/contract-oracle.md" in PROMPT, "contract-oracle reference missing"

def test_prompt_is_debiased():
    for p in BIAS_PHRASES:
        assert p not in PROMPT, f"behaviour-anchored oracle still present: {p!r}"

def test_every_case_has_contract_expectation():
    assert PLAN.get("emits_deviations") is True, "deviations[] channel not declared"
    assert PLAN.get("soak", 0) >= 2, "soak repetition missing"
    for c in PLAN["cases"]:
        assert "expected_by_contract" in c, f"case {c.get('case')} lacks expected_by_contract"

def test_no_standard_code_downgrade():
    for c in PLAN["cases"]:
        ac = c.get("also_accept", [])
        if c.get("operation") == "create":
            assert 200 not in ac, "create case downgrades 201→200 via also_accept (bias)"

def test_black_box_readback_for_effects():
    ops = {c["operation"]: c["expected_by_contract"].get("invariants", []) for c in PLAN["cases"]}
    if "create" in ops: assert "readback_reflects_create" in ops["create"]
    if "delete" in ops: assert "readback_returns_404" in ops["delete"]
```

---

## 5. Verification test — "it was added correctly to each and every agent"

The single acceptance test. It discovers **all** agents from the manifest and proves each one carries
the guardrail, is de-biased, and declares the new emit contract — in every prompt copy — and that the
**checked set equals the manifest** (no agent skipped). Static, so it runs today over the prompt files.

`tests/api-tester/test_contract_oracle_rollout.py`:

```python
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]          # agent-foundry/
MANIFEST = json.loads((ROOT / "registry/coverage-manifest.json").read_text())
AGENTS = sorted(k.split("/", 1)[1] for k in MANIFEST["agents"])   # 39 short names

REQUIRED = [
    "Contract-conformance oracle",                 # the guardrail heading
    "agent-foundry/references/contract-oracle.md", # the universal table it cites
    "expected_by_contract",                        # per-case contract oracle
    "deviations",                                  # findings channel
    "read-back",                                   # black-box effect verification
    "soak",                                        # repetition for intermittents
    "missing_capability",                          # full-surface negatives-of-omission
]
FORBIDDEN = [                                       # de-bias: must be gone
    "documented soft-delete markers",
    "as the contract specifies",
    "follow-up read reflects the original",
    "not actually persisted",
]
# every prompt copy that must carry it: the canonical subagent prompt + the four framework runners + judge
def prompt_copies(agent):
    base = ROOT / "agents/api-tester" / agent
    yield base / "subagent" / f"api-tester-{agent}.md"
    for fw in ("langgraph", "crewai", "claude_sdk", "subagent"):
        p = base / fw / "run.py"
        if p.exists(): yield p
    j = ROOT / "judge/api-tester" / agent / "score.py"
    if j.exists(): yield j

def check(agent):
    problems = []
    seen_any = False
    for f in prompt_copies(agent):
        if not f.exists(): continue
        seen_any = True
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in REQUIRED:
            if m not in text: problems.append(f"{f.name}: missing marker {m!r}")
        for b in FORBIDDEN:
            if b in text: problems.append(f"{f.name}: biased phrase still present {b!r}")
    if not seen_any: problems.append("no prompt copies found")
    return problems

def test_contract_oracle_added_to_every_agent():
    report, failed = [], {}
    for a in AGENTS:
        probs = check(a)
        status = "PASS" if not probs else "FAIL"
        report.append(f"  {a:<44} {status}")
        if probs: failed[a] = probs
    print("\nContract-oracle rollout verification (" + str(len(AGENTS)) + " agents):")
    print("\n".join(report))
    # no-bypass: the checked set must equal the manifest set, and every agent must pass
    assert len(AGENTS) == len(MANIFEST["agents"]), "manifest/agent-set mismatch"
    assert not failed, "agents missing the contract-oracle guardrail or still biased:\n" + json.dumps(failed, indent=2)

if __name__ == "__main__":
    try:
        test_contract_oracle_added_to_every_agent(); print("\nALL 39 OK")
    except AssertionError as e:
        print("\nFAIL:", e); sys.exit(1)
```

Run it: `python tests/api-tester/test_contract_oracle_rollout.py` (or `pytest -s` for the per-agent
table). It **fails loudly** naming any agent that is missing a marker, still carries a biased phrase, or
isn't in the manifest — so "added to each and every agent" is proven, not assumed.

---

## 6. Acceptance (no-bypass)

The rollout is complete only when, for **all 39** agents: the guardrail clause is present in every
prompt copy (§5), the golden matches (§3), the per-agent unit tests pass (§4), the code-review gate is
≥85 on every reviewer, the regression baseline held or improved, and
`test_contract_oracle_rollout.py` is green with the checked set equal to the manifest. Any missing
marker, residual biased phrase, or skipped agent fails the rollout. Agents stay feature-agnostic and
bug-blind throughout.

I can now (a) generate `references/contract-oracle.md` from the table, (b) drop the two test files in
place, and (c) run the batch to apply the guardrail across the 39 — say go.
