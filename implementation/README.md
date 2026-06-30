# api-tester — Implementation Plans

One implementation plan per `api-tester` agent (39 total), each a standalone file
`api-tester-<name>-implementation-plan.md`. Every plan has three sections:

1. **Guardrails (force no hallucination)** — hard rules that keep the agent deriving only from the
   documented target surface: plan-only (never guess a response), closed vocabulary, stay-in-lane /
   fail-closed, deterministic + exhaustive enumeration, byte-for-byte echo of provided values.
2. **Prompt (run verbatim — miss no detail)** — the complete `update-agent` build-spec prompt for
   that agent, copied verbatim from
   `agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md`, including its spec, lane
   guardrail, golden + unit tests, the Standard compliance & lane-ownership clause section, and the
   Code review section. Nothing is summarized or dropped.
3. **Test (verify the job was done correctly)** — a verification checklist plus an automated
   (pytest-style) test that fails unless every title-named case is present, no out-of-lane case
   appears, the system prompt carries the standard-compliance clause, and the code-review gate passed.

**Source of truth for the prompts:** `agent-foundry/agents/api-tester/api-tester-update-agent-prompts.md`
**Ratings & overlap rationale:** `agent-foundry/agents/api-tester/api-tester-update-plan.md`

## How to run

**To get it started (one prompt, runs all 39 one at a time):** paste the prompt in **`RUN.md`**. A
single send works through every plan **strictly one at a time** — it fully completes and verifies a
plan (guardrails → verbatim prompt → test → verify) and records it in `PROGRESS.md` before starting the
next. It never runs two at once, never skips, never weakens a gate, and resumes from `PROGRESS.md` if
interrupted.

**To step through manually (one plan per send):** paste the prompt in **`RUN-ONE.md`** — it completes
exactly one plan, records it, and stops; re-send to advance.

The README is only the index; `RUN.md` / `RUN-ONE.md` are the start prompts, and `PROGRESS.md` is the
shared ledger both use.

**To run one plan manually:**

1. Read Section 1 and hold its guardrails.
2. Paste Section 2 verbatim to the `update-agent` skill.
3. After the update completes, run Section 3's test (and confirm the code-review receipt) to verify
   the agent fully covers its title workflow with no hallucinated or out-of-lane cases.

## Agents (priority order)

Authentication: test-authentication-flows, check-authorization-rules ·
CRUD: verify-crud-operation-integrity, test-idempotency-of-endpoints, test-soft-delete-behavior ·
Search & filtering: validate-search-and-filter-queries, test-pagination-behavior, validate-query-parameter-handling ·
Error handling: validate-request-payloads, validate-null-empty-fields, verify-response-status-codes, verify-error-message-clarity, verify-enum-value-restrictions ·
Plus the remaining 26 protocol/infra/reporting agents.
