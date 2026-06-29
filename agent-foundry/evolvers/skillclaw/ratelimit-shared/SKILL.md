# Shared skill — rate-limit-enforcement test-plan construction

> SkillClaw collective pool for api-tester/test-rate-limit-enforcement. Local
> filesystem backend, air-gapped. Distilled from the four agents' session artifacts;
> offered to all agents in the folder. Adoption is the user's call — never auto-applied.

## What good looks like (distilled, cross-agent)

When converting one endpoint's rate-limit contract into a test plan, the high-fidelity
pattern that reproduces the gold observed tokens is:

- Emit one JSON object with all eleven keys; copy the eight context fields verbatim.
- `at_limit.count` = **exactly `limit_n`** — the documented per-window allowance, no more.
  Over-counting fires extra requests; under-counting never reaches the boundary.
- `over_limit.count` = **exactly `1`** — the single request `N+1`. The first 429 (if the
  API enforces the limit) must land on this ordinal; multiple over-limit requests blur
  the trigger ordinal the metric reads.
- `probes` = **exactly two**, in order: `within_window` at `offset_seconds -2` and
  `after_window` at `offset_seconds 1`. The signs matter: `-2` is before the window
  closes (expect still limited), `+1` is after (expect cleared).
- Never send requests, never time anything, never guess a status/Retry-After/ordinal —
  the harness measures the real timing and records the real responses.

## Why it raises fidelity

The judge metric (Rate-Limit-Test Fidelity) rewards reproducing the gold token for every
`(endpoint, scenario)`. The tokens are determined by the request sequence the harness
executes from your plan: the burst size sets `at_limit_all_non_429`, the over-limit
request sets `over_limit_status` / `first_429_ordinal` / `trigger_precision_exact` /
`retry_after_*`, and the two probe offsets set `within_window_still_429` /
`after_window_non_429`. Any drift in count or offset moves a token off gold.

## Target reality note (DummyJSON)

DummyJSON enforces no limit, so the gold tokens for an unthrottled API are: all bursts
non-429, no 429 at any ordinal (`first_429_ordinal = none`), no Retry-After, and the
after-window probe trivially non-429. A faithful plan reproduces exactly these — the
finding is the target's, not the plan's.
