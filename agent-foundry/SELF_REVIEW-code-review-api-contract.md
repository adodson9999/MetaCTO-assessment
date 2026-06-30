# SELF_REVIEW — code-review-api-contract

Group `code-review`, short name `api-contract`. Single lens: **does this break or weaken a
promise other code already depends on** — judge the backward compatibility of an
externally-depended-on interface (signatures, fields, endpoints, types, defaults, status/
error codes, semantics, versioning). Built by adapting the sibling `data-integrity` /
`logic-error` substrate to this lens; identical plumbing, divergent prompt and held-out set.

## Deliverable set (all present)

- Prompt module: `agents/common/apicontract_prompt.py` (13 debate-gated APPROVED_LINES).
- Driver: `agents/common/apicontract.py` (per-case run + score + emit, sandbox-guarded).
- Spec/scoring substrate: `agents/common/apicontract_spec.py` (case load, oracle, strict
  `{rating, notes}` schema, band scoring).
- Four framework dispatchers: `agents/code-review/api-contract/{subagent,langgraph,crewai,claude_sdk}/run.py`.
- Canonical prompt artifact: `agents/code-review/api-contract/subagent/code-review-api-contract.md`
  (frontmatter + body; body byte-identical to `APPROVED_PROMPT` — verified).
- Judge: `judge/code-review/api-contract/metric.json` + `score.py`.
- Held-out: `results/code-review/api-contract/held_out.jsonl` (6 cases; the 2 mandatory
  seeds + 4 lens-covering cases).
- Data spec: `data/code-review-api-contract/apicontract_spec.json`.
- Host registration: `.claude/agents/code-review-api-contract.md` (confirmed written).

## Held-out coverage (AC-001..AC-006)

- AC-001 additive optional keyword param (default off) → `[85,100]` backward-compatible.
- AC-002 removed required `region` param → `[0,40]` breaks all callers (seed).
- AC-003 dropped response field clients read → `[0,40]` breaks consumers.
- AC-004 status 200-with-body → 204 → `[0,45]` changed status/semantics.
- AC-005 tightened validation `len<=100` → `len<=20` → `[0,45]` rejects old input.
- AC-006 new `/v2/users` endpoint, `/v1` untouched → `[85,100]` safely versioned/additive.

Mix is 2 clearly-good (additive / versioned) + 4 clearly-breaking, which a capable model
lands cleanly while the gold bands stay defensible per the lens.

## Verification performed

- **Oracle self-test (saturation guard):** over all 6 cases the reference (gold-band-midpoint)
  decision scores **1.0**, an **empty** emission scores **0.0**, and a **benign-wrong**
  (opposite-end) emission scores **0.0**. No fallback path saturates the metric.
- **Schema strictness (`strict` mode):** extra key / bool rating / empty notes / rating 101
  all rejected; exact `{rating, notes}` accepted.
- **Prompt consistency:** the `.md` body equals `apicontract_prompt.APPROVED_PROMPT`.
- **Compile:** all 8 new Python files `py_compile` clean.
- **Backend:** ran on the pinned `claude-cli` shim (Ollama is disabled foundry-wide; config
  `provider = "claude-cli"`). Live subagent baseline recorded in the leaderboard.

## Residual gaps / fragilities

- **Single-framework live baseline.** subagent validated end-to-end on Claude; langgraph,
  crewai, claude_sdk share the identical thin-dispatcher pattern and injected `generate`, so
  wiring risk is low, but a full four-framework parallel sweep + judge leaderboard is the
  remaining confidence step.
- **"No external dependents" exclusion is judgement-bound.** The lens says not to flag a
  purely internal interface; the held-out set encodes externally-visible changes only and
  cannot test the agent's restraint on a genuinely-internal refactor. Add a clearly-internal
  case (e.g. a renamed private helper with no callers) at `[85,100]` to exercise the
  exclusion.
- **Held-out breadth.** Not yet covered: renamed config key, narrowed type (not just length),
  changed default value, and silent-semantic-change-with-same-signature. The prompt covers
  them; grow the held-out set to exercise each.

## Concrete improvements (not auto-applied)

1. Add an internal-only refactor case rated `[85,100]` to test the "no external dependents"
   restraint directly.
2. Add 2–3 held-out cases for the uncovered facets (renamed config key, changed default,
   silent semantic change).
3. Run the full four-framework parallel sweep + judge on the Claude backend to publish the
   first real leaderboard and lock the golden baseline.
