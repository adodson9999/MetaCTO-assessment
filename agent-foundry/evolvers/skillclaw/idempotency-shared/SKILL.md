# Shared skill — idempotency test-plan construction (api-tester)

Distilled from run artifacts across all four frameworks; offered to every agent in
the foundry. Adoption is the user's call (never auto-adopted).

- Build exactly two idempotent-endpoint probes that REUSE one Idempotency-Key across
  all three replays: put {method PUT, path /<collection>/<target_id>, body
  {"title":"idempotency-probe"}, key A, replays 3} and delete {method DELETE, same path,
  body null, key B, replays 3}. The reused key is what makes it an idempotency test —
  never rotate the key between the three replays.
- Build one create probe: post {method POST, path /<collection>/add, key C, replays 3}
  PLUS a distinct second_key D for the fresh-key check (a real idempotency layer makes a
  fresh key create a DISTINCT record).
- Keep every key a fixed literal and every replays count exactly 3 — the executor compares
  the three responses BYTE-FOR-BYTE (not semantic JSON), so a stable, reproducible plan is
  required. The plan never sends requests or guesses responses.
- Emit one valid JSON object per collection and nothing else — a missing or unparseable
  plan scores every scenario for that collection as 'missing' (zero fidelity there).
