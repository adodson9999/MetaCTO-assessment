# Shared skill — api-tester / verify-sorting-behavior (SkillClaw pool)

Collective, cross-agent skill for the sorting-behavior workflow. Offered to all four
agents (langgraph, crewai, claude_sdk, api-tester-verify-sorting-behavior); adoption
is staged for the user's review — never auto-adopted.

Distilled reinforcement (the failure modes most worth guarding against):

- Always emit exactly twenty seed records, each with both "name" and "created_at";
  never drop a record or collapse duplicates — the ordering test needs twenty
  distinct, known values, and a short or duplicated seed fails the seed_count check.
- Keep the twenty names in the given deliberately-non-alphabetical order; never
  "tidy" them into alphabetical order, which would make a correct sort indistinguishable
  from a no-op.
- Give created_at a fixed base of "2026-06-25T12:00:00Z" and a strict two-second step
  in ISO-8601 UTC with a trailing Z; never substitute the current time or vary the
  step, so created_at ordering stays deterministic and distinct from name ordering.
- Emit all six sort cases in the fixed order; for each "order" case carry the correct
  "field" and "direction" and the matching params {sort, order} so the harness can
  verify every adjacent record pair.
- Construct both negative probes precisely: invalid_sort_field sends only
  sort="nonexistent_field" (no order key) and expects 400 with a message naming the
  field; invalid_order_direction sends sort="name" with order="sideways" and expects
  400 (the bad order must be paired with a valid sort field so it is actually validated).
- Keep every params value a literal JSON string and every expect_status the bare
  integer 200 or 400; never normalise a value to a number or a status to a string.
