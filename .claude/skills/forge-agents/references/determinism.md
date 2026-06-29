# Determinism Review — wraps every AI action

Inspired by the QAN non-deterministic-agent pipeline (generate → execute across
runs → compare → review), this is a **cross-cutting guardrail**: *anything* an AI
produces in this skill is reviewed for non-determinism before it is trusted or
written. No exceptions (constitution Article I.8). That includes:

- agent code / prompts authored in Phase 3,
- debate-gate verdicts,
- the judge's scores,
- every self-revision in the Phase 4.5 improvement loop,
- the data-input pattern report.

The enforcer is `scripts/determinism_check.py`. It is scaffolded into the foundry
workspace and writes a **receipt** per reviewed artifact under
`results/_global/determinism/`.

## The review

Given an AI action `A` that should be repeatable:

1. **Sample N times.** Re-run `A` `N` times (default `N=5`, from
   `config.toml [determinism].samples`) under the resolved backend, fixing every
   knob that *should* be fixed: same input, `temperature=0` where the backend
   supports it, same seed where available, same sandbox.
2. **Canonicalize.** Reduce each output to the part that must be stable. For
   structured outputs, compare the **canonical JSON** (sorted keys, normalized
   whitespace) and the **deterministic fields** (counts, labels, constant values,
   schema shape) — never free-text prose. For prompts, compare the gated lines.
3. **Compare.** Compute agreement across the N samples:
   - `deterministic` — all N canonical outputs identical.
   - `stable-within-tolerance` — they differ only in fields the metric/task marks
     non-essential, within `config.toml [determinism].tolerance`.
   - `non-deterministic` — essential fields vary.
4. **Verdict + receipt.** Write
   `results/_global/determinism/<artifact-id>-<TS>.json`:
   ```json
   {"artifact": "<id>", "kind": "agent_prompt|debate_verdict|judge_score|revision|pattern_report",
    "samples": 5, "verdict": "deterministic|stable-within-tolerance|non-deterministic",
    "essential_diff": [...], "backend": "<provider/model>", "ts": "<iso8601>"}
   ```

## Adoption rule

- `deterministic` → adopt.
- `stable-within-tolerance` → adopt, receipt records the tolerated diff.
- `non-deterministic` → **do not adopt.** For a prompt line, return it to the
  debate gate (the variance is usually residual ambiguity). For a judge score,
  the metric must be made more deterministic (program over LLM-judgement) before
  it can rank or gate. For a self-revision, discard the round and retry. A
  non-deterministic artifact can never be the thing a build certifies as "done".

## Interaction with other gates

- **Debate gate:** ambiguity is caught *before* writing a line; determinism is the
  *empirical* check that the written line actually behaves singularly. They are
  complementary — a line can pass the gate yet still sample non-deterministically,
  which sends it back to the gate.
- **Improvement loop (Phase 4.5):** every round's revision gets a determinism
  review; an unstable revision is rejected even if its single-run score is higher.
- **Guardrails:** `verify_build.py` checks that a determinism receipt exists and
  is non-`non-deterministic` for each AI artifact class (guardrails item 5).

## Cost control (built for the simplest model)

`N` defaults to 5 but is configurable down to 3 for cheap local models, and the
checker caches receipts by artifact hash so unchanged artifacts are not re-sampled.
Determinism review is deterministic plumbing — the model is only invoked to
produce the samples; the comparison is pure Python.
