# SELF_REVIEW — api-tester / create-postman-collection ("n601")

Phase-6 self-questioning pass. Findings are reported, not auto-applied.

## What is solid
- **Deterministic core fully verified, no LLM/server needed.** `build_gold.py` →
  14 HTTP cases, 14 items, 100% coverage, 14/14 scenarios. The oracle (feeding contracts
  through the real harness) confirms the metric discriminates and is NOT saturated:
  reference 14/14; empty 2/14 (0% cov); wrong-filter 3/14 (0% cov); wrong-group 13/14;
  drop any header trigger 13/14; drop any of the 4 body triggers 13/14; empty variables
  13/14; bad method regex 13/14.
- **Saturation bug found and fixed.** The build-path extractors originally fell back to
  the canonical constants when a contract knob was missing, so a do-nothing/empty contract
  silently built the correct collection and scored 100%. Fallbacks are now benign-wrong
  (empty), so an omitted knob is a defect; `reference_contract()`/`ideal_for()` keep the
  canonical values explicitly, so gold is unaffected.
- **DummyJSON untouched; Newman isolated.** An early `npm i newman` walked up to the
  DummyJSON root `package.json`; that change was reverted (`git checkout`), the package
  removed from the root `node_modules`, and Newman reinstalled in a self-contained
  `tools/newman/` with its own `package.json`. Newman validation is real (loads via the
  bundled `postman-collection` SDK) and correctly rejects malformed collections.
- **Pipeline wired end-to-end:** run → `judge/.../score.py` (fidelity) → `judge_score.py`
  (leaderboard). All four agents emit even when the LLM is unreachable.

## HIGH — live ranking is blocked (by owner constraint, not a defect)
The owner set Ollama as the backend and asked that the server NOT be started. With Ollama
down, all four agents emit an empty contract and tie at the 14.29% floor (recorded with a
PROVENANCE banner in the leaderboard). The live ranking needs `ollama serve` (+ the
configured model pulled) then `bash scripts/phase4_postman_run.sh`. This is the same
blocked-live state as the other recent forge builds.

## HIGH — likely 4-way tie even when Ollama is up
The contract is thirteen mostly-constant knobs (regexes, fixed trigger lists, fixed
variables). A capable local model will likely reproduce it verbatim across all four
frameworks → a 4-way 100% fidelity tie, as seen on other highly-determined builds. The
recurring recommendation applies: add a latency/token tie-breaker to the judge, or
parameterize the contract (e.g. vary base_url / group key / status forms per run) so the
ranking has something to separate on. Not done here to stay within the established judge
shape.

## MEDIUM — the registry is a fixture, not the real n600 output
n600 (`test-case-creator`) is a sibling agent being built concurrently; it produces the
real `results/test-case-registry.json`. n601's forge measurement deliberately reads the
bundled fixture so it is deterministic and isolated from that concurrent write. The
production CLI reads the real `results/` registry. When n600 lands, run the CLI against
its output to validate n601 on genuine data; the fixture's `step_text` style (capitalized
`Assert`, `→ assert`) was chosen to match the spec regexes and may differ from n600's
actual phrasing — if n600 emits lowercase "assert", many statuses will resolve to 0 (the
spec's primary regex is case-sensitive). That is a property of the spec, surfaced here as
a finding.

## MEDIUM — spec quirks corrected, and documented
- The spec's test-script line `"functi() {"` is an obvious typo; valid Postman/Newman
  JavaScript requires `"function() {"`, which is what the harness emits (otherwise the
  collection would not be importable). Documented in `postman_spec.test_lines`.
- The spec's `newman run ... --dry-run` uses a flag Newman does not have. The intent
  (validate the collection is structurally valid v2.1 without firing requests) is honored
  via Newman's own `postman-collection` loader. Documented in `metric.json` + task_spec.

## LOW — two fixture mutations are no-ops (not metric weakness)
Swapping `status_pattern_primary`/`fallback` is a no-op on this fixture because no
`step_text` matches both forms (mutually exclusive). This is a property of the fixture
text, not the metric; a step containing both an `Assert …` and a `→ assert …` form would
distinguish a swap. Body triggers were made independently testable (each maps to exactly
one case) after an initial redundancy ("with body" is a substring of "with body:").

## LOW — concurrent-workspace coupling
The foundry is being refactored by a parallel process (runner package, prompt stubs)
while this build ran; the four `run.py` were rewritten to thin dispatchers over
`common/runners/*`. The build was aligned to that convention and re-verified. Shared paths
(`results/test-case-registry.json`, `agent_built_prompts/`) are contended; n601's forge
path avoids the shared registry by reading the fixture directly.

## Suggested next steps (user's call)
1. Start Ollama and run `scripts/phase4_postman_run.sh` for the live leaderboard.
2. When n600 lands, run `python scripts/postman_collection_cli.py --workspace .` against
   the real registry and confirm 100% coverage on genuine data.
3. Add a judge tie-breaker (latency or emitted-token count) to break the expected tie.
