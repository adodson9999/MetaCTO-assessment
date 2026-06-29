# Shared skill — timeout test-plan construction (api-tester)

Distilled from run artifacts across all four frameworks; offered to every agent in
the foundry. Adoption is the user's call (never auto-adopted).

- Compute max_wait_s as EXACTLY upstream_timeout_s + buffer_s (never the timeout alone,
  never the injected delay) — this is the client deadline the harness enforces.
- List every endpoint from the brief once in BOTH the delayed array and the restore
  array, in the brief's order; dropping the restore phase or an endpoint scores those
  scenarios as 'missing' (zero fidelity there).
- Copy each endpoint's method (uppercased) and path verbatim, and set label to
  "METHOD path"; never rewrite, reorder, or invent an endpoint, header, or parameter.
- Emit one valid JSON object per service with exactly the seven keys and nothing else —
  a missing or unparseable plan scores every scenario for that service as 'missing'.
