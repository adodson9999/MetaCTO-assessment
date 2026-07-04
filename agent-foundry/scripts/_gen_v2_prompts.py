#!/usr/bin/env python3
"""Generate v2 exhaustive-test-case-generator subagent prompts from the update specs.

Each agent's canonical subagent .md is rewritten to the v2 standard
(update-prompts/api-tester/00-AUTHORING-STANDARD-exhaustive-testcases.md): a pure
test-case GENERATOR that emits ONE JSON object with a `test_cases[]` array, fills
Expected Result from the contract oracle, leaves actual_result/status for the judge,
and emits NO verdict. The lane-agnostic v2 role + schema preamble is constant; each
agent's authoritative lane surface + coverage is its verbatim Change prompt + ADDENDUM
embedded from its spec. test-ssl-tls-enforcement is skipped (hand-authored exemplar).

    python scripts/_gen_v2_prompts.py [--only <name>] [--all]
"""
from __future__ import annotations
import argparse
import glob
import re
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
SPECS = WS / "update-prompts" / "api-tester"
SKIP = {"test-ssl-tls-enforcement"}  # hand-authored exemplar, do not overwrite

CODE = {
    "test-authentication-flows": "AUTHN", "check-authorization-rules": "AUTHZ",
    "verify-third-party-oauth-integration": "OAUTH", "test-ip-allowlist-enforcement": "IPALLOW",
    "verify-crud-operation-integrity": "CRUD", "test-idempotency-of-endpoints": "IDEM",
    "test-soft-delete-behavior": "SOFTDEL", "test-concurrent-request-handling": "CONC",
    "test-bulk-operation-endpoints": "BULK", "validate-search-and-filter-queries": "SEARCH",
    "test-pagination-behavior": "PAGE", "validate-query-parameter-handling": "QPARAM",
    "verify-sorting-behavior": "SORT", "validate-request-payloads": "PAYLOAD",
    "validate-null-empty-fields": "NULLEMPTY", "verify-enum-value-restrictions": "ENUM",
    "verify-response-status-codes": "STATUS", "verify-error-message-clarity": "ERRMSG",
    "validate-json-schema-responses": "SCHEMA", "validate-header-propagation": "HEADER",
    "validate-correlation-id-propagation": "CORRID", "verify-caching-headers": "CACHE",
    "verify-content-type-negotiation": "CONNEG", "validate-api-versioning-behavior": "VERSION",
    "validate-retry-after-header-compliance": "RETRYAFTER", "test-rate-limit-enforcement": "RATELIMIT",
    "test-timeout-handling": "TIMEOUT", "test-api-gateway-routing": "GATEWAY",
    "test-webhook-delivery": "WEBHOOK", "test-event-driven-api-triggers": "EVENT",
    "test-long-polling-support": "LONGPOLL", "test-file-upload-and-download": "FILE",
    "test-multipart-form-data-handling": "MULTIPART", "test-ssl-tls-enforcement": "TLS",
    "validate-graphql-depth-limits": "GRAPHQL", "verify-audit-log-generation": "AUDIT",
    "track-defect-density": "DEFECT", "run-regression-suite": "REGRESS",
    "measure-api-consumer-satisfaction": "CSAT",
}


def spec_parts(name: str) -> tuple[str, str]:
    t = (SPECS / f"{name}.update-agent.md").read_text()
    cm = re.search(r"## Change prompt \(verbatim[^)]*\)\n(.*?)\n## (Research basis|Gap summary|De-dup)", t, re.S)
    am = re.search(r"## ADDENDUM[^\n]*\n(.*)$", t, re.S)
    return (cm.group(1).strip() if cm else ""), (am.group(1).strip() if am else "")


def preamble(name: str, code: str) -> str:
    return f"""You are an API {name} EXHAUSTIVE TEST-CASE GENERATOR (v2); your sole job is to convert one runtime-supplied feature/endpoint in your lane into a single JSON object that enumerates every testable angle as fully-detailed, plain-language test cases, and you never perform any action other than emitting that JSON object.
You AUTHOR test cases and their Expected Result ONLY. You make NO bug judgement, send NO request, and emit NO deviations, verdict, is_bug, or pass/fail — a separate judging/executing agent later runs each case, fills the Actual Result, and decides pass/fail. You fill every field EXCEPT `actual_result` (always the literal string "TO BE FILLED DURING EXECUTION") and `status` (always the literal string "Not Executed").
An orchestration prompt supplies the feature and its endpoint(s)/inputs at runtime; refer to every input ONLY by its role and never assume, hardcode, name, or mention any specific URL, path, host, port number, token, resource, or feature; if no in-lane surface is provided, fail closed with a single out-of-scope error requesting it.

Emit exactly one JSON object whose `test_cases[]` array holds the exhaustive in-lane test cases and nothing else — no prose, no code fence, no extra top-level keys. Each element of `test_cases[]` MUST contain, in plain language and maximum detail, every one of these fields: `test_case_id` (unique, stable, zero-padded, sequential, prefixed `TC-{code}-` e.g. `TC-{code}-001`); `title`; `description`; `category` (exactly one of `happy` | `negative` | `boundary` | `edge` | `broad`); `feature_under_test` (the feature role exercised, feature-agnostic); `preconditions`; `test_data` (exact inputs/variables/credentials by role); `test_steps` (sequential, reproducible steps a tester follows); `expected_result` (the exact, measurable correct behavior — status, body invariants, read-back — sourced from `agent-foundry/references/contract-oracle.md` and the given spec, NEVER the target's own observed behavior; this is the definition of correct, NOT a verdict); `actual_result` (the literal "TO BE FILLED DURING EXECUTION"); `status` (the literal "Not Executed"); `postconditions`; `severity_hint` (`critical`|`major`|`minor` — the impact IF it failed, a reporting aid only); `references` (the grounding standard — RFC/OWASP/spec section); and `tags`. Preserve this agent's prior machine fields for the judge/harness under a `machine` key inside each case (e.g. `endpoint_role`, `method`, `recipe`/`probe`, `expected_class`/`expected_by_contract`, `asserts`, `also_accept`, `steps`) so nothing structured is lost.

Enumerate your lane EXHAUSTIVELY across all five angles, still MECE across agents: **happy** (valid/typical/permitted success), **negative** (invalid/unauthorized/malformed/missing/forbidden/wrong-type/wrong-state), **boundary** (min, min−1, max, max+1, empty, zero, one, first, last, exact-limit), **edge** (nulls, unicode/homoglyph/whitespace, extreme sizes, encodings, concurrency/timing, ordering, idempotent replays, locale, precision), and **broad/combinatorial** (every documented field × method × relevant state; each enum value; each documented parameter; pairwise where the space is large). If a competent human tester could construct a distinct, reportable case for a distinct in-lane condition, emit it. Zero duplicate cases within this agent or across siblings.

Your exact lane surface, the specific cases to cover, the closed machine vocabulary, and the sibling boundaries you must defer to are defined authoritatively in the two sections below (your Change prompt and its ADDENDUM). Apply them fully; source every Expected Result from the contract oracle; keep references role-only and feature-agnostic; stay strictly in your MECE lane per `00-MECE-boundary-map.md` and, on out-of-lane input, emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope`. Read and write files only within FORGE_WORKSPACE."""


def render(name: str) -> str:
    code = CODE[name]
    change, add = spec_parts(name)
    fm = (f"---\nname: api-tester-{name}\n"
          f"description: \"API {name} exhaustive test-case GENERATOR (v2, no verdict): emits ONE JSON "
          f"object with a test_cases[] array (human-readable schema TC-{code}-NNN … expected_result, plus "
          f"machine fields under `machine`); actual_result is left 'TO BE FILLED DURING EXECUTION' and "
          f"status 'Not Executed'. Authors test cases only — a separate judge executes them and decides "
          f"pass/fail. Feature-agnostic; owns its declared MECE lane.\"\n"
          f"tools: Read\nmodel: inherit\n---\n\n")
    body = preamble(name, code)
    lane = ("\n\n## Your lane specification (authoritative — the Change prompt to apply)\n\n" + change)
    add = ("\n\n## ADDENDUM (v2 — exhaustive test-case + reporting standard)\n\n" + add) if add else ""
    tail = ("\n\n## Standard compliance & lane ownership\n\n"
            "You operate under the foundry's Universal Agent Authoring & Update Standard and the Global "
            "Authoring Standard for Exhaustive Test-Case Generation "
            "(`update-prompts/api-tester/00-AUTHORING-STANDARD-exhaustive-testcases.md`). You own a unique, "
            "mutually-exclusive slice of the test surface and NEVER emit a case owned by another agent "
            "(`00-MECE-boundary-map.md`). All code you produce is reviewed by every agent in "
            "`agents/code-review/` and must score ≥85, no exception, looping until it does. See also "
            "`references/memory-everos.md`.\n")
    return fm + body + lane + add + tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    names = [args.only] if args.only else sorted(CODE)
    wrote = 0
    for name in names:
        if name in SKIP and not args.only:
            continue
        sub = WS / "agents" / "api-tester" / name / "subagent"
        if not sub.is_dir():
            print(f"  SKIP (no subagent dir): {name}")
            continue
        md = sub / f"api-tester-{name}.md"
        if not md.exists():
            cand = sorted(glob.glob(str(sub / "*.md")))
            md = Path(cand[0]) if cand else md
        md.write_text(render(name))
        wrote += 1
        print(f"  wrote v2 prompt: {name} ({md.name})")
    print(f"\n{wrote} v2 prompts written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
