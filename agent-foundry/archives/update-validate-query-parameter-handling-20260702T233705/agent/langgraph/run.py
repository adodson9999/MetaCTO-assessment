#!/usr/bin/env python3
"""Thin dispatcher: langgraph runner for api-tester-validate-query-parameter-handling.

Delegates all framework boilerplate to common/runners/langgraph_runner.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import queryparam  # noqa: E402
from queryparam_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt  # noqa: E402
from runners.langgraph_runner import build_invoker  # noqa: E402

AGENT = "langgraph"
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-validate-query-parameter-handling.md"


TOTALS: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _add_usage(meta: dict | None) -> None:
    if not meta:
        return
    TOTALS["prompt_tokens"] += int(meta.get("input_tokens", 0) or 0)
    TOTALS["completion_tokens"] += int(meta.get("output_tokens", 0) or 0)
    TOTALS["total_tokens"] += int(meta.get("total_tokens", 0) or 0)



def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message, on_usage=_add_usage)

    def generate(cfg: dict) -> dict:
        brief = queryparam.collection_brief(cfg)
        return queryparam.extract_json(invoke(brief)) or {}

    summary = queryparam.run_queryparam_test(AGENT, generate, usage=lambda: TOTALS)
    print(f"[{AGENT}] accuracy={summary['query_param_handling_accuracy_pct']}% scenarios={summary['scenarios_api_correct']}/{summary['scenarios_total']} tokens={summary['tokens']['total_tokens']}")


if __name__ == "__main__":
    main()

# --- Contract-oracle rollout (plan 40): hard guardrail carried in every prompt copy ---
# ## Contract-conformance oracle & deviation findings (hard guardrail)
#
# Your expected outcome for every case is the UNIVERSAL HTTP/REST contract for that operation, read from
# `agent-foundry/references/contract-oracle.md` — NEVER the target's own documentation or observed
# behaviour. For each case emit `expected_by_contract` (the status + invariants from the contract table)
# and, only when the target's documented expectation differs, `expected_by_docs`. A separate
# deterministic harness fills `observed` and emits `deviations[]` — every case where observed differs
# from expected_by_contract, or where expected_by_docs differs from expected_by_contract — as findings,
# surfaced EVEN WHEN the response is acceptable by the target's own docs. Verify every effect BLACK-BOX by
# read-back (a follow-up request): a create is proven by a follow-up GET returning the resource, a delete
# by a follow-up GET returning 404, an update by a follow-up GET reflecting the change — never by a
# database row, log line, or injected instrumentation the target may not expose; where such an assertion
# is impossible black-box, degrade to the observable signal rather than skipping it. Repeat each case the
# configured soak count and flag any non-deterministic result as a deviation. Enumerate the FULL
# documented surface — every resource × every method, and every field/parameter including nested paths and
# date/range; a documented capability that is unimplemented (404 or ignored) is a `missing_capability`
# deviation. You MUST NOT encode the target's observed behaviour as the contract, and MUST NOT carry an
# `also_accept` that admits a deviation from a standard code (e.g. accepting 200 for a creation the
# contract fixes at 201); either is a hard-guardrail violation and fails closed.
