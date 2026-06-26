# Shared skill — null-and-empty-fields request-body test construction

Collective, cross-agent skill (SkillClaw, local-filesystem backend, air-gapped) distilled
from the four agents' sessions on the api-tester / validate-null-empty-fields task. Offered
to every agent in the folder; adoption is the user's call (staged, never auto-adopted).

## What this skill encodes
Turning one endpoint's request-body schema into the complete null/empty test matrix as a
single JSON object with six keys, with byte-exact bodies so a deterministic harness can send
them and grade against the documented null/empty contract.

## Hard-won rules (the failure modes to avoid)
1. **Never type-filter the empty states.** Every required field gets all SEVEN states
   (key_absent, json_null, empty_string, integer_zero, boolean_false, empty_array,
   empty_object); every optional field gets SIX (the same minus boolean_false). Do NOT skip
   a state because its JSON type matches the field's declared type — that is the wrong-type
   task's rule, not this one.
2. **Mutate exactly one field per body** (except the explicit null combinations), leaving
   every other field at its known-valid value; `key_absent` removes the key entirely.
3. **The combinations are bounded.** `each_required_null` = one body per required field.
   `combo_required_null` = one body per unordered pair when ≤5 required fields, else exactly
   one half-null body (first floor(N/2) required fields). Never enumerate all subsets.
4. **string_null is the 4-character string `"null"`, NOT the JSON null token.** This probe
   exists precisely to confirm a literal string "null" is treated as an ordinary non-null
   string; collapsing it to `null` destroys the test.
5. **Emit only the JSON object.** No prose, no status codes, no guesses — a separate program
   sends the bodies and records the real responses.

## Provenance
Seeded from the debate-gated approved prompt (literal / adversarial / intent / Ultron gate).
Backend for this build: Claude (`claude-haiku-4-5`). Metric gate: Null-Empty-Test Fidelity.
