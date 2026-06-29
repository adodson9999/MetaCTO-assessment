# Code-Review Perspective Agents — rating edition

Twenty single-lens code reviewers. Each reads one piece of code (a line, a
function, or a whole script) and returns **one rating out of 100 plus notes**.
Format matches the foundry's subagent prompt (`../general-documentation-reviewer.md`):
YAML frontmatter (`name`, `description`, `tools`, `model: inherit`) + a body —
here the body is a short, fully-defined, numbered-step prompt.

## The output contract (identical for every agent)

```json
{"rating": <integer 0-100>, "notes": "<one string>"}
```

- `rating` — integer 0 (worst through this lens) to 100 (nothing to improve through this lens).
- `notes` — when `rating < 100`: the reason it is not 100 **and** what would make it 100; when `rating == 100`: a statement that no change is needed.
- Exactly those two keys. Exactly one bare JSON object. No prose, no code fences.

## How a non-deterministic LLM is forced to the correct output

You cannot make an LLM's prose deterministic, so — following the skill's own
`guardrails.md` / `determinism.md` / `golden-tests.md` — we force the **structure**
and never compare the prose. Three layers do this:

1. **Schema** (`schema/review_output.schema.json`) — the formal JSON Schema for
   `{rating, notes}`: integer 0–100, non-empty string, no extra keys.
2. **Guardrail** (`guardrails/validate_output.py`) — a deterministic, stdlib-only
   validator. Same input → same verdict, always. It parses exactly one bare JSON
   object and rejects code fences, surrounding prose, extra keys, float/string/bool
   ratings, out-of-range ratings, and empty notes. This is the gate an agent's
   output must pass before it is trusted.
3. **Tests + golden suite** —
   - `tests/test_validate_output.py` (pytest): unit tests pinning every rule of
     the guardrail.
   - `tests/golden.json`: `schema_cases` (inline good/bad outputs that MUST pass
     or fail exactly as marked — the deterministic forcing function) and
     `band_cases` (example code whose rating must land in an expected band,
     ±`band_tolerance`).
   - `tests/golden_run.py`: runs the schema cases with no model (always) and the
     band cases against recorded agent outputs you supply.

The prompt itself carries the same rules in its "Hard output rules" section, so
the agent is told the contract and the harness enforces it.

## Running the gates

```bash
# unit tests for the guardrail
pytest -q tests/test_validate_output.py

# validate a single agent output
echo '{"rating": 90, "notes": "..."}' | python3 guardrails/validate_output.py

# golden suite (schema cases always run; add --outputs to check band cases)
python3 tests/golden_run.py
python3 tests/golden_run.py --outputs ./recorded --require-bands
```

> Note: these were authored and reviewed but not executed in-session (the
> sandbox shell was unavailable). They use only the Python standard library plus
> pytest; run the three commands above to confirm green.

## The twenty perspectives

Original nine: `math-correctness`, `system-design`, `device-stack`, `network`,
`security`, `vulnerability`, `unit-test`, `performance`, `logic-error`.

Ten added: `concurrency`, `error-handling-resilience`, `data-integrity`,
`memory-resource`, `maintainability`, `api-contract`, `observability`,
`dependency-supply-chain`, `adversarial-input`, `domain-requirements`.

New: `minimalist` — *less is more*; rewards code with nothing left to remove.

> `security` (posture/attack surface) and `vulnerability` (concrete exploits) are
> intentionally separate — run both.

## Ranking with the fleet

Because every agent emits the same `{rating, notes}`, ranking is trivial and
deterministic: run all twenty over the same code, sort by `rating` ascending, and
the lowest scores are the most urgent issues; the `notes` tell you exactly what to
change to push each lens to 100. An aggregate (e.g. min, or mean) gives a single
headline score per piece of code.

## Files

```
schema/review_output.schema.json      the formal output schema
guardrails/validate_output.py         deterministic validator (the gate)
tests/test_validate_output.py         pytest unit tests
tests/golden.json                     schema_cases + band_cases
tests/golden_run.py                   golden runner
<perspective>-reviewer.md  x20        the agent prompts
```

## Placement note

To slot into the foundry's per-agent convention, move each `<name>.md` to
`agent-foundry/agents/<group>/<name>/subagent/<name>.md` (e.g. group
`code-review`), copy `golden.json` to `tests/golden/<group>/<name>/golden.json`,
and add a thin `run.py` dispatcher per agent mirroring the documentation-reviewer.
