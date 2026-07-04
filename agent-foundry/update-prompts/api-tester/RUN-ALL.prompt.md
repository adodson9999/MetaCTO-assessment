# Orchestration prompt — apply all 39 api-tester updates via the update-agent skill

Paste the block below into an interactive Claude Code session opened at the repo root
(the one where the `update-agent` skill and `agent-foundry/` exist).

---

You are going to bring all 39 `api-tester` agents up to standard by applying the pre-written change
specs in `agent-foundry/update-prompts/api-tester/`. **You MUST use the `update-agent` skill for every
one — one invocation per agent. Do not hand-edit any agent file, run.py, golden.json, or metric.json
directly; the update-agent skill is the only mechanism.**

Every agent becomes a **pure, exhaustive test-case generator** that makes **no bug judgement**: it
authors fully-detailed, human-readable test cases (happy/negative/boundary/edge/broad) and fills the
*Expected Result*, but leaves `actual_result` blank and `status` = `Not Executed` — a separate judge
agent decides bugs. This behavior is specified in `00-AUTHORING-STANDARD-exhaustive-testcases.md` and
carried in each file's **## ADDENDUM (v2 …)** section.

Procedure:
1. Read `agent-foundry/update-prompts/api-tester/00-INDEX-and-run-order.md`,
   `00-AUTHORING-STANDARD-exhaustive-testcases.md`, and `00-MECE-boundary-map.md` first for context,
   the reporting schema, and ownership rules.
2. For EACH agent below, in this exact order, do:
   a. Open `agent-foundry/update-prompts/api-tester/<name>.update-agent.md`.
   b. Concatenate the text under its "## Change prompt (verbatim, exhaustive)" section AND the text
      under its "## ADDENDUM (v2 — exhaustive test-case + reporting standard)" section into a single
      change prompt (the ADDENDUM is mandatory — it carries the exhaustive-coverage + no-verdict +
      reporting-schema requirements).
   c. Invoke the skill: `update-agent <name> "<change prompt + addendum>"`.
   d. Let the skill run its full flow (debate/determinism/analyze/re-judge/code-review ≥85/regression
      + golden regression). Do NOT proceed to the next agent until the current one completes and passes.
3. Process ONE agent at a time. If an update **hard-halts** (regression below golden baseline, a
   code-review reviewer < 85 that won't converge, or an `/analyze` contradiction), STOP, show me the
   skill's halt report, and wait for my decision — never force or bypass a gate.
4. Skip `create-postman-collection` entirely (it is moving to the general/ folder).
5. On the oversized-request seam (414/431): apply the files as written (all three aspects kept). If the
   MECE gate flags a duplicate identity, follow the recommendation in 00-INDEX-and-run-order.md (drop the
   414/431 cases from `test-api-gateway-routing`, keep its "no backend hit" assertion) and note it.
6. After each agent passes, give me a one-line result (agent, score delta, pass). At the end, give a
   summary table of all 39 and flag anything that halted.

Run order (39 agents):
1. test-ssl-tls-enforcement
2. validate-graphql-depth-limits
3. verify-audit-log-generation
4. validate-retry-after-header-compliance
5. validate-correlation-id-propagation
6. track-defect-density
7. run-regression-suite
8. measure-api-consumer-satisfaction
9. validate-null-empty-fields
10. verify-enum-value-restrictions
11. validate-request-payloads
12. validate-query-parameter-handling
13. validate-search-and-filter-queries
14. test-pagination-behavior
15. verify-sorting-behavior
16. verify-response-status-codes
17. verify-error-message-clarity
18. validate-json-schema-responses
19. validate-header-propagation
20. verify-caching-headers
21. verify-content-type-negotiation
22. validate-api-versioning-behavior
23. test-rate-limit-enforcement
24. test-timeout-handling
25. test-api-gateway-routing
26. test-webhook-delivery
27. test-event-driven-api-triggers
28. test-long-polling-support
29. test-file-upload-and-download
30. test-multipart-form-data-handling
31. verify-crud-operation-integrity
32. test-idempotency-of-endpoints
33. test-soft-delete-behavior
34. test-concurrent-request-handling
35. test-bulk-operation-endpoints
36. test-authentication-flows
37. check-authorization-rules
38. verify-third-party-oauth-integration
39. test-ip-allowlist-enforcement

Begin with agent 1 now, using the update-agent skill.
