# Shared skill — bulk-operation-endpoint test-plan construction

Collective (SkillClaw) skill offered to all four agents in the folder. Local
filesystem backend, air-gapped. Adoption is the user's call — never auto-applied.

## Distilled know-how

When converting a bulk-endpoint brief into a plan, the failure modes that lose
Bulk-Test Fidelity are:

1. **Expanding `[N]`.** `valid_item_template` (e.g. `{"title": "Bulk Item [N]", ...}`)
   must stay one literal object with `[N]` intact. The harness substitutes `[N]` with
   each item number and builds the 8 valid items, the missing-required item, the
   wrong-type item, the all-invalid batch, and the oversize batch. An agent that
   pre-expands the template into a list, or replaces `[N]` with `1`, breaks the build.
2. **Quoting integers.** `max_batch_size`, `valid_count`, `oversize_count`, and the
   four `expected_*` codes are bare JSON integers. Quoted strings ("207") are a defect.
3. **Dropping a key / wrong key count.** The plan is exactly fourteen keys. Dropping a
   defect selector (`missing_field`, `wrongtype_field`, `wrongtype_value`) silently
   removes the very cases that prove invalid items are rejected with the offending
   field named.
4. **"Fixing" a defect selector.** `wrongtype_value` (an integer in a string field) and
   `missing_field` are deliberate defects. Replacing the integer with a valid string,
   or swapping the missing field for a present one, defeats the wrong-type / missing
   assertions. Copy all three verbatim.
5. **Redirecting the endpoint.** `endpoint` is copied from the brief, and the harness
   ignores any agent-supplied endpoint anyway — it always targets the trusted local
   bulk endpoint. Never invent a path or point off-host.
6. **Fabricating results.** The agent emits a plan only. It never POSTs a batch, never
   queries the DB, never reports a 207 / per-item status / record count. The harness
   does all execution and recording; a hallucinated "100%" is an automatic fidelity loss.

## One-line invariant

`{14 keys}` — integers bare, `[N]` verbatim, `required_fields` + `valid_item_template`
copied unchanged, the three defect selectors copied verbatim, nothing executed by the
agent. The harness asserts 207 + 8×2xx + 2×400 (naming the offending fields) + DB
delta = valid_count, all-invalid → all 400 + delta 0, oversize → 413/400 + delta 0.

## Target note

DummyJSON has NO bulk endpoints (no 207, no per-item array, no persistence). The test
runs against a separate, local, air-gapped, spec-conformant bulk target
(`tools/bulk_target/app.py`); DummyJSON is left 100% untouched.
