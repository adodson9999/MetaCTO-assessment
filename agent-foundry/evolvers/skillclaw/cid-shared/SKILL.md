# Shared skill — correlation-ID propagation test construction (cid-shared)

Collective, cross-agent skill pool for the api-tester / validate-correlation-id-propagation
workflow. Local filesystem backend, air-gapped. Offered to all four agents; adoption is the
user's call (staged, never auto-adopted).

## Distilled guidance (the patterns that survive the judge metric)

- Emit the single eight-key object with the five brief values copied unchanged and the three
  built values (`with_header_request`, `no_header_request`, `assertions`) shaped exactly per
  the contract.
- The **with-header request** carries the `correlation_id` **byte-for-byte** under the exact
  `header_name`; never normalize, trim, lowercase, or re-encode it — a modified id makes a real
  propagation match impossible to observe.
- The **no-header request** carries **no** correlation-ID header of any name — that is what
  exercises the API's UUID-v4 auto-generation.
- Write the token as the literal `Bearer <valid_token>`; the harness substitutes the real token.
- Emit the **ten assertion labels in the fixed order**; dropping or reordering them leaves
  scenarios uncovered (scored `missing` = a fidelity miss).
- Never send a request, read a log, or guess a result — the harness executes and records.

## Provenance

Distilled from the four agents' debate-gated prompts under the SkillClaw collective-evolution
pattern. The single judge metric (Correlation-ID-Propagation-Test Fidelity) is the only gate.
