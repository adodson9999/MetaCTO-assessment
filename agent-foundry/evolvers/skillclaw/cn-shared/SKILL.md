# Shared skill — content-type-negotiation test-plan construction

Collective (SkillClaw) skill pool offered to all four content-type-negotiation
agents. Local filesystem, air-gapped. Adoption is staged and is the user's call —
nothing here is auto-applied.

Distilled cross-agent lessons (the plausible failures the debate gate flagged):

- Branch strictly on the brief's `kind`. An `accept` endpoint yields exactly five
  probes with keys `label`/`accept`; a `consumes` endpoint yields exactly three
  probes with keys `label`/`content_type`. Never mix the two key sets.
- Copy each media type and token (`application/json`, `application/xml`, `text/csv`,
  `text/html`, `*/*`, `text/plain`) verbatim from the named brief field. Do not
  normalise, lowercase, drop charset parameters, or expand `*/*`.
- Use the fixed literal labels exactly (`accept_application_json`,
  `accept_text_html_unsupported`, `ctype_text_plain_unsupported`, …). The harness
  buckets every probe by label; a renamed label scores as a missing scenario.
- Copy `endpoint` (and `method` for consumes) character-for-character, keeping any
  `{id}` placeholder as-is — the executor substitutes it.
- Emit exactly one parseable JSON object, never a code fence or prose, and never a
  guessed status code, Content-Type, or body-validity verdict.
