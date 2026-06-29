# Shared skill — concurrent-request-handling test-plan construction

Collective (SkillClaw) skill offered to all four agents in the folder. Local
filesystem backend, air-gapped. Adoption is the user's call — never auto-applied.

## Distilled know-how

When converting a concurrency-test brief into a plan, the failure modes that lose
Concurrency-Test Fidelity are:

1. **Expanding `[VU_ID]`.** The template `concurrent-test-[VU_ID]` must stay a single
   literal string. The harness substitutes `[VU_ID]` with each VU number 1..N and
   namespaces the ids per (run, agent). An agent that pre-expands into 50 ids, or
   replaces `[VU_ID]` with `1`, breaks the write test.
2. **Quoting integers.** `concurrency`, `expected_status`, `vu_start`, `vu_end`,
   `assert_count_delta` are bare JSON integers. Quoted strings ("50") are a defect.
3. **Dropping a key / wrong key count.** `read` has exactly 6 keys; `write` has exactly
   12. Missing `assert_zero_duplicates` / `assert_zero_missing` / `assert_count_delta`
   silently drops the DB-corruption checks that are the heart of the task.
4. **Wrong endpoint or method.** `read` is GET on the brief's read_endpoint; `write`
   is POST on the brief's write_endpoint. Never swap, never invent, never point off-host.
5. **Fabricating results.** The agent emits a plan only. It never fires the 50 requests,
   never queries the DB, never reports a status code or count. The harness does all
   execution and recording; a hallucinated "100% success" is an automatic fidelity loss.

## One-line invariant

`{"read": {6 keys}, "write": {12 keys}, "assert_zero_500": true}` — integers bare,
`[VU_ID]` verbatim, endpoints copied from the brief, nothing executed by the agent.
