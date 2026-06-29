# Shared skill — IP-allowlist-enforcement test-plan construction

> SkillClaw collective pool for api-tester/test-ip-allowlist-enforcement. Local filesystem
> backend, air-gapped. Distilled from the four agents' session artifacts; offered to all
> agents in the folder. Adoption is the user's call — never auto-applied.

## What good looks like (distilled, cross-agent)

When converting one restricted endpoint's IP-allowlist contract into a test plan, the
high-fidelity pattern that reproduces the gold observed tokens is:

- Emit one JSON object with all eleven keys; copy the ten context fields verbatim.
- `cases` = **exactly the five fixed enforcement cases, in order**:
  1. `allowlisted_baseline` — `allow_ip`, no XFF, `none` → expect **200 + data**. Proves a
     legitimately-allowlisted source IP is admitted.
  2. `nonallowlisted_baseline` — `block_ip`, no XFF, `none` → expect **403 + no data**. The
     negative baseline; a `200` here is a critical P1 bypass.
  3. `xff_spoof_rejected` — `block_ip`, **`send_xff = allow_ip`**, `none` → expect
     **403 + no data**. The crux: the allowlist must decide on the edge-verified source IP,
     never the client-supplied `X-Forwarded-For`. An endpoint that returns `200` here trusts
     a forgeable header — the classic IP-allowlist bypass.
  4. `allowlist_add_allows` — `block_ip`, no XFF, **`add_block_ip`** → expect **200 + data**.
     Confirms an allowlist addition actually takes effect.
  5. `allowlist_remove_blocks` — `block_ip`, no XFF, **`remove_block_ip`** → expect
     **403 + no data**. Confirms removal re-blocks and leaves no stale access.

## Failure modes this pattern avoids

- **Honoring X-Forwarded-For for access control.** The single most important assertion;
  case 3 exists solely to catch it. Never weaken its expectation to 200.
- **Leaking resource data in a 403 body.** `expect_data` is `false` on every blocked case;
  a 403 that still carries records is a data exposure, not just a status mismatch.
- **Dropping the management lifecycle.** Cases 4 and 5 must both run, in order — add then
  remove — so the allowlist returns to baseline and the update path is verified both ways.
- **Letting the agent act.** The agent only emits the plan; the harness performs every
  request, sets the source IP and XFF, and runs the allowlist add/remove. The agent never
  sends a request, never mutates the allowlist, and never guesses a result.
